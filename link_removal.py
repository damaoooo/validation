#!/usr/bin/env python3
import os
import subprocess
import sys
import logging
from pathlib import Path
from rich.logging import RichHandler
import shutil

# Configure logging to use RichHandler for better terminal display
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)

logger = logging.getLogger("replace-symlinks")

# Emoji prefix mapping
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
            # logger.warning(f"{get_emoji('WARNING')} {file_path} is not a symbolic link. Skip.")
            return True

        # Get the target that the symbolic link points to
        target = os.readlink(file_path)

        # Handle relative paths
        if not os.path.isabs(target):
            target = os.path.join(os.path.dirname(file_path), target)
            target = os.path.abspath(target)

        if not os.path.exists(target):
            # logger.error(f"{get_emoji('ERROR')} Target file does not exist: {target}, skip {file_path}")
            return False

        if not os.path.isfile(target):
            # logger.error(f"{get_emoji('ERROR')} Target is not a regular file: {target}, skip {file_path}")
            return False

        # Use cp command to overwrite symbolic link
        # Use shutil to copy file and overwrite existing symbolic link
        if os.path.islink(file_path):
            os.unlink(file_path)  # Delete symbolic link
        shutil.copy2(target, file_path)

        logger.info(f"{get_emoji('SUCCESS')} Successfully replaced {file_path} with {target}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"{get_emoji('ERROR')} Copy failed: {e}, file: {file_path}")
    except Exception as e:
        logger.error(f"{get_emoji('ERROR')} Error occurred while processing {file_path}: {e}")
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

    logger.info(f"{get_emoji('INFO')} Processing completed: {success_count} successful, {fail_count} failed.")

def main():
    # Get target directory, default to current working directory
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = os.getcwd()

    # Check if target directory exists
    if not os.path.isdir(root_dir):
        logger.error(f"{get_emoji('ERROR')} Directory does not exist: {root_dir}")
        sys.exit(1)

    logger.info(f"{get_emoji('INFO')} Start processing directory: {root_dir}")
    traverse_and_replace(root_dir)

if __name__ == "__main__":
    main()
