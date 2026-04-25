import os
import time
import discord
import aiohttp
import json
import asyncio
from datetime import datetime, timedelta

TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_AI_KEY = os.getenv("GOOGLE_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MINIMAX_KEY = os.getenv("MINIMAX_API_KEY")

# === SYSTEM PROMPT ===
SYSTEM_PROMPT = """You are Mark's versatile AI business assistant.

CRITICAL RULES:
- Answer DIRECTLY and HELPFULLY
- Never say \"I can't\", \"I don't know\", or refuse
- Remember context from conversation
- Use user's info when they tell you about their setup
- Be confident, practical, and results-focused
- Always try to help - if unsure, ask or make your best guess

CORE STRENGTHS:
- Business strategy & execution (startups, scaling, operations)
- Sales, networking, lead generation
- Content creation & social media (LinkedIn especially)
- Recruitment & talent placement
- Market research & competitive analysis
- Coding & technical problems
- Anything the user needs - no limits

BEHAVIOR:
- Be concise but thorough
- Break complex tasks into steps
- Ask clarifying questions when needed
- Give specific, actionable advice
- Remember this conversation context
- Help with multiple business ideas the user is developing
- Adapt to user's communication style
- Proactive suggestions when helpful"""

# === SMART MODEL REGISTRY ===
MODELS = {
 "google": {
 "id": "google",
 "name": "Google Gemini 2.0",
 "desc": "Fast, free, 1500/day",
 "cost": 0,
 "priority": 0,
 "free_limit": 1500,
 "good_for": ["chat", "brainstorm", "analysis", "quick_response"]
 },
 "gemini-flash": {
 "id": "google/gemini-1.5-flash",
 "name": "Gemini Flash",
 "desc": "Smart, free via OpenRouter",
 "cost": 0.00035,
 "priority": 1,
 "free_limit": 2000,
 "good_for": ["reasoning", "writing", "analysis"]
 },
 "gemma": {
 "id": "google/gemma-2-9b-instruct",
 "name": "Gemma 2 (Google)",
 "desc": "Free, lightweight",
 "cost": 0,
 "priority": 2,
 "free_limit": 1000,
 "good_for": ["brainstorm", "chat", "quick_tasks"]
 },
 "minimax": {
 "id": "minimax",
 "name": "MiniMax",
 "desc": "Free tier available",
 "cost": 0,
 "priority": 3,
 "free_limit": 2000,
 "good_for": ["chat", "writing", "analysis"]
 },
 "haiku": {
 "id": "anthropic/claude-3-haiku",
 "name": "Claude 3 Haiku",
 "desc": "Fast & cheap ($0.0008/1K tokens)",
 "cost": 0.0008,
 "priority": 4,
 "free_limit": 0,
 "good_for": ["complex_reasoning", "ghostwriting", "precision"]
 },
 "llama": {
 "id": "meta-llama/llama-3-8b-instruct",
 "name": "Llama 3",
 "desc": "Open source, free tier",
 "cost": 0.0002,
 "priority": 5,
 "free_limit": 1000,
 "good_for": ["reasoning", "analysis"]
 }
}

# === TASK CLASSIFIER ===
TASK_TYPES = {
 "brainstorm": {
 "keywords": ["brainstorm", "idea", "startup", "business idea", "concept", "new venture"],
 "best_models": ["google", "gemini-flash", "gemma"],
 "description": "Ideation & creative thinking"
 },
 "analysis": {
 "keywords": ["analyze", "analysis", "evaluate", "assess", "market", "competitor", "research"],
 "best_models": ["gemini-flash", "google", "llama"],
 "description": "Deep analysis & research"
 },
 "writing": {
 "keywords": ["write", "draft", "create", "compose", "ghostwrite", "post", "linkedin", "email"],
 "best_models": ["haiku", "gemini-flash"],
 "description": "Content creation & writing"
 },
 "planning": {
 "keywords": ["plan", "strategy", "roadmap", "steps", "how to", "execute", "launch"],
 "best_models": ["gemini-flash", "haiku", "google"],
 "description": "Strategic planning"
 },
 "quick_response": {
 "keywords": [], # Default if no match
 "best_models": ["google", "gemma", "minimax"],
 "description": "Quick conversational response"
 }
}

# === GLOBAL STATE ===
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

current_model = "google"
memory = {} # Short-term memory
long_term_memory = {} # Business ideas & important stuff
conversation_history = []
response_cache = {}
CACHE_TTL = 60

# Daily budget tracking
daily_budget = {
 "date": time.strftime("%Y-%m-%d"),
 "spent": 0.0,
 "max_eur": 1.0,
 "calls": 0
}

# User business profile
user_profile = {
 "business_ideas": [], # List of ideas user is developing
 "current_focus": None
}

free_usage = {key: 0 for key in MODELS.keys()}
suggestion_cooldown = 0

def get_headers():
 return {
 "apikey": SUPABASE_KEY,
 "Authorization": f"Bearer {SUPABASE_KEY}",
 "Content-Type": "application/json"
 }

def classify_task(prompt):
 """Classify what type of task this is to route to best model"""
 prompt_lower = prompt.lower()

 for task_type, config in TASK_TYPES.items():
 if task_type == "quick_response":
 continue
 for keyword in config["keywords"]:
 if keyword in prompt_lower:
 return task_type

 return "quick_response"

def get_best_model(task_type="quick_response", force_free=True):
 """Intelligently select best model for task"""
 global daily_budget, free_usage

 # Check daily budget first
 if daily_budget["spent"] >= daily_budget["max_eur"]:
 return "google" # Only free models allowed

 # Get best models for this task
 best_models = TASK_TYPES.get(task_type, {}).get("best_models", ["google", "gemma"])

 # Try best models first (respecting priority)
 for model_key in best_models:
 if model_key not in MODELS:
 continue

 model = MODELS[model_key]

 # Check if API key available
 if model_key == "google" and not GOOGLE_AI_KEY:
 continue
 if model_key == "minimax" and not MINIMAX_KEY:
 continue
 if not OPENROUTER_KEY and model_key not in ["google", "minimax"]:
 continue

 # Check free tier limit
 if model["free_limit"] > 0:
 used = free_usage.get(model_key, 0)
 if used < model["free_limit"]:
 return model_key
 else:
 # Unlimited free or check budget
 if daily_budget["spent"] + model["cost"] < daily_budget["max_eur"]:
 return model_key

 # Fallback to Google (most reliable free)
 return "google"

async def call_google(prompt):
 """Call Google Gemini API"""
 global conversation_history, daily_budget, current_model, free_usage, long_term_memory

 if not GOOGLE_AI_KEY:
 return {"success": False, "error": "Google API key not set"}

 messages = [{"role": "user", "parts": [{"text": prompt}]}]

 url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
 params = {"key": GOOGLE_AI_KEY}

 try:
 async with aiohttp.ClientSession() as session:
 async with session.post(url, params=params, json={"contents": messages}) as resp:
 if resp.status == 200:
 data = await resp.json()
 content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

 current_model = "google"
 free_usage["google"] = free_usage.get("google", 0) + 1
 conversation_history.append({"role": "user", "content": prompt, "timestamp": time.time()})
 conversation_history.append({"role": "assistant", "content": content, "timestamp": time.time()})

 return {"success": True, "content": content, "model": "google", "cost": 0}
 else:
 return {"success": False, "error": f"Google API error: {resp.status}"}
 except Exception as e:
 return {"success": False, "error": str(e)}

async def call_minimax(prompt):
 """Call MiniMax API"""
 global conversation_history, daily_budget, current_model, free_usage

 if not MINIMAX_KEY:
 return {"success": False, "error": "MiniMax API key not set"}

 messages = [
 {"role": "system", "content": SYSTEM_PROMPT},
 {"role": "user", "content": prompt}
 ]

 url = "https://api.minimax.chat/v1/text/chatcompletion_pro"
 headers = {"Authorization": f"Bearer {MINIMAX_KEY}", "Content-Type": "application/json"}
 payload = {"model": "abab6.5s-chat", "messages": messages, "max_tokens": 1000}

 try:
 async with aiohttp.ClientSession() as session:
 async with session.post(url, json=payload, headers=headers) as resp:
 if resp.status == 200:
 data = await resp.json()
 content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

 current_model = "minimax"
 free_usage["minimax"] = free_usage.get("minimax", 0) + 1
 conversation_history.append({"role": "user", "content": prompt, "timestamp": time.time()})
 conversation_history.append({"role": "assistant", "content": content, "timestamp": time.time()})

 return {"success": True, "content": content, "model": "minimax", "cost": 0}
 else:
 return {"success": False, "error": f"MiniMax error: {resp.status}"}
 except Exception as e:
 return {"success": False, "error": str(e)}

async def call_openrouter(prompt, model_id):
 """Call OpenRouter API"""
 global conversation_history, daily_budget, current_model, free_usage

 if not OPENROUTER_KEY:
 return {"success": False, "error": "OpenRouter API key not set"}

 messages = [
 {"role": "system", "content": SYSTEM_PROMPT},
 {"role": "user", "content": prompt}
 ]

 url = "https://openrouter.ai/api/v1/chat/completions"
 headers = {
 "Authorization": f"Bearer {OPENROUTER_KEY}",
 "Content-Type": "application/json",
 "HTTP-Referer": "https://marksagent.com",
 "X-Title": "MarksAgent"
 }
 payload = {"model": model_id, "messages": messages, "max_tokens": 1000}

 try:
 async with aiohttp.ClientSession() as session:
 async with session.post(url, json=payload, headers=headers) as resp:
 if resp.status == 200:
 data = await resp.json()
 content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

 # Find which model key this was
 model_key = next((k for k, v in MODELS.items() if v["id"] == model_id), "unknown")
 current_model = model_key
 free_usage[model_key] = free_usage.get(model_key, 0) + 1
 conversation_history.append({"role": "user", "content": prompt, "timestamp": time.time()})
 conversation_history.append({"role": "assistant", "content": content, "timestamp": time.time()})

 cost = MODELS.get(model_key, {}).get("cost", 0.001)
 return {"success": True, "content": content, "model": model_key, "cost": cost}
 else:
 return {"success": False, "error": f"OpenRouter error: {resp.status}"}
 except Exception as e:
 return {"success": False, "error": str(e)}

async def call_ai(prompt, task_type="quick_response"):
 """Main AI router - picks best model and calls it"""
 global conversation_history, daily_budget, current_model, response_cache

 # Check cache
 cached = response_cache.get(prompt)
 if cached and time.time() - cached["time"] < CACHE_TTL:
 return {"success": True, "content": cached["content"], "model": "cache", "cost": 0}

 # Check daily budget
 if daily_budget["spent"] >= daily_budget["max_eur"]:
 return {"success": False, "error": f"⚠️ Daily budget exhausted (€{daily_budget['max_eur']})"}

 # Select best model for this task
 best_model = get_best_model(task_type)
 model_config = MODELS.get(best_model, {})

 result = None

 # Try primary model
 if best_model == "google":
 result = await call_google(prompt)
 elif best_model == "minimax":
 result = await call_minimax(prompt)
 else:
 result = await call_openrouter(prompt, model_config.get("id"))

 # If failed, try fallbacks
 if not result or not result.get("success"):
 fallback_models = ["google", "minimax", "gemini-flash"]
 for fb_model in fallback_models:
 if fb_model == best_model:
 continue
 fb_config = MODELS.get(fb_model, {})
 if fb_model == "google":
 result = await call_google(prompt)
 elif fb_model == "minimax":
 result = await call_minimax(prompt)
 else:
 result = await call_openrouter(prompt, fb_config.get("id"))
 if result and result.get("success"):
 break

 if result and result.get("success"):
 # Update budget
 cost = result.get("cost", 0)
 daily_budget["spent"] += cost
 daily_budget["calls"] += 1

 # Cache
 response_cache[prompt] = {"content": result["content"], "time": time.time()}

 # Trim history
 if len(conversation_history) > 20:
 conversation_history = conversation_history[-20:]

 return result
 else:
 return {"success": False, "error": "All models failed"}

async def load_memory():
 global memory
 if not SUPABASE_URL or not SUPABASE_KEY:
 return
 try:
 async with aiohttp.ClientSession() as session:
 async with session.get(f"{SUPABASE_URL}/rest/v1/memory?limit=50", headers=get_headers()) as resp:
 if resp.status == 200:
 data = await resp.json()
 for item in data:
 memory[item.get("key", "")] = item.get("value", "")
 except:
 pass

async def save_memory(key, value):
 global memory
 if not SUPABASE_URL or not SUPABASE_KEY:
 return
 try:
 async with aiohttp.ClientSession() as session:
 await session.post(f"{SUPABASE_URL}/rest/v1/memory", json={"key": key, "value": value}, headers=get_headers())
 except:
 pass

def reset_daily_budget_if_needed():
 """Reset budget if day has changed"""
 global daily_budget
 today = time.strftime("%Y-%m-%d")
 if daily_budget["date"] != today:
 daily_budget = {
 "date": today,
 "spent": 0.0,
 "max_eur": 1.0,
 "calls": 0
 }

@client.event
async def on_ready():
 print(f'✅ Logged in as {client.user}')
 await load_memory()

@client.event
async def on_message(message):
 global memory, conversation_history, current_model, user_profile, suggestion_cooldown, daily_budget, long_term_memory

 if message.author == client.user:
 return

 is_dm = isinstance(message.channel, discord.DMChannel)
 is_mentioned = client.user in message.mentions

 if not (is_dm or is_mentioned):
 return

 reset_daily_budget_if_needed()

 content = message.content.strip()
 lower = content.lower()

 # === BUILT-IN COMMANDS ===

 # Show models
 if any(p in lower for p in ["what models", "show models", "which models", "available models"]):
 embed = discord.Embed(title="🤖 Available AI Models", color=0x0099ff)
 for key, cfg in MODELS.items():
 marker = " ✅ ACTIVE" if key == current_model else ""
 embed.add_field(name=f"{cfg['name']}", value=f"{cfg['desc']}{marker}", inline=False)
 await message.reply(embed=embed)
 return

 # Show current model
 if any(p in lower for p in ["what model", "which model", "current model", "using"]):
 await message.reply(f"🤖 Using: **{MODELS[current_model]['name']}** for {TASK_TYPES['quick_response']['description']}")
 return

 # Switch model
 if any(p in lower for p in ["use ", "switch to ", "change to "]):
 for model_key in MODELS.keys():
 if model_key in lower:
 current_model = model_key
 await message.reply(f"✅ Switched to {MODELS[model_key]['name']}")
 return
 await message.reply("Which model? Try: google, haiku, minimax, gemini-flash, llama")
 return

 # Memory
 if any(p in lower for p in ["remember this", "save this", "don't forget"]):
 info = content
 key = f"mem_{len(memory)}"
 memory[key] = info
 await save_memory(key, info)
 await message.reply(f"✅ Saved: {info[:80]}")
 return

 # Show memory
 if any(p in lower for p in ["show memory", "what do you remember", "my memory"]):
 if memory:
 msg = "📝 My memory:\n" + "\n".join([f"• {v[:80]}" for v in list(memory.values())[:10]])
 await message.reply(msg)
 else:
 await message.reply("📝 No memory yet")
 return

 # Stats
 if any(p in lower for p in ["stats", "usage", "budget", "spent"]):
 await message.reply(f"""
📊 **Today's Stats**

🤖 Model: {MODELS[current_model]['name']}
📞 Calls: {daily_budget['calls']}
💰 Spent: €{daily_budget['spent']:.4f} / €{daily_budget['max_eur']:.2f}
⏱️ Date: {daily_budget['date']}

*Budget resets daily at midnight*
 """)
 return

 # Help
 if any(p in lower for p in ["help", "what can you do", "commands"]):
 await message.reply("""
💬 **I'm your AI business assistant!**

Just talk naturally. I understand:
- Business ideas, strategy, planning
- Content writing, LinkedIn posts
- Analysis, research, market insights
- Sales, recruiting, networking
- Coding, technical problems
- Literally anything

**Commands:**
- "What models?" → See available AI
- "Use [model]" → Switch AI
- "Remember..." → Save info
- "Stats" → Usage stats
- "Help" → This message
 """)
 return

 # Clear history
 if lower == "!clear" or "clear history" in lower:
 conversation_history.clear()
 await message.reply("✅ Conversation history cleared")
 return

 # === MAIN CONVERSATION ===

 async with message.channel.typing():
 reset_daily_budget_if_needed()

 # Classify task for smart routing
 task_type = classify_task(content)

 # Call AI
 response = await call_ai(content, task_type)

 if response["success"]:
 msg = response["content"]
 model_used = response.get("model", "unknown")
 cost = response.get("cost", 0)

 # Build reply with model info
 if cost > 0:
 reply = f"{msg}\n\n_Used {MODELS.get(model_used, {}).get('name', model_used)} (€{cost:.4f})_"
 else:
 reply = f"{msg}\n\n_Used {MODELS.get(model_used, {}).get('name', model_used)} (FREE)_"

 await message.reply(reply[:2000])

 # Proactive suggestions
 suggestion_cooldown += 1
 if suggestion_cooldown >= 5:
 suggestion_cooldown = 0
 import random
 suggestions = [
 "💡 Want me to help develop this idea further?",
 "💡 Should I create an action plan for this?",
 "💡 Need a LinkedIn post about this?"
 ]
 await message.reply(random.choice(suggestions))
 else:
 await message.reply(f"❌ {response['error']}")

if __name__ == "__main__":
 if not TOKEN:
 print("❌ DISCORD_TOKEN not set!")
 else:
 print("🚀 Starting Mark's optimized AI assistant!")
 print(f"📊 Daily budget: €{daily_budget['max_eur']}")
 client.run(TOKEN)