import os
from utils.config import Config
from models.base import BaseModel

class LLMRouter:
    """Smart routing: free for chat, paid for reasoning only"""
    
    # Free models first, paid for reasoning
    REASONING_KEYWORDS = [
        "think", "reason", "analyze", "complex", "decision", "strategy",
        "plan", "evaluate", "assess", "compare", "improve", "debug",
        "architecture", "design", "logic", "solve", "break down"
    ]
    
    def __init__(self, models: list[BaseModel], spend_tracker):
        self.models = models
        self.spend_tracker = spend_tracker
        
        # Free models first (cheapest first)
        self.models.sort(key=lambda m: getattr(m, 'name', 'unknown'))
        
        print(f"🔀 Router: {len(models)} models (free first, €1/day budget)")
        
        self.system_prompt = """You are a helpful, direct AI assistant.

RULES:
- Be genuinely helpful, not performatively helpful
- Have opinions - you're allowed to disagree
- Be resourceful before asking
- Be careful with external actions - ask first
- Remember what you're told

STYLE:
- Concise when needed, thorough when it matters
- Skip filler - just answer
- Think step-by-step for complex problems"""
    
    def _needs_reasoning(self, prompt: str) -> bool:
        """Check if prompt needs complex reasoning"""
        p = prompt.lower()
        return any(k in p for k in self.REASONING_KEYWORDS)
    
    async def route_request(self, mode: str, prompt: str, user_id: str = None) -> dict:
        """Route to free models, use paid only for reasoning"""
        
        if not self.spend_tracker.can_spend():
            return {"success": False, "error": "Daily budget exhausted."}
        
        full_prompt = f"{self.system_prompt}\n\n---\n\n{prompt}"
        
        # Use paid model only for reasoning tasks
        if self._needs_reasoning(prompt) or mode in ["reasoning", "think"]:
            models = self.models
            print(f"🧠 Reasoning task - trying all models")
        else:
            models = self.models  # Free first anyway
        
        for model in models:
            if not model.is_available():
                continue
            try:
                response = await model.generate(full_prompt, mode)
                if response["success"]:
                    cost = response.get("cost", 0)
                    self.spend_tracker.add_spend(cost)
                    print(f"✅ {model.name} (€{cost:.4f})")
                    return response
            except Exception as e:
                print(f"❌ {model.name}: {e}")
                continue
        
        return {"success": False, "error": "All models failed."}