import json
from pathlib import Path
from typing import Dict

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(rich_markup_mode="rich")
console = Console()

# 定义语言与对应的锁文件名映射
# 你可以根据实际生成文件的习惯在这里增删
LANGUAGE_LOCK_MAP: Dict[str, str] = {
    "rust": "Cargo.lock",
    "python": "poetry.lock",  # 或者 requirements.txt
    "ruby": "Gemfile.lock",
    "php": "composer.lock",
    "nodejs": "package-lock.json",
    "go": "go.sum",
    "java": "pom.xml" # 或者 build.gradle
}

@app.command()
def scan(
    language: str = typer.Argument(..., help="编程语言 (如: rust, python, ruby, php)"),
    repo_full_name: str = typer.Argument(..., help="格式为 '作者/仓库名' (如: sagiegurari/duckscript)"),
    base_dir: str = typer.Option("/home/damaoooo/sbom", help="SBOM 文件存放的基础根目录")
):
    """
    🚀 动态识别语言并解析 Grype 漏洞扫描 JSON 文件
    """
    
    # 1. 处理 author 和 repo_name
    if "/" not in repo_full_name:
        console.print("[bold red]错误:[/bold red] repo_full_name 格式必须是 'author/repo_name'")
        raise typer.Exit(code=1)
    
    author, repo_name = repo_full_name.split("/", 1)
    lang_lower = language.lower()

    # 2. 根据语言获取对应的锁文件名
    lock_file = LANGUAGE_LOCK_MAP.get(lang_lower)
    if not lock_file:
        # 如果找不到映射，尝试直接用语言名兜底，或者报错
        console.print(f"[yellow]提示:[/yellow] 未配置语言 '{language}' 的默认锁文件，将尝试使用 '{language}.lock'")
        lock_file = f"{language}.lock"

    # 3. 拼接动态路径
    # 路径规则: {base_dir}/{language}/vuln/syft_data_sbom_{language}_{author}_{repo_name}_{lock_file}.json_Grype_vuln.json
    filename = f"syft_data_sbom_{lang_lower}_{author}_{repo_name}_{lock_file}.json_Grype_vuln.json"
    file_path = Path(base_dir) / lang_lower / "vuln" / filename

    if not file_path.exists():
        console.print(f"[bold red]错误: 找不到文件[/bold red]")
        console.print(f"预期路径: [yellow]{file_path}[/yellow]")
        raise typer.Exit(code=1)

    # 4. 解析并打印
    _render_table(file_path, author, repo_name, lang_lower)

def _render_table(file_path: Path, author: str, repo_name: str, language: str):
    """内部函数：负责读取 JSON 并渲染 Rich Table"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        matches = data.get("matches", [])
        
        table = Table(
            title=f"🛡️  [bold white]漏洞报告[/bold white] | {author}/{repo_name} | [bold cyan]{language.upper()}[/bold cyan]",
            caption=f"Source: {file_path.name}",
            header_style="bold magenta",
            border_style="dim"
        )
        
        table.add_column("CVE ID", style="cyan", no_wrap=True)
        table.add_column("Artifact", style="green")
        table.add_column("Version", style="blue")
        table.add_column("Severity", justify="center")
        table.add_column("Fix State", style="italic")

        for match in matches:
            v = match.get('vulnerability', {})
            a = match.get('artifact', {})
            
            severity = v.get('severity', 'Unknown')
            # 颜色映射
            color = {"Critical": "bold red", "High": "red", "Medium": "yellow", "Low": "blue"}.get(severity, "white")

            table.add_row(
                v.get('id', 'N/A'),
                a.get('name', 'N/A'),
                a.get('version', 'N/A'),
                f"[{color}]{severity}[/{color}]",
                v.get('fix', {}).get('state', 'not-fixed')
            )

        console.print(table)
        console.print(f"\n[bold green]✅ 完成![/bold green] 路径下共解析到 [bold cyan]{len(matches)}[/bold cyan] 个漏洞项。")

    except Exception as e:
        console.print(f"[bold red]解析失败:[/bold red] {e}")

if __name__ == "__main__":
    app()