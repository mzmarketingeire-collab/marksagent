import os
import aiohttp
from datetime import datetime

class SupabaseService:
    """Supabase database service"""
    
    def __init__(self, config):
        self.url = config.SUPABASE_URL
        self.key = config.SUPABASE_KEY
        self.table_leads = "leads"
        self.table_conversations = "conversations"
        
    def _get_headers(self):
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    async def save_leads(self, leads: list, criteria: str):
        """Save leads to Supabase"""
        if not self.url or not self.key:
            print("⚠️  Supabase not configured, skipping save")
            return
            
        for lead in leads:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "data": lead,
                        "criteria": criteria,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    async with session.post(
                        f"{self.url}/rest/v1/{self.table_leads}",
                        json=payload,
                        headers=self._get_headers()
                    ) as resp:
                        if resp.status in [200, 201]:
                            print(f"✅ Saved lead: {lead.get('name', 'Unknown')}")
                        else:
                            print(f"❌ Failed to save lead: {await resp.text()}")
            except Exception as e:
                print(f"❌ Error saving lead: {e}")
    
    async def save_conversation(self, user_id: str, message: str, response: str):
        """Save conversation to Supabase"""
        if not self.url or not self.key:
            return
            
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "user_id": user_id,
                    "message": message,
                    "response": response,
                    "created_at": datetime.utcnow().isoformat()
                }
                async with session.post(
                    f"{self.url}/rest/v1/{self.table_conversations}",
                    json=payload,
                    headers=self._get_headers()
                ) as resp:
                    pass  # Don't need to log every success
        except Exception as e:
            print(f"❌ Error saving conversation: {e}")