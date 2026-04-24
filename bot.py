import os
import discord
import aiohttp
import json

TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Available models with descriptions
MODELS = {
    "haiku": {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku", "desc": "Fast & concise"},
    "flash": {"id": "google/gemini-1.5-flash", "name": "Gemini Flash", "desc": "Quick & smart"},
    "llama": {"id": "meta-llama/llama-3-8b-instruct", "name": "Llama 3", "desc": "Open source"},
    "mistral": {"id": "mistralai/mistral-7b-instruct", "name": "Mistral", "desc": "Balanced"},
    "sonar": {"id": "perplexity/sonar-small-online", "name": "Sonar", "desc": "Web search"}
}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

current_model = "haiku"
memory = {}

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

async def load_memory():
    """Load memory from Supabase on startup"""
    global memory
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ Supabase not configured, no memory")
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SUPABASE_URL}/rest/v1/memory?order=created_at.desc&limit=20", headers=get_headers()) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        memory[item.get("key", "")] = item.get("value", "")
                    print(f"✅ Loaded {len(memory)} memories")
    except Exception as e:
        print(f"⚠️ Memory load error: {e}")

async def save_memory(key, value):
    """Save memory to Supabase"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"key": key, "value": value}
            async with session.post(f"{SUPABASE_URL}/rest/v1/memory", json=payload, headers=get_headers()) as resp:
                pass
    except:
        pass

async def call_ai(prompt, model_id=None):
    if not OPENROUTER_KEY:
        return {"success": False, "error": "OPENROUTER_API_KEY not set"}
    
    model = model_id or MODELS[current_model]["id"]
    
    # Include memory in prompt if exists
    memory_context = ""
    if memory:
        memory_lines = [f"- {v}" for v in list(memory.values())[-5:]]
        memory_context = f"\n\nPrevious context:\n" + "\n".join(memory_lines)
    
    full_prompt = f"{memory_context}\n\nUser: {prompt}" if memory_context else prompt
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://marksagent.com",
        "X-Title": "MarksAgent"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": full_prompt}],
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

@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    await load_memory()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions
    
    if not (is_dm or is_mentioned):
        return
    
    # Check for commands
    content = message.content.strip()
    
    if content.lower().startswith("!models"):
        # Show available models
        embed = discord.Embed(title="🤖 Available Models", color=0x0099ff)
        for key, val in MODELS.items():
            embed.add_field(name=f"!use {key}", value=f"{val['name']} - {val['desc']}", inline=False)
        await message.reply(embed=embed)
        return
    
    if content.lower().startswith("!use "):
        # Switch model
        model_key = content.lower().split("!use ")[1].strip()
        if model_key in MODELS:
            global current_model
            current_model = model_key
            await message.reply(f"✅ Switched to {MODELS[model_key]['name']}")
        else:
            await message.reply(f"❌ Unknown model. Use !models to see list.")
        return
    
    if content.lower().startswith("!remember "):
        # Save to memory
        info = content.split("!remember ")[1].strip()
        key = f"mem_{len(memory)}"
        memory[key] = info
        await save_memory(key, info)
        await message.reply(f"✅ Remembered: {info}")
        return
    
    if content.lower().startswith("!memory"):
        # Show memory
        if memory:
            mem_list = "\n".join([f"- {v}" for v in memory.values()])
            await message.reply(f"📝 My memory:\n{mem_list[:1500]}")
        else:
            await message.reply("📝 No memory yet. Use !remember <info> to add.")
        return
    
    await message.channel.typing()
    
    try:
        response = await call_ai(message.content)
        if response["success"]:
            await message.reply(response["content"][:2000])
            
            # Auto-save if user mentioned important info
            lower = message.content.lower()
            if any(kw in lower for kw in ["remember", "important", "note this", "new business", "client"]):
                key = f"mem_{len(memory)}"
                memory[key] = message.content
                await save_memory(key, message.content)
        else:
            await message.reply(f"❌ Error: {response['error']}")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set!")
    else:
        print("🚀 Starting bot with memory & model switching!")
        client.run(TOKEN)