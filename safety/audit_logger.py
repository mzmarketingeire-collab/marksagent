"""
Audit Logger
Logs all bot actions
"""

from datetime import datetime
from supabase import create_client

class AuditLogger:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
    
    async def log(self, action, details=None, status="success"):
        """Log an action"""
        try:
            self.supabase.table('audit_log').insert({
                'action': action,
                'details': details or {},
                'status': status
            }).execute()
        except Exception as e:
            print(f"Error logging: {e}")
    
    async def get_recent_actions(self, limit=50):
        """Get recent audit log entries"""
        try:
            response = self.supabase.table('audit_log').select('*').order('created_at', desc=True).limit(limit).execute()
            return response.data
        except:
            return []
