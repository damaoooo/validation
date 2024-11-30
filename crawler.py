from markdown import MarkdownParser
import os
from dataclasses import dataclass
from urllib.parse import urlparse, unquote
from typing import List, Union
from tqdm.asyncio import tqdm
import asyncio
import aiohttp
from utils import LanguageSpec, get_git_token
from enum import Enum

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
    def __init__(self, token: str, language: LanguageSpec):
        self.token = token
        self.language = language
        
        if not os.path.exists(self.language.name):
            os.makedirs(self.language.name)
            
        self.output_dir = os.path.join(os.getcwd(), self.language.name)
        
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    async def crawl(self, github_url: str):
        # purify the URL, remove the ?tab=xxx part
        github_url = github_url.split("?")[0]
        
        # purify the URL, remove the trailing hash part
        github_url = github_url.split("#")[0]
        
        repo_owner, repo_name = github_url.split("/")[-2:]
        base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents"
        files: list[str] = await fetch_files_async(base_url, self.token, recursive=False)
        
        results = [file for file in files if file and any(name in file for name in self.language.file_names)]
        return results
            

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


if __name__ == "__main__":
    
    markdown_page = "https://raw.githubusercontent.com/vinta/awesome-python/refs/heads/master/README.md"
    parser = MarkdownParser(markdown_page)
    
    token = get_git_token()
    crawler = GitHubCrawler(token, LanguageSpec.python)
    
    all_result = crawler.fetch_all_urls(parser.url_list)
    crawler.save_urls(all_result)
    
    

    

