import os
import aiohttp

class GitHubService:
    """GitHub integration service"""
    
    def __init__(self, config):
        self.token = config.GITHUB_TOKEN
        self.repo = config.GITHUB_REPO
        
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    async def create_issue(self, title: str, body: str):
        """Create a GitHub issue"""
        if not self.token or not self.repo:
            print("⚠️  GitHub not configured")
            return None
            
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.github.com/repos/{self.repo}/issues"
                payload = {"title": title, "body": body}
                
                async with session.post(url, json=payload, headers=self._get_headers()) as resp:
                    if resp.status == 201:
                        data = await resp.json()
                        print(f"✅ Created GitHub issue: {data.get('html_url')}")
                        return data.get('html_url')
                    else:
                        print(f"❌ GitHub API error: {await resp.text()}")
                        return None
        except Exception as e:
            print(f"❌ Error creating issue: {e}")
            return None
    
    async def create_gist(self, filename: str, content: str, description: str = ""):
        """Create a GitHub gist"""
        if not self.token:
            return None
            
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.github.com/gists"
                payload = {
                    "description": description,
                    "public": False,
                    "files": {filename: {"content": content}}
                }
                
                async with session.post(url, json=payload, headers=self._get_headers()) as resp:
                    if resp.status == 201:
                        data = await resp.json()
                        print(f"✅ Created gist: {data.get('html_url')}")
                        return data.get('html_url')
                    else:
                        print(f"❌ GitHub Gist error: {await resp.text()}")
                        return None
        except Exception as e:
            print(f"❌ Error creating gist: {e}")
            return None