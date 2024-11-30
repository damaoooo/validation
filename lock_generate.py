from utils import LanguageSpec
import os
import subprocess
from multiprocessing import Pool, Manager
from tqdm import tqdm

class LockGenerator:
    def __init__(self, language: LanguageSpec):
        self.language = language
        
    def generate_lock(self, pwd: str):
        os.chdir(pwd)
        # Make sure the project file is here
        if not os.path.exists(self.language.file_names[1]):
            print(f"Cannot find {self.language.file_names[1]}")
            return False
        
        try:
            match self.language:
                case LanguageSpec.python:
                    try:
                        p = subprocess.run(["poetry", "init", "-n"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=pwd)
                    except subprocess.CalledProcessError as e:
                        if "already exists" in e.stderr.decode():
                            pass
                    finally:
                        subprocess.run(["poetry", "lock"], check=True, cwd=pwd)
                case LanguageSpec.rust:
                    subprocess.run(["cargo", "generate-lockfile"], check=True, cwd=pwd)
                case LanguageSpec.javascript:
                    subprocess.run(["npm", "install", "--package-lock-only"], check=True, cwd=pwd)
                case LanguageSpec.ruby:
                    subprocess.run(["bundle", "lock"], check=True, cwd=pwd)
                case LanguageSpec.php:
                # Be Careful, this will install all the dependencies, and it may take a long time and a lot of space
                    subprocess.run(["composer", "install"], check=True, cwd=pwd)
                case _:
                    print("Not implemented yet")
            return True
        except Exception as e:
            print(f"Failed to generate lock file: {e}, file: {pwd}")
            return False

def find_folder(language: LanguageSpec):
    # Run os.walk to find the folder
    lock_file = language.file_names[0]
    proj_file = language.file_names[1]
    
    target_folders = []
    
    for root, dirs, files in os.walk(language.name):
        # Check is there is only proj file, no lock file
        if proj_file in files and lock_file not in files:
            # Get absolute path
            root = os.path.abspath(root)
            target_folders.append(root)
    return target_folders
    
def generate_locks_multi(pwd: str = os.getcwd()):
    

    
    def update_count(success: bool):
        if success:
            success_count.value += 1
        else:
            fail_count.value += 1
    
    for language in LanguageSpec:
        
        if language != LanguageSpec.php:
            continue
        
        os.chdir(pwd)
        folders = find_folder(language)
        lock_generator = LockGenerator(language)
        
        manager = Manager()
        success_count = manager.Value("i", 0)
        fail_count = manager.Value("i", 0)
        
        with tqdm(total=len(folders), desc=f"Generating locks for {language.name}") as pbar:
            with Pool(processes=os.cpu_count()) as pool:
                for _ in pool.imap_unordered(lock_generator.generate_lock, folders):
                    pbar.update()
                    update_count(_)
                    
        print(f"Generated locks for {language.name}: {success_count.value}, failed: {fail_count.value}")
        
        
def generate_locks_single(pwd: str = os.getcwd()):
    for language in LanguageSpec:
        success_count = 0
        fail_count = 0
        os.chdir(pwd)
        folders = find_folder(language)
        lock_generator = LockGenerator(language)
        
        with tqdm(total=len(folders), desc=f"Generating locks for {language.name}") as pbar:
            for folder in folders:
                pbar.set_description(f"Generating locks for {language.name} ({folder})")
                success = lock_generator.generate_lock(folder)
                pbar.update()
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    
        print(f"Generated locks for {language.name}: {success_count}, failed: {fail_count}")
    
        

if __name__ == "__main__":
    rust = LanguageSpec.rust
    generate_locks_multi()