import os
import subprocess
import logging
from multiprocessing import Pool, Manager
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.logging import RichHandler
from logging.handlers import RotatingFileHandler
from utils import LanguageSpec
import argparse
from typing import Union, List

def parse_args():
    parser = argparse.ArgumentParser(description="Generate lock files for specified languages.")
    parser.add_argument(
        "-l", "--language",
        choices=[lang.name for lang in LanguageSpec] + ["all"],
        default="all",
        help="Specify the language to generate lock files for. Default is 'all'."
    )
    parser.add_argument(
        "-m", "--multiprocessing",
        action="store_true",
        help="Use multiprocessing for lock generation. Default is False (use multithreading)."
    )
    # Add a path
    parser.add_argument(
        "-p", "--path",
        default=os.getcwd(),
        help="Specify the path to search for projects. Default is the current working directory."
    )
    return parser.parse_args()


# 配置日志记录，使用 RichHandler 以获得更好的终端显示效果
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(), RotatingFileHandler("lock_generator.log", maxBytes=1000000, backupCount=3, mode='w')]
)

logger = logging.getLogger("lock-generator")

# Emoji 前缀映射
LOG_EMOJIS = {
    'INFO': "ℹ️",
    'DEBUG': "🐛",
    'WARNING': "⚠️",
    'ERROR': "❌",
    'SUCCESS': "✅",
    'LOCK': "🔒",
    'PROCESS': "🛠️",
    'INIT': "🚀"
}

def get_emoji(level):
    return LOG_EMOJIS.get(level, "ℹ️")

