import os
import aiohttp
from models.base import BaseModel

class MiniMaxModel(BaseModel):
    """MiniMax API (free tier)"""
    
    def __init__(self, config):
        super().__init__(config)
        self.name = "minimax"
        self.api_key = config.MINIMAX_API_KEY
        self.base_url = "https://api.minimax.chat/v1"
        
    def is_available(self) -> bool:
        return bool(self.api_key)
        
    async def generate(self, prompt: str, mode: str = "general") -> dict:
        if not self.api_key:
            return {"success": False, "error": "MINIMAX_API_KEY not set"}
            
        try:
            url = f"{self.base_url}/text/chatcompletion_pro"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "MiniMax-Text-01",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        return {
                            "success": True,
                            "content": content,
                            "model": self.name,
                            "cost": 0  # Check MiniMax free tier
                        }
                    else:
                        error = await resp.text()
                        return {"success": False, "error": f"MiniMax API error: {error}"}
        except Exception as e:
            return {"success": False, "error": str(e)}