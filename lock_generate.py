import os
import subprocess
import logging
from multiprocessing import Pool, Manager
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.logging import RichHandler
from logging.handlers import RotatingFileHandler
from utils import LanguageSpec, is_poetry_project
import typer
from typing import Union, List

# Configure logging to use RichHandler for better terminal display
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(), RotatingFileHandler("lock_generator.log", maxBytes=1000000, backupCount=3, mode='w')]
)

logger = logging.getLogger("lock-generator")

# Emoji prefix mapping
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
                        # Only handle real Poetry projects and run lock directly
                        if not is_poetry_project(proj_file):
                            logger.warning(f"{get_emoji('WARNING')} {proj_file} in {pwd} is not a Poetry project. Skipping.")
                            return False

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
                            logger.debug(f"{get_emoji('DEBUG')} yarn install output: {npm_result.stdout.strip()}")
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            logger.error(f"{get_emoji('ERROR')} yarn install failed: {pwd}:\n{stderr}")
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
                        # Note: This will install all dependencies, may take a long time and require a lot of space
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
                    case LanguageSpec.go:
                        logger.info(f"{get_emoji('LOCK')} Generating Go modules lock file 🗝️ {pwd}")
                        try:
                            go_result = subprocess.run(
                                ["go", "mod", "tidy"],
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            logger.debug(f"{get_emoji('DEBUG')} Go mod tidy output: {go_result.stdout.strip()}")
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            logger.error(f"{get_emoji('ERROR')} Go mod tidy failed: {pwd}:\n{stderr}")
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

# Move Typer app and main to module level for importability
app = typer.Typer(help="Generate lock files for specified languages.")

@app.command()
def main(
    language: str = typer.Option(
        "all",
        "-l",
        "--language",
        help="Specify the language to generate lock files for. Default is 'all'. Allowed: " + ", ".join([lang.name for lang in LanguageSpec]) + " or 'all'."
    ),
    multiprocessing: bool = typer.Option(
        False,
        "-m",
        "--multiprocessing",
        help="Use multiprocessing for lock generation. Default is False (use multithreading)."
    ),
    path: str = typer.Option(
        os.getcwd(),
        "-p",
        "--path",
        help="Specify the path to search for projects. Default is the current working directory."
    ),
):
    allowed = [lang.name for lang in LanguageSpec] + ["all"]
    if language not in allowed:
        raise typer.BadParameter(f"language must be one of: {', '.join(allowed)}")

    if language == "all":
        languages = list(LanguageSpec)
    else:
        languages = [LanguageSpec[language]]

    lock_manager = LockManager(path, use_multiprocessing=multiprocessing)
    lock_manager.generate_locks(languages)


if __name__ == "__main__":
    app()