class LockGenerator:
    def __init__(self, language: LanguageSpec):
        self.language = language

    def generate_lock(self, pwd: str) -> bool:
        original_dir = os.getcwd()
        try:
            os.chdir(pwd)
            logger.debug(f"{get_emoji('DEBUG')} Changed directory to {pwd}")

            proj_file = self.language.file_names[1]
            if not os.path.exists(proj_file):
                logger.warning(f"{get_emoji('WARNING')} Cannot find {proj_file} in {pwd}")
                return False

            try:
                match self.language:
                    case LanguageSpec.python:
                        try:
                            logger.debug(f"{get_emoji('INIT')} Initializing Poetry project")
                            result = subprocess.run(
                                ["poetry", "init", "-n"],
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            logger.debug(f"{get_emoji('DEBUG')} Poetry init output: {result.stdout.strip()}")
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            if "already exists" in stderr:
                                logger.info(f"{get_emoji('INFO')} Poetry project already initialized.")
                            else:
                                logger.error(f"{get_emoji('ERROR')} Poetry init failed: {pwd}:\n{stderr}")
                                return False
                        finally:
                            logger.info(f"{get_emoji('LOCK')} Generating Poetry lock file 🗝️")
                            try:
                                lock_result = subprocess.run(
                                    ["poetry", "lock"],
                                    check=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True
                                )
                                logger.debug(f"{get_emoji('DEBUG')} Poetry lock output: {lock_result.stdout.strip()}")
                            except subprocess.CalledProcessError as e:
                                stderr = e.stderr.strip()
                                logger.error(f"{get_emoji('ERROR')} Poetry lock failed: {stderr}")
                                print(f"{get_emoji('ERROR')} Poetry lock failed in {pwd}:\n{stderr}")
                                return False
                    case LanguageSpec.rust:
                        logger.info(f"{get_emoji('LOCK')} Generating Cargo lock file 🗝️")
                        try:
                            cargo_result = subprocess.run(
                                ["cargo", "generate-lockfile"],
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            logger.debug(f"{get_emoji('DEBUG')} Cargo generate-lockfile output: {cargo_result.stdout.strip()}")
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            logger.error(f"{get_emoji('ERROR')} Cargo generate-lockfile failed: {pwd}:\n{stderr}")
                            return False
                    case LanguageSpec.javascript:
                        logger.info(f"{get_emoji('LOCK')} Generating npm lock file 🗝️")
                        try:
                            npm_result = subprocess.run(
                                ["npm", "install", "--package-lock-only"],
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            logger.debug(f"{get_emoji('DEBUG')} npm install output: {npm_result.stdout.strip()}")
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            logger.error(f"{get_emoji('ERROR')} npm install failed: {pwd}:\n{stderr}")
                            return False
                    case LanguageSpec.ruby:
                        logger.info(f"{get_emoji('LOCK')} Generating Bundler lock file 🗝️")
                        try:
                            bundle_result = subprocess.run(
                                ["bundle", "lock"],
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            logger.debug(f"{get_emoji('DEBUG')} Bundler lock output: {bundle_result.stdout.strip()}")
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            logger.error(f"{get_emoji('ERROR')} Bundler lock failed: {pwd}:\n{stderr}")
                            return False
                    case LanguageSpec.php:
                        logger.info(f"{get_emoji('LOCK')} Generating Composer lock file 🗝️")
                        # 注意，这将安装所有依赖项，可能需要较长时间和大量空间
                        try:
                            composer_result = subprocess.run(
                                ["composer", "install", "--no-interaction"],
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            logger.debug(f"{get_emoji('DEBUG')} Composer install output: {composer_result.stdout.strip()}")
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            logger.error(f"{get_emoji('ERROR')} Composer install failed: {pwd}:\n{stderr}")
                            return False
                    case _:
                        logger.warning(f"{get_emoji('WARNING')} Lock generation not implemented for {self.language.name}")
                        return False
                logger.info(f"{get_emoji('SUCCESS')} Successfully generated lock file for {pwd} ✅")
                return True
            except subprocess.CalledProcessError as e:
                stderr = e.stderr.strip()
                logger.error(f"{get_emoji('ERROR')} Subprocess error: {pwd}:\n{stderr}")
                return False
            except Exception as e:
                logger.error(f"{get_emoji('ERROR')} Failed to generate lock file: {e} in {pwd}")
                print(f"{get_emoji('ERROR')} Failed to generate lock file in {pwd}:\n{e}")
                return False
        finally:
            os.chdir(original_dir)
            logger.debug(f"{get_emoji('DEBUG')} Reverted directory to {original_dir}")


class LockManager:
    def __init__(self, pwd: str = os.getcwd(), use_multiprocessing: bool = True):
        self.pwd = pwd
        self.use_multiprocessing = use_multiprocessing
        self.lock_generators = {language: LockGenerator(language) for language in LanguageSpec}
        self.manager = Manager()
        self.success_counts = self.manager.dict({language: 0 for language in LanguageSpec})
        self.fail_counts = self.manager.dict({language: 0 for language in LanguageSpec})

    def find_folders(self, language: LanguageSpec):
        lock_file, proj_file = language.file_names[:2]
        target_folders = []

        for root, dirs, files in os.walk(language.name):
            
            # restirct the depth of the search only 2, one level for owner, one level for repo
            current_depth = root[len(language.name):].count(os.sep)
            if current_depth > 2:
                dirs[:] = []
            
            if proj_file in files and lock_file not in files:
                abs_path = os.path.abspath(root)
                target_folders.append(abs_path)
                logger.debug(f"{get_emoji('DEBUG')} Found target folder: {abs_path}")

        return target_folders

    def update_counts(self, language: LanguageSpec, success: bool):
        if success:
            self.success_counts[language] += 1
        else:
            self.fail_counts[language] += 1

    def process_folder(self, language: LanguageSpec, folder: str):
        lock_generator = self.lock_generators[language]
        success = lock_generator.generate_lock(folder)
        self.update_counts(language, success)
        return success

    def generate_locks(self, languages: List[LanguageSpec]):
        os.chdir(self.pwd)
        logger.info(f"{get_emoji('PROCESS')} Starting lock generation in {self.pwd}")
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            refresh_per_second=10,
        )
        pwd = self.pwd

        with progress:
            for language in languages:
                os.chdir(pwd)
                folders = self.find_folders(language)
                if not folders:
                    logger.info(f"{get_emoji('INFO')} No folders found for {language.name}. Skipping.")
                    continue

                task_description = f"Generating locks for {language.name} 🚀"
                task = progress.add_task(task_description, total=len(folders))

                if self.use_multiprocessing:
                    executor_cls = ProcessPoolExecutor
                else:
                    executor_cls = ThreadPoolExecutor

                with executor_cls(max_workers=os.cpu_count()) as executor:
                    futures = {executor.submit(self.process_folder, language, folder): folder for folder in folders}
                    for future in futures:
                        try:
                            future.result()
                        except Exception as e:
                            folder = futures[future]
                            logger.error(f"{get_emoji('ERROR')} Error processing folder {folder}: {e}")
                            print(f"{get_emoji('ERROR')} Error processing folder {folder}:\n{e}")
                        finally:
                            progress.advance(task)

                logger.info(
                    f"{get_emoji('LOCK')} Generated locks for {language.name}: {self.success_counts[language]} succeeded, {self.fail_counts[language]} failed."
                )

        logger.info(f"{get_emoji('SUCCESS')} Lock generation process completed.")





if __name__ == "__main__":
    # 示例用法：
    # 要使用多进程，将 use_multiprocessing 设置为 True
    # 要使用多线程，将 use_multiprocessing 设置为 False
    args = parse_args()
    language: Union[str, LanguageSpec] = args.language
    multiprocessing: bool = args.multiprocessing
    path: str = args.path

    if language == "all":
        languages = list(LanguageSpec)
    else:
        languages = [LanguageSpec[args.language]]

    lock_manager = LockManager(path,  use_multiprocessing=multiprocessing)

    lock_manager.generate_locks(languages)
