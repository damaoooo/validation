from crawler import GitHubCrawler, MarkdownParser
from sbom import SBOMComparer, Trivy, Syft, SBOM, Package, analyze_difference
import os
from utils import LanguageSpec, get_git_token, awesome_dict, parse_ground_truth
import json
from multiprocessing import Pool, Manager
from tqdm import tqdm
import numpy as np
import shutil
import pandas as pd
from utils import SBOMStandard, SBOMFileMode


class SBOMAnalyzer:
    def __init__(self, target_dir: str = "/sbom", standard: SBOMStandard = SBOMStandard.cyclonedx, mode: SBOMFileMode = SBOMFileMode.lock):
        self.target_dir = target_dir
        self.standard = standard
        self.syft = Syft(standard=standard)
        self.trivy = Trivy(standard=standard)
        self.mode = mode

    def run_analysis(self, language: LanguageSpec):
        """Run the complete SBOM analysis process"""
        self._run_sbom_tools(language)
        mean, std = self._analyze_jaccard_similarity(language)
        left, right, common = self._compute_accuracy(language)
        return {
            'jaccard': {'mean': mean, 'std': std},
            'accuracy': {'left': left, 'right': right, 'common': common}
        }

    def _run_sbom_tools(self, language: LanguageSpec, repo_path: str = "/repo"):
        output_dir = os.path.join(self.target_dir, language.name)
        comparer = SBOMComparer(trivy=self.trivy, syft=self.syft, output_dir=output_dir)
        lock_files = []
        # os walk a folder
        for root, dirs, files in os.walk(os.path.join(repo_path, language.name)):
            if root[len(repo_path):].count(os.sep) > 3:
                continue
            for file in files:
                if self.mode == SBOMFileMode.project:
                    condition = (file == language.file_names[1] or (len(language.file_names) > 2 and file == language.file_names[2]))
                elif self.mode == SBOMFileMode.lock:
                    condition = (file == language.file_names[0])
                else:
                    raise ValueError("Invalid mode, Provided: {self.mode}, Expected: [project, lock]")
                if condition:
                    input_file = os.path.join(root, file)
                    lock_files.append(input_file)

        with Pool(processes=os.cpu_count()) as pool:
            with tqdm(total=len(lock_files)) as pbar:
                for left_only, right_only, common in pool.imap_unordered(comparer.compare, lock_files):
                    pbar.update()

    def _analyze_jaccard_similarity(self, language: LanguageSpec):
        jaccords = []
        output_folder = os.path.join(self.target_dir, language.name, "diff")
        for root, dirs, files in os.walk(output_folder):
            for file in files:
                if file.endswith(".json"):
                    with open(os.path.join(root, file)) as f:
                        data = json.load(f)
                        left = data["left"]
                        right = data["right"]
                        common = data["common"]
                        try:
                            jaccord = len(common) / (len(left) + len(right) + len(common))
                        except ZeroDivisionError:
                            jaccord = 1
                        if jaccord != 1:
                            print(file, jaccord)
                        jaccords.append(jaccord)
        return np.mean(jaccords), np.std(jaccords)

    def _compute_accuracy(self, language: LanguageSpec):
        left_len = []
        right_len = []
        common_len = []
        output_folder = os.path.join(self.target_dir, language.name, "diff")
        for root, dirs, files in os.walk(output_folder):
            for file in files:
                if file.endswith(".json"):
                    content = DataProcessor.load_json(os.path.join(root, file))
                    left = content["left"]
                    right = content["right"]
                    common = content["common"]
                    if not common:
                        continue
                    origin_file = content["input_file"]
                    ground_truth = parse_ground_truth(origin_file, language)
                    if language == LanguageSpec.ruby:
                        ground_truth = [{**pkg, "version": pkg["version"].split("-")[0]} if "-" in pkg["version"] else pkg for pkg in ground_truth]
                    common_df = SBOM(common)
                    ground_truth_df = SBOM(ground_truth)
                    left, right, common = analyze_difference(common_df, ground_truth_df)
                    left_len.append(len(left))
                    right_len.append(len(right))
                    common_len.append(len(common))
        return np.sum(left_len), np.sum(right_len), np.sum(common_len)

class GitHubAnalyzer:
    def __init__(self, token: str):
        self.token = token

    def download_files(self):
        """Download files"""
        for lang, url in awesome_dict.items():
            parser = MarkdownParser(url)
            crawler = GitHubCrawler(self.token, LanguageSpec[lang])
            all_result = crawler.fetch_all_urls(parser.url_list)
            crawler.save_urls(all_result)

    def download_repos(self):
        """Download repositories"""
        for lang, url in awesome_dict.items():
            parser = MarkdownParser(url)
            crawler = GitHubCrawler(self.token, LanguageSpec[lang])
            all_result = crawler.fetch_all_urls(parser.url_list)
            crawler.download_repos(all_result)

class DataProcessor:
    @staticmethod
    def load_json(file_path: str):
        with open(file_path) as f:
            return json.load(f)

    @staticmethod
    def javascript_fix(input_file: str, left: list, right: list, common: list):
        with open(input_file) as f:
            data = json.load(f)
        self_name: str = data["name"]
        left = [x for x in left if x["name"] != self_name]
        right = [x for x in right if x["name"] != self_name]
        common = [x for x in common if x["name"] != self_name]
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

def main():
    # Initialize analyzer
    sbom_standard = SBOMStandard.cyclonedx
    sbom_mode = SBOMFileMode.project
    
    # FIXME: Only find valid project file which can be used to generate a lock file
    
    analyzer = SBOMAnalyzer(target_dir="/sbom", standard=sbom_standard, mode=sbom_mode)
    
    # Clean target directory
    shutil.rmtree(analyzer.target_dir, ignore_errors=True)
    
    # Analyze for each language
    for language in LanguageSpec:
        results = analyzer.run_analysis(language)
        print(f"Language: {language.name}")
        print(f"Jaccard - Mean: {results['jaccard']['mean']}, Std: {results['jaccard']['std']}")
        print(f"Accuracy - Left: {results['accuracy']['left']}, "
              f"Right: {results['accuracy']['right']}, "
              f"Common: {results['accuracy']['common']}")

if __name__ == "__main__":
    main()