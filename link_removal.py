#!/usr/bin/env python3
import os
import subprocess
import sys
import logging
from pathlib import Path
from rich.logging import RichHandler
import shutil

# 配置日志记录，使用 RichHandler 以获得更好的终端显示效果
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)

logger = logging.getLogger("replace-symlinks")

# Emoji 前缀映射
LOG_EMOJIS = {
    'INFO': "ℹ️",
    'SUCCESS': "✅",
    'ERROR': "❌",
    'WARNING': "⚠️",
}

def get_emoji(level):
    return LOG_EMOJIS.get(level, "ℹ️")

def replace_symlink_with_cp(file_path):
    try:
        if not os.path.islink(file_path):
            # logger.warning(f"{get_emoji('WARNING')} {file_path} 不是一个符号链接。跳过。")
            return False

        # 获取符号链接指向的目标
        target = os.readlink(file_path)

        # 处理相对路径
        if not os.path.isabs(target):
            target = os.path.join(os.path.dirname(file_path), target)
            target = os.path.abspath(target)

        if not os.path.exists(target):
            # logger.error(f"{get_emoji('ERROR')} 目标文件不存在：{target}，跳过 {file_path}")
            return False

        if not os.path.isfile(target):
            # logger.error(f"{get_emoji('ERROR')} 目标不是一个常规文件：{target}，跳过 {file_path}")
            return False

        # 使用 cp 命令覆盖符号链接
        # 使用 shutil 复制文件并覆盖原有的符号链接
        shutil.copy2(target, file_path)

        logger.info(f"{get_emoji('SUCCESS')} 成功将 {file_path} 替换为 {target}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"{get_emoji('ERROR')} 复制失败：{e}，文件：{file_path}")
    except Exception as e:
        logger.error(f"{get_emoji('ERROR')} 处理 {file_path} 时发生错误：{e}")
    return False

def traverse_and_replace(root_dir):
    success_count = 0
    fail_count = 0
    target_filenames = {'Gemfile', 'Gemfile.lock'}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename in target_filenames:
                file_path = os.path.join(dirpath, filename)
                if replace_symlink_with_cp(file_path):
                    success_count += 1
                else:
                    fail_count += 1

    logger.info(f"{get_emoji('INFO')} 处理完成：成功 {success_count} 个，失败 {fail_count} 个。")

def main():
    # 获取目标目录，默认使用当前工作目录
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = os.getcwd()

    # 检查目标目录是否存在
    if not os.path.isdir(root_dir):
        logger.error(f"{get_emoji('ERROR')} 目录不存在：{root_dir}")
        sys.exit(1)

    logger.info(f"{get_emoji('INFO')} 开始处理目录：{root_dir}")
    traverse_and_replace(root_dir)

if __name__ == "__main__":
    main()
