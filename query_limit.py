import requests
import datetime
from utils import get_git_token

def get_rate_limit_status(token=None):
    url = "https://api.github.com/rate_limit"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        ret = response.json()
        used = ret["resources"]["core"]["used"]
        limit = ret["resources"]["core"]["limit"]
        remaining = ret["resources"]["core"]["remaining"]
        reset = ret["resources"]["core"]["reset"]
        reset_time = datetime.datetime.fromtimestamp(reset)
        print(f"used: {used}, limit: {limit}, remaining: {remaining}, reset: {reset_time}")
    else:
        raise Exception(f"Failed to fetch rate limit status: {response.status_code}")

# Example usage
if __name__ == "__main__":
    # If you have a GitHub personal access token, replace it in the string below
    token = get_git_token()
    get_rate_limit_status(token)

