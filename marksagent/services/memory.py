import os
import aiohttp
from datetime import datetime

class MemoryService:
    def __init__(self, config):
        self.url = config.SUPABASE_URL
        self.key = config.SUPABASE_KEY
        self.context = {}
        
    def _get_headers(self):
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "Prefer": "return=representation"}
    
    async def load_context(self):
        if not self.url or not self.key:
            self.context = {}
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.url}/rest/v1/memory?order=created_at.desc&limit=20", headers=self._get_headers()) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data:
                            self.context[item.get("key", "")] = item.get("value", "")
        except:
            pass
    
    async def get_context(self):
        if not self.context:
            return "No previous context."
        lines = [f"- {k}: {v}" for k, v in list(self.context.items())[:10]]
        return "\n".join(lines)
    
    async def check_and_save(self, response_text, user_prompt):
        prompt_lower = user_prompt.lower()
        if any(kw in prompt_lower for kw in ["remember", "save this", "note this", "new business", "new client", "workflow", "process"]):
            await self.force_save(user_prompt)
    
    async def force_save(self, info):
        if not info or len(info) < 3:
            return
        key = f"memory_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self.context[key] = info
        if self.url and self.key:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {"key": key, "value": info, "created_at": datetime.utcnow().isoformat()}
                    async with session.post(f"{self.url}/rest/v1/memory", json=payload, headers=self._get_headers()) as resp:
                        pass
            except:
                pass
    
    async def remove(self, item):
        to_remove = [k for k, v in self.context.items() if item.lower() in v.lower()]
        for k in to_remove:
            del self.context[k]