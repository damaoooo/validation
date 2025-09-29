import os
import json
import pandas as pd
from dataclasses import dataclass
from typing import List, Tuple, Union
import subprocess
import re
import traceback 
from utils import SBOMStandard

def remove_node_modules_prefix(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    if 'packages' in data:
        packages = data['packages']
        updated_packages = {}
        for key, value in packages.items():
            new_key = key.replace('node_modules/', '', 1) if key.startswith('node_modules/') else key
            updated_packages[new_key] = value
        data['packages'] = updated_packages
        # not remove, but add the new key
        # data['packages'] = {**packages, **updated_packages}

        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    

@dataclass
class Package:
    """Represents a software package with name and version."""
    name: str
    version: str

    def __str__(self):
        return f"{self.name}=={self.version}"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if isinstance(other, Package):
            return self.name == other.name and self.version == other.version
        return False
    


class SBOM:
    """Represents a Software Bill of Materials (SBOM)."""

    def __init__(self, packages: Union[List[Package], List[dict]]):
        self.packages = packages

        if isinstance(self.packages, list) and all(isinstance(p, dict) for p in self.packages):
            self.packages = [Package(**p) for p in self.packages]

    def to_dataframe(self) -> pd.DataFrame:
        """Converts the SBOM packages to a pandas DataFrame."""
        df = pd.DataFrame([vars(p) for p in self.packages])
        return df.drop_duplicates()

    def __len__(self):
        return len(self.packages)

    def __str__(self):
        return "\n".join(str(p) for p in self.packages)
    
    def to_dict(self):
        return [vars(p) for p in self.packages]


class SBOMTool:
    def __init__(self, name: str, binary_path: str, standard: SBOMStandard = SBOMStandard.cyclonedx):
        self.name = name
        self.standard = standard
        self.binary_path = binary_path
        
    def run(self, input_path: str, output_path: str):
        raise NotImplementedError("Subclasses must implement this method.")


class Trivy(SBOMTool):
    def __init__(self, standard: SBOMStandard = SBOMStandard.cyclonedx):
        super().__init__("Trivy", "trivy", standard)

    def run(self, input_path: str, output_path: str):
        # "/root/workspace/trivy/cmd/trivy/trivy"

        match self.standard:
            case SBOMStandard.spdx:
                format_string = "spdx-json"
            case SBOMStandard.cyclonedx:
                format_string = "cyclonedx"
            case _:
                raise ValueError(f"Unsupported standard: {self.standard}")

        cmd = [self.binary_path, "fs", "--format", format_string, "--output", output_path, input_path, "-q"]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running Trivy: {e.stderr} for {input_path}")
            


class Syft(SBOMTool):
    def __init__(self, standard: SBOMStandard = SBOMStandard.cyclonedx):
        super().__init__("Syft", "syft", standard)

    def run(self, input_path: str, output_path: str):
        match self.standard:
            case SBOMStandard.spdx:
                format_string = "spdx-json"
            case SBOMStandard.cyclonedx:
                format_string = "cyclonedx-json"
            case _:
                raise ValueError(f"Unsupported standard: {self.standard}")

        cmd = [self.binary_path, "scan", input_path, "-o", f"{format_string}={output_path}", "-q"]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running Syft: {e.stderr} for {input_path}")


def parse_cyclonedx(file_path: str) -> SBOM:
    """Parses a CycloneDX JSON file into an SBOM."""

    language_folder_name = os.path.basename(os.path.dirname(os.path.dirname(file_path))).lower()
    
    with open(file_path, "r") as f:
        data: dict = json.load(f)

    packages = []
    for component in data.get("components", []):
        if "name" in component and "version" in component:
            name = component["name"].strip()

            if "javascript" == language_folder_name:
                continue
            
            version = component["version"].strip()
            if "-" in version and "ruby" == language_folder_name:
                version = version[:version.index("-")]
                
            packages.append(Package(name, version))
    return SBOM(packages)


def parse_spdx(file_path: str) -> SBOM:
    """Parses a SPDX JSON file into an SBOM."""
    with open(file_path, "r") as f:
        data: dict = json.load(f)

    language_folder_name = os.path.basename(os.path.dirname(os.path.dirname(file_path))).lower()

    packages = []
    for package in data.get("packages", []):
        name = package.get("name", "").strip()
        version = package.get("versionInfo", "").strip()

        if "javascript" == language_folder_name:
            continue

        if "-" in version and "ruby" == language_folder_name:
            version = version[:version.index("-")]

        if "rust" == language_folder_name and name.endswith("Cargo.lock"):
            continue

        if "python" == language_folder_name and name.endswith("poetry.lock"):
            continue

        if "ruby" == language_folder_name and (name.endswith("Gemfile.lock") or re.match(r".*Gemfile\.\d+-\d+\.lock$", name)):
            continue

        if "php" == language_folder_name and name.endswith("composer.lock"):
            continue

        packages.append(Package(name, version))
    return SBOM(packages)
    


def analyze_difference(
        sbom1: SBOM, sbom2: SBOM
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compares two SBOMs and returns their differences."""
    df1 = sbom1.to_dataframe()
    df2 = sbom2.to_dataframe()

    # Find the common columns
    common_columns = df1.columns.intersection(df2.columns).tolist()

    # if df1 is empty and df2 is also empty, return empty dataframes
    if df1.empty and df2.empty:
        return df1, df2, pd.DataFrame(columns=common_columns)
    
    if df1.empty or df2.empty:
        return df1, df2, pd.DataFrame(columns=common_columns)
    
    # Perform outer merge with indicator
    df_all = pd.merge(df1, df2, on=common_columns, how="outer", indicator=True)

    left_only = df_all[df_all["_merge"] == "left_only"].drop(columns="_merge")
    right_only = df_all[df_all["_merge"] == "right_only"].drop(columns="_merge")
    common = df_all[df_all["_merge"] == "both"].drop(columns="_merge")

    return left_only, right_only, common

def format_json(input_path: str, output_path: str = None, indent: int = 4):
    """
    Reads a JSON file, formats it with indentation, and saves to a new file.

    Args:
        input_path (str): Path to the input JSON file.
        output_path (str): Path to the output JSON file.
        indent (int): Number of spaces for indentation. Default is 4.
    """

    if output_path is None:
        output_path = input_path

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    
    # print(f"Formatted JSON saved to: {output_path}")


class SBOMComparer:
    """Handles the process of generating, parsing, and comparing SBOMs."""

    def __init__(self, trivy: SBOMTool, syft: SBOMTool, output_dir: str = "./tmp",):
        self.output_dir = output_dir
        self.trivy = trivy
        self.syft = syft

        # Ensure output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # output_dir/raw for SBOM direct result
        raw_dir = os.path.join(output_dir, "raw")
        if not os.path.exists(raw_dir):
            os.makedirs(raw_dir, exist_ok=True)

        # output_dir/diff for SBOM comparison result
        diff_dir = os.path.join(output_dir, "diff")
        if not os.path.exists(diff_dir):
            os.makedirs(diff_dir, exist_ok=True)

        self.raw_path = raw_dir
        self.diff_path = diff_dir

    def compare(self, input_file: str, repo_path: str = "/data/sbom", save=True) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Main entry point for comparing SBOMs. This will:
        - Run Trivy and Syft
        - Parse their outputs
        - Compare the resulting SBOMs

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]: Trivy-only, Syft-only, and common packages.
        """
        # if it is a symbolic link, get the real path
        if os.path.islink(input_file):
            input_file = os.path.realpath(input_file)
            
        def extract_first_level_directory(path, base=repo_path):
            # Get relative path
            relative_path = os.path.relpath(path, base)
            # Split path into directory levels
            parts = relative_path.split(os.sep)
            # Return first level directory name
            return parts[0] if parts else None
        
        language = extract_first_level_directory(input_file)
        # if language == "javascript":
        #     remove_node_modules_prefix(input_file)
        
        # get the absolute path of the input file
        input_file = os.path.abspath(input_file)

        trivy_output_json = "trivy" + input_file.replace("/", "_") + ".json"
        syft_output_json = "syft" + input_file.replace("/", "_") + ".json"

        trivy_output_json_path = os.path.join(self.raw_path, trivy_output_json)
        syft_output_json_path = os.path.join(self.raw_path, syft_output_json)

        self.trivy.run(input_file, trivy_output_json_path)
        self.syft.run(input_file, syft_output_json_path)

        # Parse SBOMs
        if self.trivy.standard == SBOMStandard.cyclonedx:   
            trivy_sbom: SBOM = parse_cyclonedx(trivy_output_json_path)
        elif self.trivy.standard == SBOMStandard.spdx:
            trivy_sbom: SBOM = parse_spdx(trivy_output_json_path)

        if self.syft.standard == SBOMStandard.cyclonedx:
            syft_sbom: SBOM = parse_cyclonedx(syft_output_json_path)
        elif self.syft.standard == SBOMStandard.spdx:
            syft_sbom: SBOM = parse_spdx(syft_output_json_path)

        # Compare SBOMs
        try:
            left, right, common = analyze_difference(trivy_sbom, syft_sbom)
        except Exception as e:
            print(f"Error comparing SBOMs: {e}, for {input_file}")
            traceback.print_exc()
            return None, None, None

        def pandas_save_json(df: pd.DataFrame):
            # save the result as {"left": [], "right": [], "common": []}
            # convert the dataframe to list of dict
            result = df.to_dict(orient="records")
            return result
        
        if save:
            full_json = {
                "left": pandas_save_json(left),
                "right": pandas_save_json(right),
                "common": pandas_save_json(common),
                f"{self.trivy.name}": trivy_sbom.to_dict(),
                f"{self.syft.name}": syft_sbom.to_dict(),
                "input_file": input_file
            }
            with open(os.path.join(self.diff_path, f"{input_file.replace('/', '_')}.json"), "w") as f:
                json.dump(full_json, f, indent=4)

            # format the json
            format_json(trivy_output_json_path)
            format_json(syft_output_json_path)

        else:
            # remove the temporary files
            os.remove(trivy_output_json)
            os.remove(syft_output_json)

        return left, right, common



if __name__ == "__main__":
    standard = SBOMStandard.spdx
    trivy = Trivy(standard=standard)
    syft = Syft(standard=standard)
    comparer = SBOMComparer(trivy=trivy, syft=syft)
    left_only, right_only, common = comparer.compare(input_file="./example/Cargo.lock", save=True)

    print("Trivy-only packages:")
    print(left_only)

    print("\nSyft-only packages:")
    print(right_only)

    print("\nCommon packages:")
    print(common)