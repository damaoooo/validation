from markdown import MarkdownParser
import os
from dataclasses import dataclass
from urllib.parse import urlparse, unquote
from typing import List, Union
from tqdm.asyncio import tqdm
import asyncio
import aiohttp
import shutil
from utils import LanguageSpec, get_git_token, awesome_dict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from git import Repo, GitCommandError
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, SpinnerColumn
from rich.console import Console
from rich.logging import RichHandler
import multiprocessing
import logging
import time
import threading
import argparse


def parse_args():
    """
    Parse command-line arguments for the GitHub Repository Crawler.
    Returns:
        argparse.Namespace: Parsed command-line arguments.
    Arguments:
        --language (str): Specify the language to download. Use 'all' to clone all repositories.
                          Choices are the names of languages in LanguageSpec or 'all'.
                          Default is 'all'.
        --file_mode (bool): If set, download project files only. Defaults to False.
    """
    parser = argparse.ArgumentParser(description="GitHub Repository Crawler")
    parser.add_argument(
        "--language", 
        type=str, 
        default="all", 
        choices=[lang.name for lang in LanguageSpec] + ["all"],
        help="Specify the language to download. Use 'all' to clone all repositories."
    )
    parser.add_argument(
        "--file_mode", 
        action="store_true", 
        help="If set, download project files only. Defaults to False."
    )
    return parser.parse_args()

args = parse_args()


def clone_repo(repo_url, clone_dir):
    # Clone dir should be user_name/repo_name
    repo = Repo.clone_from(repo_url, clone_dir)
    repo.submodule_update(recursive=True)
    

# 设置参数

