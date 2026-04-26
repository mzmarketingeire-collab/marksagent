import os
from utils.config import Config
from models.base import BaseModel

class LLMRouter:
    """Routes requests intelligently - free for chat, paid for complex reasoning"""
    
    # Priority: free models first, then paid
    MODEL_PRIORITY = [
        "gemma",      # Free (local Ollama)
        "gemini",     # Free tier (fast, capable)
        "minimax",    # Free tier
        "openrouter", # Paid - use only for reasoning
    ]
    
    # Keywords that trigger paid/paid reasoning
    REASONING_TRIGGERS = [
        "think", "reason", "analyze", "complex", "decision", "strategy",
        "plan", "evaluate", "assess", "compare", "improve", "debug",
        "architecture", "design", "logic", "solve", "break down"
    ]
    
    def __init__(self, models: list[BaseModel], spend_tracker):
        self.models = models
        self.spend_tracker = spend_tracker
        
        # Sort models by priority (free first)
        self.models.sort(key=lambda m: self._get_priority(m.name))
        
        print(f"🔀 Router initialized: {len(models)} models (free first, paid for reasoning)")
        
        # System prompt - mirrors Javi's personality
        self.system_prompt = """You are a helpful, direct AI assistant.

RULES:
- Be genuinely helpful, not performatively helpful
- Have opinions - you're allowed to disagree and prefer things
- Be resourceful before asking - try to figure it out yourself first
- Be careful with external actions - ask first
- Remember what you're told
- Listen to what the user tells you about their setup

STYLE:
- Concise when needed, thorough when it matters
- Not a corporate drone, not a sycophant
- Skip filler like "Great question!" - just answer
- Think step-by-step for complex problems

If you don't know something, say so but offer to help anyway."""
        
    def _get_priority(self, model_name: str) -> int:
        """Lower = higher priority"""
        return self.MODEL_PRIORITY.index(model_name) if model_name in self.MODEL_PRIORITY else 999
    
    def _needs_reasoning(self, prompt: str) -> bool:
        """Check if the prompt needs complex reasoning (triggers paid model)"""
        prompt_lower = prompt.lower()
        return any(trigger in prompt_lower for trigger in self.REASONING_TRIGGERS)
        
    async def route_request(self, mode: str, prompt: str, user_id: str = None) -> dict:
        """Route to free models by default, paid for complex reasoning"""
        
        # Check budget first
        if not self.spend_tracker.can_spend():
            return {
                "success": False,
                "error": "Daily budget exhausted. Try again tomorrow."
            }
        
        # Build full prompt with system instructions
        full_prompt = f"{self.system_prompt}\n\n---\n\n{prompt}"
        
        # Determine if we need paid model (complex reasoning)
        use_paid = self._needs_reasoning(prompt) or mode in ["reasoning", "think"]
        
        # Build model list - if paid needed, put OpenRouter first
        if use_paid:
            # Move paid model to front for reasoning tasks
            models_to_try = [m for m in self.models if m.name == "openrouter"] + \
                           [m for m in self.models if m.name != "openrouter"]
            print(f"🧠 Complex task detected - using paid model for reasoning")
        else:
            # Free models first for everything else
            models_to_try = self.models
        
        # Try models in order
        for model in models_to_try:
            if not model.is_available():
                print(f"⏭️  Model {model.name} unavailable, skipping...")
                continue
                
            try:
                print(f"📤 Trying model: {model.name}")
                response = await model.generate(full_prompt, mode)
                
                if response["success"]:
                    # Track spend
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