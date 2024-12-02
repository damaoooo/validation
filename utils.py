from enum import Enum
from typing import List
import os
import tomllib
import re
import json
from prettytable import PrettyTable

class LanguageSpec(Enum):
    python = ["poetry.lock", "pyproject.toml"]
    rust = ["Cargo.lock", "Cargo.toml"]
    javascript = ["package-lock.json", "package.json"]
    ruby = ["Gemfile.lock", "Gemfile", ".gemspec"]
    php = ["composer.lock", "composer.json"]

    @property
    def file_names(self) -> List[str]:
        return self.value
    
awesome_dict = {
    "python": "https://raw.githubusercontent.com/vinta/awesome-python/refs/heads/master/README.md",
    "rust": "https://raw.githubusercontent.com/rust-unofficial/awesome-rust/refs/heads/main/README.md",
    "javascript": "https://raw.githubusercontent.com/sorrycc/awesome-javascript/refs/heads/master/README.md",
    "ruby": "https://raw.githubusercontent.com/markets/awesome-ruby/refs/heads/master/README.md",
    "php": "https://raw.githubusercontent.com/ziadoz/awesome-php/refs/heads/master/README.md"
}
    
def count_files(root_dir, proj_file: str, lock_file: str):
    proj_file_count = 0
    lock_file_count = 0
    both_files_count = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
        current_depth = dirpath[len(root_dir):].count(os.sep)
        if current_depth >= 2:
            dirnames[:] = []
        has_cargo_toml = proj_file.lower() in [x.lower() for x in filenames]
        has_cargo_lock = lock_file.lower() in [x.lower() for x in filenames]

        if has_cargo_toml and has_cargo_lock:
            both_files_count += 1
        elif has_cargo_toml:
            proj_file_count += 1
        elif has_cargo_lock:
            lock_file_count += 1

    return proj_file_count, lock_file_count, both_files_count
    
def print_stat_table():
    table = PrettyTable()
    table.field_names = ["Language", "Project File Only", "Lock File Only", "Both", "Total"]

    # 遍历 LanguageSpec 枚举，统计文件数量并添加到表格中
    for lang in LanguageSpec:
        name = lang.name
        lock_file, proj_file = lang.file_names[:2]
        root_dir = os.path.join("/repo", name)
        proj_file_count, lock_file_count, both_files_count = count_files(root_dir, proj_file, lock_file)
        table.add_row([name, proj_file_count, lock_file_count, both_files_count, proj_file_count + lock_file_count + both_files_count])

    # 打印表格
    print(table)
    
def read_cargo_lock(file_path: str):
    with open(file_path, 'rb') as f:
        cargo_lock = tomllib.load(f)
    
    packages = cargo_lock.get('package', [])
    package_list = [{'name': pkg['name'], 'version': pkg['version']} for pkg in packages]
    
    return package_list

def read_composer_lock(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        composer_data = json.load(file)
    
    packages = composer_data.get('packages', [])
    package_list = [{'name': pkg['name'], 'version': pkg['version']} for pkg in packages]
    
    return package_list

def read_poetry_lock(file_path):
    with open(file_path, 'rb') as f:
        poetry_lock = tomllib.load(f)
    
    packages = poetry_lock.get('package', [])
    package_list = [{'name': pkg['name'], 'version': pkg['version']} for pkg in packages]
    
    return package_list


def read_npm_lock(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        package_lock = json.load(file)
    
    packages = package_lock.get('dependencies', {})
    package_list = [{'name': name, 'version': details['version']} for name, details in packages.items()]
    
    return package_list


def read_gemfile_lock(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # 使用正则表达式匹配 gem 名称和版本
    pattern = re.compile(r'^\s{4}(\S+)\s\(([^)]+)\)', re.MULTILINE)
    matches = pattern.findall(content)
    
    # 构建包含 gem 名称和版本的列表
    package_list = [{'name': name, 'version': version} for name, version in matches]
    
    return package_list
    
def get_git_token():
    with open("/root/workspace/validation/git_token") as f:
        return f.read().strip()

def parse_ground_truth(path: str, language: LanguageSpec):
    if language == LanguageSpec.python:
        return read_poetry_lock(path)
    elif language == LanguageSpec.rust:
        return read_cargo_lock(path)
    elif language == LanguageSpec.javascript:
        return read_npm_lock(path)
    elif language == LanguageSpec.ruby:
        return read_gemfile_lock(path)
    elif language == LanguageSpec.php:
        return read_composer_lock(path)
    else:
        raise ValueError("Language not supported")

if __name__ == "__main__":
    print_stat_table()