async def fetch_file(session, url, token):
    """Fetch a single file or directory."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    async with session.get(url, headers=headers) as response:
        if response.status != 200:
            print(f"Error fetching {url}: {response.status}")
            return []
        return await response.json()

# Get file List
async def fetch_files_async(url, token, recursive=True):
    """Fetch files asynchronously."""

    async with aiohttp.ClientSession() as session:
        items = await fetch_file(session, url, token)
        if not items:
            return []
        
        tasks = []
        files = []
        
        for item in items:
            if item["type"] == "file":
                files.append(item["download_url"])
            elif item["type"] == "dir" and recursive:
                # Create a task for the directory fetch
                tasks.append(fetch_files_async(item["url"], token, recursive))

        if tasks:
            # Gather results from all directory tasks
            nested_files = await asyncio.gather(*tasks)
            for sublist in nested_files:
                files.extend(sublist)

        return files


def extract_file_info(url):
    # 解析 URL
    parsed_url = urlparse(url)
    # 获取并解码路径部分
    path = unquote(parsed_url.path)
    # 获取文件名
    file_name = os.path.basename(path)
    # 获取文件夹路径
    folder_path = os.path.dirname(path)
    return folder_path, file_name



class GitHubCrawler:
    def __init__(self, token: str, language: LanguageSpec, file_mode: bool = True, retries: int = 3, delay: int = 4):
        """
            Initialize the Crawler instance.
            Args:
                token (str): The GitHub token for authentication.
                language (LanguageSpec): The language specification for the project.
                file_mode (bool, optional): If True, download project files only. 
                                            If False, clone the entire repository. Defaults to True.
            Attributes:
                token (str): The GitHub token for authentication.
                language (LanguageSpec): The language specification for the project.
                output_dir (str): The directory where the output will be stored.
                headers (dict): The headers for the GitHub API requests.
        """
        self.token = token
        self.language = language
        self.file_mode = file_mode
        self.retries = retries
        self.delay = delay
        self.max_workers = max(32, (multiprocessing.cpu_count() or 1) * 5)
        self.console = Console()

        self.terminate_event = threading.Event()

        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(console=self.console), logging.FileHandler("git_cloner.log", mode='w')]
        )
        self.logger = logging.getLogger("GitHubCrawler")
        
        if not os.path.exists(self.language.name):
            os.makedirs(self.language.name)
            
        self.output_dir = os.path.join(os.getcwd(), self.language.name)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    async def crawl(self, github_url: str):
        # purify the URL, remove the ?tab=xxx part
        github_url = github_url.split("?")[0]

        # replace double slashes with single slash only after https://
        github_url = github_url[:8] + github_url[8:].replace("//", "/")

        # remove the trailing slash
        if github_url.endswith("/"):
            github_url = github_url[:-1]

        # purify the URL, remove the trailing hash part
        github_url = github_url.split("#")[0]
        
        repo_owner, repo_name = github_url.split("/")[-2:]
        base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents"
        files: list[str] = await fetch_files_async(base_url, self.token, recursive=False)
        
        results = []
        for file in files:
            if not file:
                continue
            for name in self.language.file_names:
                if file.lower().endswith(name.lower()):
                    results.append(file)
                    break
        
        if self.file_mode:
            return results
        else:
            # return the repo URL
            return [github_url] if results else []
            

    async def fetch_url_with_progress(self, semaphore, url):
        """Fetch a single URL with a semaphore to limit concurrency."""
        async with semaphore:
            return await self.crawl(url)
    
    async def fetch_all_urls_with_progress(self, url_list: List[str], max_concurrent=200):
        """Fetch all URLs in the list with a progress bar."""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        tasks = [
            self.fetch_url_with_progress(semaphore, url)
            for url in url_list
        ]

        # Use tqdm for progress tracking
        results = []
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Processing URLs"):
            result = await coro
            results.append(result)
        
        return results
    
    def fetch_all_urls(self, url_list: List[str]):
        results = asyncio.run(self.fetch_all_urls_with_progress(url_list))
        # remove empty results
        result = [result for result in results if result]
        
        # flatten the nested list
        return [item for sublist in result for item in sublist]
    
    async def download_file(self, session: aiohttp.ClientSession, url):
        # 解析 URL，提取路径部分
        parsed_url = urlparse(url)
        path = parsed_url.path.lstrip('/')  # Remove leading slash
        local_path = os.path.join(self.output_dir, path)

        # 创建本地目录结构
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        # 下载文件并保存到指定路径
        async with session.get(url) as response:
            if response.status == 200:
                with open(local_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
            else:
                print(f"Failed to download {url}: Status code {response.status}")

    def extract_innermost_string(self, nested: Union[str, List]) -> str:
        """递归提取最内层的字符串"""
        if isinstance(nested, str):
            return nested
        elif isinstance(nested, list) and len(nested) == 1:
            return self.extract_innermost_string(nested[0])
        else:
            raise ValueError("Invalid nested structure")
        
    async def download_file_with_semaphore(self, semaphore, session, url):
        """使用信号量限制并发下载"""
        async with semaphore:
            await self.download_file(session, url)

    async def download_files(self, url_list: List[Union[str, List]], max_concurrent=200):
        """下载所有文件并显示进度条"""
        semaphore = asyncio.Semaphore(max_concurrent)
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.download_file_with_semaphore(semaphore, session, url)
                for url in url_list
            ]
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Download Files"):
                await task
    
    def save_urls(self, url_list: List[str]):
        asyncio.run(self.download_files(url_list))
        
    def switch_branch(self, repo, branches):
        """
        切换到指定的分支列表中的第一个可用分支。

        :param repo: Repo - 已克隆的 Git 仓库对象。
        :param branches: List[str] - 尝试切换的分支列表。
        """
        for branch in branches:
            try:
                repo.git.checkout(branch)
                self.logger.info(f"✅ 成功切换到分支: {branch}")
                return
            except GitCommandError:
                self.logger.warning(f"⚠️ 无法切换到分支: {branch}")
        self.logger.error("❌ 无法切换到任何指定分支。")


    def parse_repo_url(self, repo_url):
        """
        解析仓库 URL，提取所有者和仓库名称。

        :param repo_url: str - 仓库的 URL。
        :return: tuple - (owner, repo_name)
        """
        parsed_url = urlparse(repo_url)
        path = parsed_url.path.rstrip('/')
        if path.endswith('.git'):
            path = path[:-4]
        parts = path.split('/')
        if len(parts) < 2:
            raise ValueError(f"Cannot Parse Repo URL: {repo_url}")
        owner = parts[-2]
        repo_name = parts[-1]
        return owner, repo_name
    
    def clone_repo(self, repo_url):
        """
        克隆单个 Git 仓库，带有重试机制，并保存到 /owner_name/repo_name 目录。

        :param repo_url: str - 仓库的 URL。
        :return: tuple - (repo_url, success: bool, message: str)
        """
        if self.terminate_event.is_set():
            self.logger.info(f"⏭️ 跳过克隆（程序正在终止）: {repo_url}")
            return (repo_url, False, "程序正在终止")

        try:
            owner, repo_name = self.parse_repo_url(repo_url)
        except ValueError as ve:
            self.logger.error(f"❌ 无法解析 URL: {repo_url} - {ve}")
            return (repo_url, False, str(ve))

        clone_dir = os.path.join(self.output_dir, owner, repo_name)
        if os.path.exists(clone_dir):
            self.logger.warning(f"⚠️ 仓库已存在: {clone_dir}")
            return (repo_url, False, "仓库已存在")

        for attempt in range(1, self.retries + 1):
            try:
                self.logger.info(f"🔄 开始克隆: {repo_url} 到 {clone_dir} (尝试 {attempt}/{self.retries})")
                # 确保所有者目录存在
                owner_dir = os.path.join(self.output_dir, owner)
                os.makedirs(owner_dir, exist_ok=True)
                
                repo = Repo.clone_from(repo_url, clone_dir)
                default_branch = next((b.name for b in repo.heads if b.name in ["master", "main"]), None)
                if default_branch:
                    repo.git.checkout(default_branch)
                    self.logger.info(f"✅ 成功切换到分支: {default_branch}")
                else:
                    self.logger.warning("⚠️ 未找到合适的默认分支。")
                # 检查并更新子模块
                if repo.submodules:
                    repo.submodule_update(recursive=True)
                self.logger.info(f"✅ 成功克隆: {repo_url}")
                return (repo_url, True, "克隆成功")
            except GitCommandError as e:
                self.logger.error(f"❌ 克隆失败 (尝试 {attempt}/{self.retries}): {repo_url} - {e}")
                self.delete_clone_dir(clone_dir)
                if attempt < self.retries:
                    self.logger.info(f"⏳ 等待 {self.delay} 秒后重试...")
                    time.sleep(self.delay)
                else:
                    self.logger.critical(f"❗ 克隆最终失败: {repo_url}")
                    return (repo_url, False, str(e))
            except Exception as e:
                self.logger.error(f"⚠️ 未知错误在克隆 {repo_url}: {e}")
                self.delete_clone_dir(clone_dir)
                return (repo_url, False, str(e))
            
    def delete_clone_dir(self, clone_dir):
        """
        删除克隆目录及其内容。

        :param clone_dir: str - 需要删除的目录路径。
        """
        if os.path.exists(clone_dir):
            try:
                shutil.rmtree(clone_dir)
                self.logger.info(f"🗑️ 已删除目录: {clone_dir}")
            except Exception as e:
                self.logger.error(f"❌ 删除目录失败: {clone_dir} - {e}")
    
    def download_repos(self, urls: List[str]):
        """
        执行并发克隆任务，并显示进度条。
        """
        self.logger.info("🚀 开始克隆所有仓库...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            TimeRemainingColumn(),
            console=self.console,
            transient=True
        ) as progress:
            task = progress.add_task("[green]克隆仓库... ", total=len(urls))

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_repo = {executor.submit(self.clone_repo, repo): repo for repo in urls}

                try:
                    for future in as_completed(future_to_repo):
                        repo = future_to_repo[future]
                        try:
                            repo_url, success, message = future.result()
                            # 结果已在 clone_repo 方法中记录
                        except Exception as exc:
                            self.logger.error(f"⚠️ {repo} 生成了异常: {exc}")
                        finally:
                            progress.advance(task)
                except KeyboardInterrupt:
                    self.logger.warning("🚨 检测到中断信号，正在停止所有克隆任务...")
                    self.terminate_event.set()  # 设置终止标志
                    executor.shutdown(wait=False)  # 不等待正在进行的任务
                    # 删除所有正在克隆的目录
                    for future in future_to_repo:
                        clone_dir = self.get_clone_dir(future_to_repo[future])
                        if clone_dir:
                            self.delete_clone_dir(clone_dir)
                    self.logger.info("🛑 所有克隆任务已被停止。")
                    return

        self.logger.info("🎉 所有克隆操作已完成。")


if __name__ == "__main__":
    args = parse_args()    
    language: LanguageSpec = LanguageSpec[args.language] if args.language != "all" else None
    token: str = get_git_token()
    file_mode: bool = args.file_mode
    
    if language:
        markdown_page = awesome_dict[language.name]
        parser = MarkdownParser(markdown_page)
        crawler = GitHubCrawler(token, language, file_mode=file_mode)
        all_result = crawler.fetch_all_urls(parser.url_list)
        if file_mode:
            crawler.save_urls(all_result)
        else:
            crawler.download_repos(all_result)
    else:
        for lang, markdown_page in awesome_dict.items():
            language = LanguageSpec[lang]
            parser = MarkdownParser(markdown_page)
            crawler = GitHubCrawler(token, language, file_mode=file_mode)
            all_result = crawler.fetch_all_urls(parser.url_list)
            if file_mode:
                crawler.save_urls(all_result)
            else:
                crawler.download_repos(all_result)
        
    # markdown_page = "https://raw.githubusercontent.com/vinta/awesome-python/refs/heads/master/README.md"
    # parser = MarkdownParser(markdown_page)
    
    # token = get_git_token()
    # crawler = GitHubCrawler(token, LanguageSpec.python, file_mode=False)
    
    # all_result = crawler.fetch_all_urls(parser.url_list)
    # crawler.download_repos(all_result)

    # # clone_repo("https://github.com/openembedded/bitbake", "./bitbake")

    

