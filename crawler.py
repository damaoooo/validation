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
    parser.add_argument(
        "--save_dir", 
        type=str, 
        default="./repo", 
        help="Directory to save downloaded files or cloned repositories. Defaults to /repo."
    )
    return parser.parse_args()

args = parse_args()


def clone_repo(repo_url, clone_dir):
    # Clone dir should be user_name/repo_name
    repo = Repo.clone_from(repo_url, clone_dir)
    repo.submodule_update(recursive=True)
    

# Set parameters

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
    # Parse URL
    parsed_url = urlparse(url)
    # Get and decode path part
    path = unquote(parsed_url.path)
    # Get file name
    file_name = os.path.basename(path)
    # Get folder path
    folder_path = os.path.dirname(path)
    return folder_path, file_name



class GitHubCrawler:
    def __init__(self, token: str, language: LanguageSpec, repo_dir: str, file_mode: bool = True, retries: int = 3, delay: int = 4):
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
        self.repo_dir = repo_dir
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
            
        self.output_dir = os.path.join(self.repo_dir, self.language.name)
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
        # Parse URL and extract path part
        parsed_url = urlparse(url)
        path = parsed_url.path.lstrip('/')  # Remove leading slash
        local_path = os.path.join(self.output_dir, path)

        # Create local directory structure
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        # Download file and save to specified path
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
        """Recursively extract the innermost string"""
        if isinstance(nested, str):
            return nested
        elif isinstance(nested, list) and len(nested) == 1:
            return self.extract_innermost_string(nested[0])
        else:
            raise ValueError("Invalid nested structure")
        
    async def download_file_with_semaphore(self, semaphore, session, url):
        """Use semaphore to limit concurrent downloads"""
        async with semaphore:
            await self.download_file(session, url)

    async def download_files(self, url_list: List[Union[str, List]], max_concurrent=200):
        """Download all files and show progress bar"""
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
        Switch to the first available branch from the specified branch list.

        :param repo: Repo - The cloned Git repository object.
        :param branches: List[str] - List of branches to attempt switching to.
        """
        for branch in branches:
            try:
                repo.git.checkout(branch)
                self.logger.info(f"✅ Successfully switched to branch: {branch}")
                return
            except GitCommandError:
                self.logger.warning(f"⚠️ Unable to switch to branch: {branch}")
        self.logger.error("❌ Unable to switch to any specified branch.")


    def parse_repo_url(self, repo_url):
        """
        Parse repository URL to extract owner and repository name.

        :param repo_url: str - The repository URL.
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
        Clone a single Git repository with retry mechanism and save to /owner_name/repo_name directory.

        :param repo_url: str - The repository URL.
        :return: tuple - (repo_url, success: bool, message: str)
        """
        if self.terminate_event.is_set():
            self.logger.info(f"⏭️ Skip cloning (program is terminating): {repo_url}")
            return (repo_url, False, "Program is terminating")

        try:
            owner, repo_name = self.parse_repo_url(repo_url)
        except ValueError as ve:
            self.logger.error(f"❌ Unable to parse URL: {repo_url} - {ve}")
            return (repo_url, False, str(ve))

        clone_dir = os.path.join(self.output_dir, owner, repo_name)
        if os.path.exists(clone_dir):
            self.logger.warning(f"⚠️ Repository already exists: {clone_dir}")
            return (repo_url, False, "Repository already exists")

        for attempt in range(1, self.retries + 1):
            try:
                self.logger.info(f"🔄 Starting clone: {repo_url} to {clone_dir} (attempt {attempt}/{self.retries})")
                # Ensure owner directory exists
                owner_dir = os.path.join(self.output_dir, owner)
                os.makedirs(owner_dir, exist_ok=True)
                
                repo = Repo.clone_from(repo_url, clone_dir)
                default_branch = next((b.name for b in repo.heads if b.name in ["master", "main"]), None)
                if default_branch:
                    repo.git.checkout(default_branch)
                    self.logger.info(f"✅ Successfully switched to branch: {default_branch}")
                else:
                    self.logger.warning("⚠️ No suitable default branch found.")
                # Check and update submodules
                if repo.submodules:
                    repo.submodule_update(recursive=True)
                self.logger.info(f"✅ Successfully cloned: {repo_url}")
                return (repo_url, True, "Clone successful")
            except GitCommandError as e:
                self.logger.error(f"❌ Clone failed (attempt {attempt}/{self.retries}): {repo_url} - {e}")
                self.delete_clone_dir(clone_dir)
                if attempt < self.retries:
                    self.logger.info(f"⏳ Waiting {self.delay} seconds before retry...")
                    time.sleep(self.delay)
                else:
                    self.logger.critical(f"❗ Final clone failure: {repo_url}")
                    return (repo_url, False, str(e))
            except Exception as e:
                self.logger.error(f"⚠️ Unknown error while cloning {repo_url}: {e}")
                self.delete_clone_dir(clone_dir)
                return (repo_url, False, str(e))
            
    def delete_clone_dir(self, clone_dir):
        """
        Delete clone directory and its contents.

        :param clone_dir: str - The directory path to be deleted.
        """
        if os.path.exists(clone_dir):
            try:
                shutil.rmtree(clone_dir)
                self.logger.info(f"🗑️ Deleted directory: {clone_dir}")
            except Exception as e:
                self.logger.error(f"❌ Failed to delete directory: {clone_dir} - {e}")
    
    def download_repos(self, urls: List[str]):
        """
        Execute concurrent cloning tasks and display progress bar.
        """
        self.logger.info("🚀 Starting to clone all repositories...")

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
            task = progress.add_task("[green]Cloning repositories... ", total=len(urls))

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_repo = {executor.submit(self.clone_repo, repo): repo for repo in urls}

                try:
                    for future in as_completed(future_to_repo):
                        repo = future_to_repo[future]
                        try:
                            repo_url, success, message = future.result()
                            # Results are already logged in the clone_repo method
                        except Exception as exc:
                            self.logger.error(f"⚠️ {repo} generated an exception: {exc}")
                        finally:
                            progress.advance(task)
                except KeyboardInterrupt:
                    self.logger.warning("🚨 Interrupt signal detected, stopping all clone tasks...")
                    self.terminate_event.set()  # Set termination flag
                    executor.shutdown(wait=False)  # Don't wait for ongoing tasks
                    # Delete all directories being cloned
                    for future in future_to_repo:
                        clone_dir = self.get_clone_dir(future_to_repo[future])
                        if clone_dir:
                            self.delete_clone_dir(clone_dir)
                    self.logger.info("🛑 All clone tasks have been stopped.")
                    return

        self.logger.info("🎉 All clone operations completed.")


if __name__ == "__main__":
    args = parse_args()    
    language: LanguageSpec = LanguageSpec[args.language] if args.language != "all" else None
    token: str = get_git_token()
    file_mode: bool = args.file_mode
    save_dir: str = args.save_dir
    
    if language:
        markdown_page = awesome_dict[language.name]
        parser = MarkdownParser(markdown_page)
        crawler = GitHubCrawler(token, language, repo_dir=save_dir, file_mode=file_mode)
        all_result = crawler.fetch_all_urls(parser.url_list)
        if file_mode:
            crawler.save_urls(all_result)
        else:
            crawler.download_repos(all_result)
    else:
        for lang, markdown_page in awesome_dict.items():
            language = LanguageSpec[lang]
            parser = MarkdownParser(markdown_page)
            crawler = GitHubCrawler(token, language, repo_dir=save_dir, file_mode=file_mode)
            all_result = crawler.fetch_all_urls(parser.url_list)
            if file_mode:
                crawler.save_urls(all_result)
            else:
                crawler.download_repos(all_result)


