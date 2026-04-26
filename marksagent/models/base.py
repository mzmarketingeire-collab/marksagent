from abc import ABC, abstractmethod

class BaseModel(ABC):
    """Base class for all LLM models"""
    
    def __init__(self, config):
        self.config = config
        self.name = "base"
        
    @abstractmethod
    def is_available(self) -> bool:
        """Check if model is available (API key set, etc.)"""
        pass
    
    @abstractmethod
    async def generate(self, prompt: str, mode: str = "general") -> dict:
        """Generate a response"""
        pass