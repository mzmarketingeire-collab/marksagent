import os
from utils.config import Config
from models.base import BaseModel

class LLMRouter:
    """Routes requests to the appropriate model based on budget and availability"""
    
    def __init__(self, models: list[BaseModel], spend_tracker):
        self.models = models
        self.spend_tracker = spend_tracker
        print(f"🔀 Initialized router with {len(models)} models")
        
    async def route_request(self, mode: str, prompt: str, user_id: str = None) -> dict:
        """Route a request to the best available model"""
        
        # Check budget first
        if not self.spend_tracker.can_spend():
            return {
                "success": False,
                "error": "Daily budget exhausted. Try again tomorrow."
            }
        
        # Try models in priority order (cheapest first)
        for model in self.models:
            if not model.is_available():
                print(f"⏭️  Model {model.name} unavailable, skipping...")
                continue
                
            try:
                print(f"📤 Trying model: {model.name}")
                response = await model.generate(prompt, mode)
                
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