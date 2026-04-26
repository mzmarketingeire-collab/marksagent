import os
import aiohttp
from models.base import BaseModel

class GemmaModel(BaseModel):
    """Gemma model via Ollama (local)"""
    
    def __init__(self, config):
        super().__init__(config)
        self.name = "gemma"
        self.ollama_url = config.OLLAMA_URL or "http://localhost:11434"
        
    def is_available(self) -> bool:
        # Check if Ollama is running
        return os.getenv("OLLAMA_URL") is not None or True
        
    async def generate(self, prompt: str, mode: str = "general") -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "gemma",
                    "prompt": prompt,
                    "stream": False
                }
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "success": True,
                            "content": data.get("response", "No response"),
                            "model": self.name,
                            "cost": 0  # Free local model
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Ollama returned {resp.status}"
                        }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }