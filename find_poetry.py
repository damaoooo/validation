import os
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

# Create a Typer application instance and a Rich console instance
app = typer.Typer()
console = Console()

def get_total_repos(root_dir: str) -> int:
    """Pre-scan to get the total number of repo directories for progress bar."""
    total = 0
    # We only care about the count of third-level directories (repo)
    # root/lang/author/repo
    for lang in os.scandir(root_dir):
        if lang.is_dir():
            for author in os.scandir(lang.path):
                if author.is_dir():
                    for repo in os.scandir(author.path):
                        if repo.is_dir():
                            total += 1
    return total

@app.command()
def find(
    root_dir: str = typer.Argument(
        "/data/sbom",
        help="Root directory to scan, structure should be 'root/language/author/repo'.",
        exists=True,      # Ensure path exists
        file_okay=False,  # Don't accept file paths
        dir_okay=True,    # Only accept directory paths
        readable=True,    # Ensure directory is readable
        resolve_path=True # Convert path to absolute path
    ),
):
    """
    Scan specified directory structure to find paths containing poetry.lock files in the first-level subdirectories of repo directories.
    """
    console.print(f"[bold cyan]Starting to scan directory: {root_dir}[/bold cyan]")

    try:
        # Pre-calculate total number of repos to initialize progress bar
        total_repos = get_total_repos(root_dir)
        if total_repos == 0:
            console.print("[yellow]Warning: No three-level directories with 'language/author/repo' structure found in the specified path.[/yellow]")
            return

        found_paths = []

        # Use rich.progress to create progress bar context
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("[green]Scanning Repos...", total=total_repos)

            # Traverse three-level directory structure
            for lang_entry in os.scandir(root_dir):
                if not lang_entry.is_dir():
                    continue
                for author_entry in os.scandir(lang_entry.path):
                    if not author_entry.is_dir():
                        continue
                    for repo_entry in os.scandir(author_entry.path):
                        if not repo_entry.is_dir():
                            continue
                        
                        # Search for subdirectories containing poetry.lock in the first level of the repo directory
                        for subdir_entry in os.scandir(repo_entry.path):
                            if subdir_entry.is_dir():
                                lockfile_path = os.path.join(subdir_entry.path, 'poetry.lock')
                                if os.path.isfile(lockfile_path):
                                    found_paths.append(subdir_entry.path)
                        
                        # After processing each repo directory, advance progress bar by one step
                        progress.update(task, advance=1)

        # After scanning, print results
        console.print("\n" + "="*50)
        if found_paths:
            console.print("[bold green]✅ Scan completed! Found the following folder paths containing 'poetry.lock':[/bold green]")
            for path in sorted(found_paths): # Sort results to make them more readable
                console.print(f"  [cyan]- {path}[/cyan]")
        else:
            console.print("[bold yellow]ℹ️ Scan completed! No folders containing 'poetry.lock' found in the specified path.[/bold yellow]")

    except PermissionError:
        console.print(f"[bold red]Error: Insufficient permissions to read some content of directory '{root_dir}'.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]An unknown error occurred: {e}[/bold red]")


if __name__ == "__main__":
    app()