from crawler import GitHubCrawler, MarkdownParser
from sbom_test import SBOMComparer, Trivy, Syft
import os
from utils import LanguageSpec, get_git_token, awesome_dict
import json
from multiprocessing import Pool, Manager
from tqdm import tqdm
import numpy as np
import shutil




def download_git_file():
    for lang, url in awesome_dict.items():
        
        parser = MarkdownParser(url)
        token = get_git_token()
        crawler = GitHubCrawler(token, LanguageSpec[lang])
        all_result = crawler.fetch_all_urls(parser.url_list)
        crawler.save_urls(all_result)
            

def download_git_repo():
    for lang, url in awesome_dict.items():
        
        parser = MarkdownParser(url)
        token = get_git_token()
        crawler = GitHubCrawler(token, LanguageSpec[lang])
        all_result = crawler.fetch_all_urls(parser.url_list)
        crawler.download_repos(all_result)
    
def run_sbom_tools(language: LanguageSpec, target_dir: str = "sbom"):
    syft = Syft()
    trivy = Trivy()
    output_dir = os.path.join(target_dir, language.name)
    comparer = SBOMComparer(trivy=trivy, syft=syft, output_dir=output_dir)
    lock_files = []
    # os walk a folder
    for root, dirs, files in os.walk(language.name):
        if root[len(language.name):].count(os.sep) > 2:
            continue
        for file in files:
            if file == language.file_names[0]:
                input_file = os.path.join(root, file)
                lock_files.append(input_file)

    with Pool(processes=os.cpu_count()) as pool:
        with tqdm(total=len(lock_files)) as pbar:
            for left_only, right_only, common in pool.imap_unordered(comparer.compare, lock_files):
                pbar.update()

def javascript_fix(input_file: str, left: list, right: list, common: list):
    with open(input_file) as f:
        data = json.load(f)
    
    self_name: str = data["name"]
    # Self Package
    left = [x for x in left if x["name"] != self_name]
    right = [x for x in right if x["name"] != self_name]
    common = [x for x in common if x["name"] != self_name]
    
    # Subname Package, like code-frame and @babel/code-frame, they are actually the same package
    
    left_remove_idx = []
    right_remove_idx = []
    common_append = []
    
    for left_idx, left_item in enumerate(left):
        for right_idx, right_item in enumerate(right):
            if left_item["name"].lower() in right_item["name"].lower() or right_item["name"].lower() in left_item["name"].lower():
                if left_item["version"] == right_item["version"]:
                    common_append.append(left_idx)
                    left_remove_idx.append(left_idx)
                    right_remove_idx.append(right_idx)
                    
    
    new_left = [x for idx, x in enumerate(left) if idx not in left_remove_idx]
    new_right = [x for idx, x in enumerate(right) if idx not in right_remove_idx]
    for item in common_append:
        common.append(left[item])
    
    return new_left, new_right, common


def analyse_sbom_diff_result(language: LanguageSpec, target_dir: str = "sbom"):
    jaccords = []
    
    output_folder = os.path.join(target_dir, language.name, "diff")
    for root, dirs, files in os.walk(output_folder):
        for file in files:
            if file.endswith(".json"):
                with open(os.path.join(root, file)) as f:
                    data = json.load(f)
                    left = data["left"]
                    right = data["right"]
                    common = data["common"]
                    
                    if language == LanguageSpec.javascript:
                        left, right, common = javascript_fix(data["input_file"], left, right, common)
                    
                    try:
                        jaccord = len(common) / (len(left) + len(right) + len(common))
                    except ZeroDivisionError:
                        jaccord = 1
                    
                    if jaccord != 1:
                        print(file, jaccord)
                    
                    jaccords.append(jaccord)
                    
    return np.mean(jaccords), np.std(jaccords)

if __name__ == "__main__":
    # download_git_repo()
    target_dir = "sbom"

    # Empty the target directory
    shutil.rmtree(target_dir, ignore_errors=True)
        
    for language in LanguageSpec:

        
        run_sbom_tools(language, target_dir=target_dir)
        mean, std = analyse_sbom_diff_result(language, target_dir=target_dir)
        print("Language:", language.name, "Mean:", mean, "Std:", std)