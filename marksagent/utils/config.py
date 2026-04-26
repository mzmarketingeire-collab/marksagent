import os

class Config:
    """Configuration settings"""
    
    # Bot settings
    COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
    
    # Budget
    MAX_DAILY_SPEND = float(os.getenv("MAX_DAILY_SPEND", "1.00"))  # €1/day
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # GitHub
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    GITHUB_REPO = os.getenv("GITHUB_REPO")  # format: "username/repo"
    
    # AI Models
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OLLAMA_URL = os.getenv("OLLAMA_URL")
    
    def __init__(self):
        self._check_required()
        
    def _check_required(self):
        """Check for required config"""
        missing = []
        if not os.getenv("DISCORD_TOKEN"):
            missing.append("DISCORD_TOKEN")
            
        if missing:
            print(f"⚠️  Missing env vars: {', '.join(missing)}")
            print("The bot will start but some features may not work")