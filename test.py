import os
import shutil

def copy_package_lock_files(source_dir, target_dir):
    for root, _, files in os.walk(source_dir):
        if 'package-lock.json' in files:
            # 计算相对路径
            relative_path = os.path.relpath(root, source_dir)
            # 目标路径
            target_path = os.path.join(target_dir, relative_path)
            # 创建目标目录
            os.makedirs(target_path, exist_ok=True)
            # 源文件路径
            source_file = os.path.join(root, 'package-lock.json')
            # 目标文件路径
            target_file = os.path.join(target_path, 'package-lock.json')
            # 复制文件
            shutil.copy2(source_file, target_file)
            print(f"Copied {source_file} to {target_file}")

# 示例用法
source_directory = '/repo/javascript'
target_directory = '/repo/lockfile'
copy_package_lock_files(source_directory, target_directory)
