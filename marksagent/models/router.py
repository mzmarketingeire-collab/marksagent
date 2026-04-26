import os
from utils.config import Config
from models.base import BaseModel

class LLMRouter:
    """Routes requests to the appropriate model - prioritizes free models, mirrors Javi's approach"""
    
    # Priority: free models first, then paid
    MODEL_PRIORITY = [
        "gemma",      # Free (local Ollama)
        "gemini",     # Free tier
        "minimax",    # Free tier
        "openrouter", # Fallback - has free credits
    ]
    
    def __init__(self, models: list[BaseModel], spend_tracker):
        self.models = models
        self.spend_tracker = spend_tracker
        
        # Sort models by priority (free first)
        self.models.sort(key=lambda m: self._get_priority(m.name))
        
        print(f"🔀 Initialized router with {len(models)} models (priority: free first)")
        
        # System prompt that mirrors Javi's personality
        self.system_prompt = """You are a helpful, direct AI assistant. 

RULES:
- Be genuinely helpful, not performatively helpful
- Have opinions - you're allowed to disagree and prefer things
- Be resourceful before asking - try to figure it out yourself first
- Be careful with external actions (emails, posts) - ask first
- Remember what you're told - use that info when answering
- Listen to what the user tells you about their setup

STYLE:
- Concise when needed, thorough when it matters
- Not a corporate drone, not a sycophant
- Just help
- Skip the "Great question!" filler - just answer

Think step-by-step for complex problems. If you don't know something, say so but offer to help anyway."""
        
    def _get_priority(self, model_name: str) -> int:
        """Lower = higher priority (try first)"""
        return self.MODEL_PRIORITY.index(model_name) if model_name in self.MODEL_PRIORITY else 999
        
    async def route_request(self, mode: str, prompt: str, user_id: str = None) -> dict:
        """Route a request to the best available free model"""
        
        # Check budget first
        if not self.spend_tracker.can_spend():
            return {
                "success": False,
                "error": "Daily budget exhausted. Try again tomorrow."
            }
        
        # Build full prompt with system instructions
        full_prompt = f"{self.system_prompt}\n\n---\n\n{prompt}"
        
        # Try models in priority order (free first)
        for model in self.models:
            if not model.is_available():
                print(f"⏭️  Model {model.name} unavailable, skipping...")
                continue
                
            try:
                print(f"📤 Trying model: {model.name}")
                response = await model.generate(full_prompt, mode)
                
                if response["success"]:
                    # Track spend if applicable
                    cost = response.get("cost", 0)
                    self.spend_tracker.add_spend(cost)
                    print(f"✅ Success with {model.name}, cost: €{cost}")
                    return response
                    
            except Exception as e:
                print(f"❌ Model {model.name} failed: {e}")
                continue
        
        return {
            "success": False,
            "error": "All models failed. Please try again later."
        }