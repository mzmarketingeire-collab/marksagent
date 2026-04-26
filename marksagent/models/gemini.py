import os
import aiohttp
from models.base import BaseModel

class GeminiModel(BaseModel):
    """Gemini via Google AI Studio (free tier)"""
    
    def __init__(self, config):
        super().__init__(config)
        self.name = "gemini"
        self.api_key = config.GEMINI_API_KEY
        
    def is_available(self) -> bool:
        return bool(self.api_key)
        
    async def generate(self, prompt: str, mode: str = "general") -> dict:
        if not self.api_key:
            return {"success": False, "error": "GEMINI_API_KEY not set"}
            
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": 2048
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        return {
                            "success": True,
                            "content": content,
                            "model": self.name,
                            "cost": 0  # Free tier
                        }
                    else:
                        error = await resp.text()
                        return {"success": False, "error": f"Gemini API error: {error}"}
        except Exception as e:
            return {"success": False, "error": str(e)}