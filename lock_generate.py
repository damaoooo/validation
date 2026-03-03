import os
import pwd
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
from rich.logging import RichHandler
from logging.handlers import RotatingFileHandler

import toml
from utils import LanguageSpec, is_poetry_project
from pathlib import Path
import tomllib
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

custom_env = os.environ.copy()
custom_env["POETRY_PACKAGE_MODE"] = "false" # 解决你遇到的这个报错
custom_env["POETRY_VIRTUALENVS_CREATE"] = "false" # SBOM 分析通常不需要真的建虚拟环境

def get_emoji(level):
    return LOG_EMOJIS.get(level, "ℹ️")

def fix_pyproject_metadata(pwd):
    """
    精确补全逻辑：根据已有字段的位置补全缺失字段，不乱跨节补充。
    """
    toml_path = Path(pwd) / "pyproject.toml"
    if not toml_path.exists():
        return False

    try:
        with open(toml_path, "r", encoding="utf-8") as f:
            data = toml.load(f)

        changed = False
        
        # 1. 检测字段位置
        # [project] 节
        p_has_name = "name" in data.get("project", {})
        p_has_version = "version" in data.get("project", {})
        
        # [tool.poetry] 节
        poetry_sec = data.get("tool", {}).get("poetry", {})
        tp_has_name = "name" in poetry_sec
        tp_has_version = "version" in poetry_sec

        # 2. 计算补全状态
        any_name = p_has_name or tp_has_name
        any_version = p_has_version or tp_has_version

        # 3. 执行“补齐对应”逻辑
        if not (any_name and any_version):
            # 情况：两个都没，默认补 [project]
            if not any_name and not any_version:
                if "project" not in data: data["project"] = {}
                data["project"]["name"] = Path(pwd).name
                data["project"]["version"] = "0.1.0"
                changed = True
            
            # 情况：缺 name，找 version 的位置来补
            elif not any_name:
                # 优先根据 project.version 补 project.name
                if p_has_version:
                    data["project"]["name"] = Path(pwd).name
                else: # 只能是 tp_has_version 有，补在 tool.poetry
                    if "tool" not in data: data["tool"] = {}
                    if "poetry" not in data["tool"]: data["tool"]["poetry"] = {}
                    data["tool"]["poetry"]["name"] = Path(pwd).name
                changed = True
            
            # 情况：缺 version，找 name 的位置来补
            elif not any_version:
                # 优先根据 project.name 补 project.version
                if p_has_name:
                    data["project"]["version"] = "0.1.0"
                else: # 只能是 tp_has_name 有，补在 tool.poetry
                    if "tool" not in data: data["tool"] = {}
                    if "poetry" not in data["tool"]: data["tool"]["poetry"] = {}
                    data["tool"]["poetry"]["version"] = "0.1.0"
                changed = True

        if changed:
            with open(toml_path, "w", encoding="utf-8") as f:
                toml.dump(data, f)
            return True

    except Exception:
        # 极端情况：文件损坏或无法解析，追加一个最基础的 [project]
        with open(toml_path, "a", encoding="utf-8") as f:
            f.write('\n[project]\nname = "{}"\nversion = "0.1.0"\n'.format(Path(pwd).name))
            f.write('[tool.poetry]\npackage-mode = false\n')
        return True

    return False


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
                            logger.debug(f"{get_emoji('WARNING')} {proj_file} in {pwd} is not a Poetry project. Skipping.")
                            return False

                        logger.warning(f"{get_emoji('LOCK')} Generating Poetry lock file 🗝️")
                        lock_success = False
                        try:
                            fix_pyproject_metadata(pwd)
                            lock_result = subprocess.run(
                                ["poetry", "lock"],
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=custom_env,
                                text=True,
                                cwd=pwd
                            )
                            logger.debug(f"{get_emoji('DEBUG')} Poetry lock output: {lock_result.stdout.strip()}")
                            lock_success = True
                        except subprocess.CalledProcessError as e:
                            stderr = e.stderr.strip()
                            logger.error(f"{get_emoji('ERROR')} Poetry lock failed: {stderr}")
                            print(f"{get_emoji('ERROR')} Poetry lock failed in {pwd}:\n{stderr}")
                        finally:
                            # 用 git restore 还原 pyproject.toml 到修改前的状态
                            restore_result = subprocess.run(
                                ["git", "restore", "pyproject.toml"],
                                cwd=pwd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            if restore_result.returncode == 0:
                                logger.debug(f"{get_emoji('DEBUG')} git restore pyproject.toml in {pwd}")
                            else:
                                logger.warning(f"{get_emoji('WARNING')} git restore failed in {pwd}: {restore_result.stderr.strip()}")
                        if not lock_success:
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


def _generate_lock_worker(language: LanguageSpec, folder: str) -> bool:
    """Module-level worker function so ProcessPoolExecutor can pickle it without pickling LockManager."""
    return LockGenerator(language).generate_lock(folder)


class LockManager:
    def __init__(self, pwd: str = os.getcwd(), use_multiprocessing: bool = True):
        self.pwd = pwd
        self.use_multiprocessing = use_multiprocessing
        self.success_counts = {language: 0 for language in LanguageSpec}
        self.fail_counts = {language: 0 for language in LanguageSpec}

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
                    futures = {executor.submit(_generate_lock_worker, language, folder): folder for folder in folders}
                    for future in futures:
                        folder = futures[future]
                        try:
                            success = future.result()
                            if success:
                                self.success_counts[language] += 1
                            else:
                                self.fail_counts[language] += 1
                        except Exception as e:
                            self.fail_counts[language] += 1
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
