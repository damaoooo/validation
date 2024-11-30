from utils import LanguageSpec
import os
import subprocess

class LockGenerator:
    def __init__(self, language: LanguageSpec):
        self.language = language
        
    def generate_lock(self, pwd: str):
        os.chdir(pwd)
        # Make sure the project file is here
        if not os.path.exists(self.language.file_names[1]):
            print(f"Cannot find {self.language.file_names[1]}")
            return
        
        match self.language:
            case LanguageSpec.python:
                os.system("poetry lock")
            case LanguageSpec.rust:
                os.system("cargo generate-lockfile")
            case LanguageSpec.javascript:
                os.system("npm install --package-lock-only")
            case LanguageSpec.ruby:
                os.system("bundle lock")
            case LanguageSpec.php:
                # Be Careful, this will install all the dependencies, and it may take a long time and a lot of space
                os.system("composer install")
            case _:
                print("Not implemented yet")

def find_folder(language: LanguageSpec):
    # Run os.walk to find the folder
    lock_file = language.file_names[0]
    proj_file = language.file_names[1]
    
    target_folders = []
    
    for root, dirs, files in os.walk(language.name):
        # Check is there is only proj file, no lock file
        if proj_file in files and lock_file not in files:
            target_folders.append(root)
    return target_folders
    

if __name__ == "__main__":
    find_folder(LanguageSpec.python)
    find_folder(LanguageSpec.rust)
    find_folder(LanguageSpec.javascript)
    find_folder(LanguageSpec.ruby)
    find_folder(LanguageSpec.php)