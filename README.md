# 🛡️ SBOM Validation & Analysis Toolkit

A comprehensive toolkit for Software Bill of Materials (SBOM) generation, analysis, and vulnerability scanning across multiple programming languages and package managers. The vulnerability report can be seen in [here](./vulnerability_report.md)

## 📋 Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Core Components](#core-components)
- [Usage Examples](#usage-examples)
- [Dependencies](#dependencies)

## 🎯 Overview

This toolkit provides a complete suite of tools for:
- 🕷️ **Repository Crawling**: GitHub repository discovery and cloning
- 🔒 **Lock File Generation**: Automated dependency lock file creation
- 📊 **SBOM Analysis**: Comparative analysis between different SBOM tools
- 🔍 **Vulnerability Scanning**: Security analysis of software dependencies
- 📈 **Statistics & Reporting**: Comprehensive project statistics and insights

## 🚀 Installation

```bash
# Clone the repository
git clone <this-repo-url>
cd validation

# Install dependencies
pip install -r requirements.txt
```

## 🧩 Core Components

### 🕷️ `crawler.py` - GitHub Repository Crawler
Downloads repositories from awesome lists and extracts specific files.

**Usage:**
```bash
# Download all repositories from all languages
python crawler.py --language all

# Download only Python repositories
python crawler.py --language python --save_dir ./my_repos

# Download project files only (not full repos)
python crawler.py --language rust --file_mode
```

**Key Features:**
- Supports 6 languages: Python, Rust, JavaScript, Ruby, PHP, Go
- Async downloading for better performance
- Selective file extraction mode

---

### 🏗️ `main.py` - SBOM Analysis Engine
Core analysis engine that orchestrates SBOM generation and comparison.

**Usage:**
```bash
# Run complete SBOM analysis for Python projects
python main.py --language python --standard cyclonedx --mode lock

# Analyze project files instead of lock files
python main.py --language javascript --mode project
```

**Capabilities:**
- Jaccard similarity analysis
- Accuracy computation
- Multi-tool SBOM comparison

---

### 📦 `sbom.py` - SBOM Tools Interface
Provides interfaces for Syft and Trivy SBOM generation tools.

**Usage (programmatic):**
```python
from sbom import SBOMComparer, Trivy, Syft
from utils import SBOMStandard

# Initialize tools
trivy = Trivy(standard=SBOMStandard.cyclonedx)
syft = Syft(standard=SBOMStandard.spdx)

# Compare SBOMs
comparer = SBOMComparer(trivy=trivy, syft=syft, output_dir="./output")
comparer.run_comparison("path/to/project")
```

---

### 🔒 `lock_generate.py` - Lock File Generator
Generates dependency lock files for various package managers.

**Usage:**
```bash
# Generate lock files for Python projects using typer CLI
python -m typer lock_generate.py run --language python --directory /path/to/projects

# Or use as a module
python lock_generate.py
```

**Supported Package Managers:**
- 🐍 **Python**: Poetry, pip-tools, pipenv
- 🦀 **Rust**: Cargo
- 📦 **JavaScript**: npm, yarn
- 💎 **Ruby**: Bundler
- 🐘 **PHP**: Composer
- 🐹 **Go**: Go modules

---

### 🛡️ `vulnerability_scan.py` - Security Scanner
Performs vulnerability scanning on SBOM files.

**Usage:**
```bash
# Scan with Grype
python vulnerability_scan.py scan --scanner grype --input /path/to/sbom --output /path/to/results

# Scan with Trivy
python vulnerability_scan.py scan --scanner trivy --input /path/to/sbom --output /path/to/results
```

**Supported Scanners:**
- 🔍 **Grype**: Anchore's vulnerability scanner
- 🛡️ **Trivy**: Aqua Security's scanner

---

### 📊 `repo_stat.py` - Repository Statistics
Analyzes repository characteristics and package manager usage.

**Usage:**
```bash
# Analyze Python build systems
python repo_stat.py python-build-system-stat --root-dir /path/to/repos

# General repository statistics
python repo_stat.py general-stats --root-dir /path/to/repos
```

**Analysis Types:**
- Build system distribution
- Lock file vs project file statistics
- Package manager usage patterns

---

### 🔍 `find_poetry.py` - Poetry Project Finder
Locates Poetry-based Python projects in directory structures.

**Usage:**
```bash
# Find all Poetry projects
python find_poetry.py find /path/to/scan

# With custom root directory
python find_poetry.py find --root-dir /data/projects
```

---

### 📝 `markdown.py` - Markdown Parser
Extracts GitHub repository URLs from markdown files (like awesome lists).

**Usage (programmatic):**
```python
from markdown import MarkdownParser

parser = MarkdownParser("https://raw.githubusercontent.com/vinta/awesome-python/master/README.md")
github_urls = parser.url_list
```

---

### 🔧 `utils.py` - Utility Functions
Core utilities and language specifications.

**Key Components:**
- `LanguageSpec`: Enum defining supported languages and file patterns
- `SBOMStandard`: SBOM format specifications
- Helper functions for project detection

---

### 🔗 `link_removal.py` - Symlink Replacer
Replaces symbolic links with actual file copies.

**Usage:**
```bash
# Replace symlinks in a directory
python link_removal.py /path/to/directory
```

---

### ⚡ `query_limit.py` - GitHub API Monitor
Monitors GitHub API rate limits.

**Usage:**
```bash
# Check current rate limit status
python query_limit.py
```

---

### 🧪 `test.py` - File Copy Utility
Utility script for copying specific files (like package-lock.json).

**Usage:**
```bash
# Copy package-lock.json files
python test.py
```

## 📊 Usage Examples

### Complete Workflow Example

```bash
# 1. Download repositories
python crawler.py --language python --save_dir ./repos

# 2. Generate lock files
python lock_generate.py --directory ./repos/python

# 3. Run SBOM analysis
python main.py --language python --sbom_dir ./sboms --input_dir ./repos

# 4. Scan for vulnerabilities
python vulnerability_scan.py scan --scanner grype --input ./sboms --output ./scan_results

# 5. Generate statistics
python repo_stat.py python-build-system-stat --root-dir ./repos
```

### Quick Analysis Pipeline

```bash
# Check GitHub API limits
python query_limit.py

# Find Poetry projects
python find_poetry.py find ./repos

# Analyze specific language
python main.py --language rust --mode lock
```

## 📦 Dependencies

- **rich**: Enhanced terminal formatting and progress bars
- **prettytable**: Table formatting for statistics
- **requests**: HTTP client for API calls
- **pandas**: Data analysis and manipulation
- **tqdm**: Progress bars
- **aiohttp**: Async HTTP client
- **gitpython**: Git repository operations
- **numpy**: Numerical computations
- **typer**: Modern CLI framework

## 🏗️ Architecture

```
validation/
├── 🕷️ crawler.py          # Repository discovery & download
├── 🏗️ main.py             # Core analysis orchestration
├── 📦 sbom.py             # SBOM generation tools
├── 🔒 lock_generate.py    # Lock file generation
├── 🛡️ vulnerability_scan.py # Security scanning
├── 📊 repo_stat.py        # Statistics generation
├── 🔍 find_poetry.py      # Poetry project finder
├── 📝 markdown.py         # Markdown parsing
├── 🔧 utils.py            # Core utilities
├── 🔗 link_removal.py     # Symlink management
├── ⚡ query_limit.py      # API monitoring
└── 🧪 test.py             # Utility scripts
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

