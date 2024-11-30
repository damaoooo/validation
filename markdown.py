import requests
import re

class MarkdownParser:
    def __init__(self, webpage: str):
        self.webpage = webpage
        self.content = self._get_content()
        self.url_list = self.parse(self.content)
        
    def _get_content(self):
        response = requests.get(self.webpage)
        if response.status_code != 200:
            print(f"Error fetching {self.webpage}: {response.status_code}")
            return ""
        return response.text

    def parse(self, markdown: str) -> list[str]:
        # parse the markdown content
        # return a list of URLs
        result = []
        
        def is_github_repository(url):
            # Match Github Repository URL
            repo_pattern = r'^https://github\.com/[^/]+/[^/]+/?$'
            return bool(re.match(repo_pattern, url))
        

        pattern = r'\[\s*.*?\s*\]\(\s*(https://github\.com[^\s\)]+)\s*\)'
        matches = re.findall(pattern, markdown)
        return [url for url in matches if is_github_repository(url)]