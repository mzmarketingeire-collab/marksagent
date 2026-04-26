import os
import aiohttp
from models.base import BaseModel

class OpenRouterModel(BaseModel):
    """OpenRouter (free credits)"""
    
    def __init__(self, config):
        super().__init__(config)
        self.name = "openrouter"
        self.api_key = config.OPENROUTER_API_KEY
        
    def is_available(self) -> bool:
        return bool(self.api_key)
        
    async def generate(self, prompt: str, mode: str = "general") -> dict:
        if not self.api_key:
            return {"success": False, "error": "OPENROUTER_API_KEY not set"}
            
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://marksagent.com",
                "X-Title": "MarksAgent"
            }
            
            payload = {
                "model": "google/gemini-2.0-flash-exp",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        # OpenRouter charges per token, calculate cost
                        usage = data.get("usage", {})
                        cost = (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)) * 0.000001  # Approximate
                        return {
                            "success": True,
                            "content": content,
                            "model": self.name,
                            "cost": cost
                        }
                    else:
                        error = await resp.text()
                        return {"success": False, "error": f"OpenRouter API error: {error}"}
        except Exception as e:
            return {"success": False, "error": str(e)}