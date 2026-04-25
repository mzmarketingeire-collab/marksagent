import os
import discord
import aiohttp
import json
import time
from datetime import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_AI_KEY = os.getenv("GOOGLE_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SYSTEM_PROMPT = """You are Mark's AI business assistant. Help with anything business-related - brainstorming, strategy, writing, analysis, recruiting, sales, coding, anything. Be direct, helpful, and confident. Remember context from this conversation."""

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

conversation_history = []
current_model = "google"
daily_budget = {"spent": 0.0, "max": 1.0, "calls": 0, "date": time.strftime("%Y-%m-%d")}
memory = {}

def get_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

async def call_google(prompt):
    """Call Google Gemini"""
    if not GOOGLE_AI_KEY:
        return {"success": False, "error": "Google API key not set"}
    
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}?key={GOOGLE_AI_KEY}", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    return {"success": True, "content": content, "model": "google", "cost": 0}
                else:
                    text = await resp.text()
                    return {"success": False, "error": f"Google error {resp.status}: {text}"}
    except Exception as e:
        return {"success": False, "error": f"Google exception: {str(e)}"}

async def call_openrouter(prompt, model):
    """Call OpenRouter"""
    if not OPENROUTER_KEY:
        return {"success": False, "error": "OpenRouter key not set"}
    
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1000
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {"success": True, "content": content, "model": model, "cost": 0.001}
                else:
                    text = await resp.text()
                    return {"success": False, "error": f"OpenRouter error {resp.status}: {text}"}
    except Exception as e:
        return {"success": False, "error": f"OpenRouter exception: {str(e)}"}

async def call_ai(prompt):
    """Smart router - tries Google first, falls back to OpenRouter"""
    global current_model, daily_budget
    
    # Check budget
    if daily_budget["spent"] >= daily_budget["max"]:
        return {"success": False, "error": f"Budget exhausted (€{daily_budget['max']})"}
    
    # Try Google first (free)
    result = await call_google(prompt)
    if result["success"]:
        current_model = "google"
        daily_budget["calls"] += 1
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": result["content"]})
        return result
    
    # Fallback to OpenRouter
    result = await call_openrouter(prompt, "anthropic/claude-3-haiku")
    if result["success"]:
        current_model = "claude-haiku"
        daily_budget["spent"] += result["cost"]
        daily_budget["calls"] += 1
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": result["content"]})
        return result
    
    return {"success": False, "error": "All APIs failed"}

@client.event
async def on_ready():
    print(f'✅ Bot online as {client.user}')

@client.event
async def on_message(message):
    global daily_budget
    
    if message.author == client.user:
        return
    
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions
    
    if not (is_dm or is_mentioned):
        return
    
    # Reset budget if day changed
    today = time.strftime("%Y-%m-%d")
    if daily_budget["date"] != today:
        daily_budget = {"spent": 0.0, "max": 1.0, "calls": 0, "date": today}
    
    content = message.content.strip().lower()
    
    # Commands
    if "help" in content or "what can you" in content:
        await message.reply("""💬 I help with anything business-related!
- Brainstorm ideas
- Strategy & planning
- Content writing
- Analysis & research
- Recruiting & sales
- Coding & technical
- Anything else you need

Type naturally or mention me. Budget: €1.0/day (€{:.4f} spent today)""".format(daily_budget["spent"]))
        return
    
    if "stats" in content or "budget" in content:
        await message.reply(f"📊 Calls: {daily_budget['calls']} | Spent: €{daily_budget['spent']:.4f} / €{daily_budget['max']}")
        return
    
    if "clear" in content:
        conversation_history.clear()
        await message.reply("✅ History cleared")
        return
    
    # Main conversation
    async with message.channel.typing():
        response = await call_ai(message.content)
        
        if response["success"]:
            cost_str = " (FREE)" if response["cost"] == 0 else f" (€{response['cost']:.4f})"
            reply = response["content"][:1900] + f"\n\n_Model: {response['model']}{cost_str}_"
            await message.reply(reply)
        else:
            await message.reply(f"❌ {response['error']}")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set")
    else:
        print("🚀 Starting bot...")
        client.run(TOKEN)
