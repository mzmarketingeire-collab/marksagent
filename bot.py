import os
import discord
import aiohttp
from decimal import Decimal

TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions
    
    if not (is_dm or is_mentioned):
        return
    
    await message.channel.typing()
    
    try:
        response = await call_ai(message.content)
        if response["success"]:
            await message.reply(response["content"][:2000])
        else:
            await message.reply(f"❌ Error: {response['error']}")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

async def call_ai(prompt):
    if not OPENROUTER_KEY:
        return {"success": False, "error": "OPENROUTER_API_KEY not set"}
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://marksagent.com",
        "X-Title": "MarksAgent"
    }
    payload = {
        "model": "google/gemini-2.0-flash-exp",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {"success": True, "content": content}
                else:
                    return {"success": False, "error": f"API error: {resp.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set!")
    else:
        print("🚀 Starting bot...")
        client.run(TOKEN)