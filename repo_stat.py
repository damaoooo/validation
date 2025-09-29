import os
from typing import Optional, List, Tuple
import typer
from rich.progress import Progress
from prettytable import PrettyTable
from utils import LanguageSpec, is_poetry_project

app = typer.Typer(help="Statistics for lockfile/projectfile distribution in repositories")

# Insert after app definition
@app.command()
def python_build_system_stat(
    root_dir: str = typer.Option(..., help="Python project root directory, structure: root_dir/python/author/repo_name")
) -> None:
    """
    Count the distribution of package managers for all Python repos: use identify_build_system when pyproject.toml exists, otherwise check setup.py and requirements.txt.
    """
    import toml
    lang_dir = os.path.join(root_dir, "python")
    if not os.path.exists(lang_dir):
        print("python directory not found")
        return
    author_dirs = [os.path.join(lang_dir, author) for author in os.listdir(lang_dir) if os.path.isdir(os.path.join(lang_dir, author))]
    repo_dirs: List[str] = []
    for author_dir in author_dirs:
        repo_dirs.extend([os.path.join(author_dir, repo) for repo in os.listdir(author_dir) if os.path.isdir(os.path.join(author_dir, repo))])

    stats = {}
    no_pyproject = 0
    setuptools_count = 0
    pip_count = 0
    for repo in repo_dirs:
        files = set(os.listdir(repo))
        if "pyproject.toml" in files:
            pyproject_path = os.path.join(repo, "pyproject.toml")
            try:
                toml_data = toml.load(pyproject_path)
                build_sys = identify_build_system(toml_data)
            except Exception:
                build_sys = "Invalid TOML"
            stats[build_sys] = stats.get(build_sys, 0) + 1
        else:
            no_pyproject += 1
            if "setup.py" in files:
                setuptools_count += 1
            elif "requirements.txt" in files:
                pip_count += 1

    table = PrettyTable(["Build System", "Count"])
    for k, v in stats.items():
        table.add_row([k, v])
    table.add_row(["Setuptools (no pyproject)", setuptools_count])
    table.add_row(["Pip (requirements.txt only)", pip_count])
    table.add_row(["Other (no pyproject/setup.py/requirements.txt)", no_pyproject - setuptools_count - pip_count])
    print(table)

def identify_build_system(toml_data):
    """
    Identify build system based on parsed TOML data.

    Args:
        toml_data (dict): Dictionary loaded from pyproject.toml file.

    Returns:
        str: Name of the build system, such as "Poetry", "Hatch", "Unknown", etc.
    """
    # 1. First check [build-system][build-backend] (most standard way)
    if "build-system" in toml_data and "build-backend" in toml_data["build-system"]:
        backend = toml_data["build-system"]["build-backend"]
        if "poetry.core.masonry.api" in backend:
            return "Poetry"
        if "hatchling.build" in backend:
            return "Hatch"
        if "pdm.backend" in backend:
            return "PDM"
        if "flit_core.buildapi" in backend:
            return "Flit"
        if "setuptools.build_meta" in backend:
            return "Setuptools"
        if "maturin" in backend:
            return "Maturin"
        # Can add other backend identification rules as needed
        return f"Unknown"

    # 2. If no build-backend, guess based on [tool.*] tables (non-standard but common)
    if "tool" in toml_data:
        if "poetry" in toml_data["tool"]:
            return "Poetry"
        if "hatch" in toml_data["tool"]:
            return "Hatch"
        if "pdm" in toml_data["tool"]:
            return "PDM"
        if "flit" in toml_data["tool"]:
            return "Flit"
        if "setuptools" in toml_data["tool"]:
            return "Setuptools"
 
    return "Not Specified"

