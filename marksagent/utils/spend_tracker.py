import os
from datetime import datetime, timedelta

class SpendTracker:
    """Track daily spend to stay within budget"""
    
    def __init__(self, config):
        self.max_daily_spend = config.MAX_DAILY_SPEND
        self.daily_spend = 0
        self.last_reset = datetime.utcnow().date()
        
    def can_spend(self) -> bool:
        """Check if we can still spend today"""
        self._check_reset()
        return self.daily_spend < self.max_daily_spend
        
    def add_spend(self, amount: float):
        """Add to daily spend"""
        self._check_reset()
        self.daily_spend += amount
        print(f"💰 Added €{amount:.4f} to spend. Total: €{self.daily_spend:.4f}")
        
    def get_daily_spend(self) -> float:
        """Get current daily spend"""
        self._check_reset()
        return self.daily_spend
        
    def _check_reset(self):
        """Reset daily spend if new day"""
        today = datetime.utcnow().date()
        if today > self.last_reset:
            self.daily_spend = 0
            self.last_reset = today
            print("🔄 Daily spend reset")