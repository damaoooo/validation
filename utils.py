from enum import Enum
from typing import List
import os
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
    
    
def count_files(root_dir, proj_file: str, lock_file: str):
    proj_file_count = 0
    lock_file_count = 0
    both_files_count = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
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
        proj_file_count, lock_file_count, both_files_count = count_files(name, proj_file, lock_file)
        table.add_row([name, proj_file_count, lock_file_count, both_files_count, proj_file_count + lock_file_count + both_files_count])

    # 打印表格
    print(table)
    
def get_git_token():
    with open("git_token") as f:
        return f.read().strip()

if __name__ == "__main__":
    print_stat_table()