@app.command()
def poetry_stat(
    root_dir: str = typer.Option(..., help="Python project root directory, structure: root_dir/python/author/repo_name")
) -> None:
    """
    Count all Python projects: number with pyproject.toml, number of poetry projects, and pyproject/lock distribution under poetry projects.
    """
    lang_dir = os.path.join(root_dir, "python")
    if not os.path.exists(lang_dir):
        print("Python directory not found")
        return
    author_dirs = [os.path.join(lang_dir, author) for author in os.listdir(lang_dir) if os.path.isdir(os.path.join(lang_dir, author))]
    repo_dirs: List[str] = []
    for author_dir in author_dirs:
        repo_dirs.extend([os.path.join(author_dir, repo) for repo in os.listdir(author_dir) if os.path.isdir(os.path.join(author_dir, repo))])

    pyproject_count = 0
    poetry_count = 0
    poetry_proj_only = 0
    poetry_lock_only = 0
    poetry_both = 0
    poetry_neither = 0
    for repo in repo_dirs:
        files = set(os.listdir(repo))
        has_pyproject = "pyproject.toml" in files
        has_lock = "poetry.lock" in files
        if has_pyproject:
            pyproject_count += 1
            pyproject_path = os.path.join(repo, "pyproject.toml")
            if is_poetry_project(pyproject_path):
                poetry_count += 1
                if has_pyproject and has_lock:
                    poetry_both += 1
                elif has_pyproject:
                    poetry_proj_only += 1
                elif has_lock:
                    poetry_lock_only += 1
                else:
                    poetry_neither += 1

    table = PrettyTable(["Item", "Count"])
    table.add_row(["Projects with pyproject.toml", pyproject_count])
    table.add_row(["Poetry projects", poetry_count])
    table.add_row(["Poetry: only pyproject.toml", poetry_proj_only])
    table.add_row(["Poetry: only poetry.lock", poetry_lock_only])
    table.add_row(["Poetry: both present", poetry_both])
    table.add_row(["Poetry: neither present", poetry_neither])
    print(table)



def get_language_choices() -> List[str]:
    """Get list of all supported language names"""
    return [lang.name for lang in LanguageSpec]

@app.command()
def stat(
    root_dir: str = typer.Option(..., help="Root directory containing multiple repos, structure: root_dir/language/author/repo_name"),
    language: Optional[str] = typer.Option(
        None,
        help=f"Specify language, only count that language. Supported: {', '.join([lang.name for lang in LanguageSpec])}",
        case_sensitive=False,
        show_choices=True,
        rich_help_panel="Language Options"
    ),
) -> None:
    """
    Count lockfile/projectfile distribution for repos of each language in specified directory.
    :param root_dir: Root directory containing languages/authors/projects
    :param language: Optional, specify language to count only that language
    """
    langs: List[LanguageSpec] = [LanguageSpec[language.lower()]] if language else list(LanguageSpec)
    table = PrettyTable(["Language", "Project File Only", "Lock File Only", "Both", "Neither", "Total"])
    results: List[Tuple[str, int, int, int, int, int]] = []
    with Progress() as progress:
        task = progress.add_task("Counting...", total=len(langs))
        for lang in langs:
            lock_file, proj_file = lang.file_names[:2]
            if language:
                lang_dir = os.path.join(root_dir, lang.name)
                author_dirs = [os.path.join(lang_dir, author) for author in os.listdir(lang_dir) if os.path.isdir(os.path.join(lang_dir, author))] if os.path.exists(lang_dir) else []
            else:
                lang_dir = os.path.join(root_dir, lang.name)
                if not os.path.exists(lang_dir):
                    results.append((lang.name, 0, 0, 0, 0, 0))
                    progress.update(task, advance=1)
                    continue
                author_dirs = [os.path.join(lang_dir, author) for author in os.listdir(lang_dir) if os.path.isdir(os.path.join(lang_dir, author))]
            repo_dirs: List[str] = []
            for author_dir in author_dirs:
                repo_dirs.extend([os.path.join(author_dir, repo) for repo in os.listdir(author_dir) if os.path.isdir(os.path.join(author_dir, repo))])
            proj_only: int = 0
            lock_only: int = 0
            both: int = 0
            neither: int = 0
            for repo in repo_dirs:
                files = set(os.listdir(repo))
                has_proj: bool = proj_file in files
                has_lock: bool = lock_file in files
                if has_proj and has_lock:
                    both += 1
                elif has_proj:
                    proj_only += 1
                elif has_lock:
                    lock_only += 1
                else:
                    neither += 1
            total: int = len(repo_dirs)
            results.append((lang.name, proj_only, lock_only, both, neither, total))
            progress.update(task, advance=1)
    for row in results:
        table.add_row(row)
    print(table)

if __name__ == "__main__":
    app()
