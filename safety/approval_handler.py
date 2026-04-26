"""
Approval Handler
Manages human approval workflow
"""

import discord
from datetime import datetime
from supabase import create_client
import json

class ApprovalHandler:
    def __init__(self, supabase_client, discord_client):
        self.supabase = supabase_client
        self.discord = discord_client
        self.approval_timeout = 3600
    
    async def request_approval(self, action_type, action_details, approval_channel_name="bot-approvals"):
        """Request human approval for an action"""
        
        approval_id = await self._save_approval_request(action_type, action_details)
        await self._send_discord_notification(action_type, action_details, approval_id, approval_channel_name)
        approved = await self._wait_for_approval(approval_id)
        
        return approved, approval_id
    
    async def _save_approval_request(self, action_type, action_details):
        """Save approval request to database"""
        try:
            response = self.supabase.table('approval_queue').insert({
                'action_type': action_type,
                'action_details': action_details,
                'status': 'pending'
            }).execute()
            return response.data[0]['id']
        except:
            return None
    
    async def _send_discord_notification(self, action_type, action_details, approval_id, channel_name):
        """Send approval request to Discord"""
        try:
            channel = discord.utils.get(self.discord.get_all_channels(), name=channel_name)
            
            if not channel:
                print(f"Approval channel '{channel_name}' not found")
                return
            
            embed = discord.Embed(
                title=f"⚠️ Approval Needed",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Type", value=action_type, inline=False)
            embed.add_field(name="Details", value=json.dumps(action_details, indent=2)[:1024], inline=False)
            embed.add_field(name="ID", value=approval_id, inline=False)
            
            view = ApprovalView(self.supabase, approval_id)
            await channel.send(embed=embed, view=view)
        
        except Exception as e:
            print(f"Error sending approval: {e}")
    
    async def _wait_for_approval(self, approval_id):
        """Wait for approval with timeout"""
        import asyncio
        start_time = datetime.now()
        
        while True:
            try:
                response = self.supabase.table('approval_queue').select('status').eq('id', approval_id).execute()
                
                if response.data and response.data[0]['status'] == 'approved':
                    return True
                elif response.data and response.data[0]['status'] == 'denied':
                    return False
                
                if (datetime.now() - start_time).total_seconds() > self.approval_timeout:
                    return False
                
                await asyncio.sleep(5)
            
            except:
                return False


class ApprovalView(discord.ui.View):
    """Discord buttons for approval"""
    
    def __init__(self, supabase_client, approval_id):
        super().__init__()
        self.supabase = supabase_client
        self.approval_id = approval_id
    
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_approval('approved')
        await interaction.response.send_message(f"✅ Approved!", ephemeral=True)
    
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_approval('denied')
        await interaction.response.send_message(f"❌ Denied!", ephemeral=True)
    
    async def _update_approval(self, status):
        try:
            self.supabase.table('approval_queue').update({'status': status}).eq('id', self.approval_id).execute()
        except:
            pass
