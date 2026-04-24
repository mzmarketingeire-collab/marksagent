"""
Budget Monitor
Tracks API spending and enforces daily limits
"""

import os
from decimal import Decimal
from datetime import datetime
from supabase import create_client

class BudgetMonitor:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.daily_limit = Decimal(os.getenv('DAILY_BUDGET_EUR', '5.0'))
    
    async def check_budget(self, estimated_cost):
        """Check if we have budget for this API call"""
        daily_spent = await self.get_daily_spent()
        remaining = self.daily_limit - daily_spent
        
        if estimated_cost > remaining:
            return False, f"Budget exceeded. Spent: €{daily_spent}, Limit: €{self.daily_limit}"
        
        return True, f"Budget OK. Spent: €{daily_spent}, Remaining: €{remaining}"
    
    async def get_daily_spent(self):
        """Get total spent today"""
        try:
            response = self.supabase.rpc('get_daily_spend').execute()
            if response.data:
                return Decimal(str(response.data[0]['total_cost']))
            return Decimal('0.0')
        except:
            return Decimal('0.0')
    
    async def log_api_call(self, model, tokens_used, estimated_cost, provider, success=True):
        """Log an API call for tracking"""
        try:
            self.supabase.table('api_calls').insert({
                'model': model,
                'tokens_used': tokens_used,
                'estimated_cost': float(estimated_cost),
                'provider': provider,
                'success': success
            }).execute()
        except Exception as e:
            print(f"Error logging API call: {e}")
    
    async def get_daily_summary(self):
        """Get daily spending summary"""
        try:
            response = self.supabase.rpc('get_daily_spend').execute()
            if response.data:
                data = response.data[0]
                return {
                    'total_spent': data['total_cost'],
                    'call_count': data['call_count'],
                    'remaining': data['remaining_budget'],
                    'limit': self.daily_limit
                }
            return None
        except:
            return None
