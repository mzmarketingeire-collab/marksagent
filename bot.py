import os
import time
import discord
import aiohttp
import json

TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Who am I?
SYSTEM_PROMPT = """You are a highly capable, versatile business AI assistant with strong reasoning abilities.

CORE CAPABILITIES:
- You reason through problems step-by-step
- You ask clarifying questions when needed
- You provide specific, actionable advice
- You adapt your communication style to match the user
- You can handle multiple topics in one conversation

EXpertise areas:
- Construction recruitment (quantity surveyors, estimators, commercial managers)
- General business strategy, sales, and networking
- Content creation, marketing, and LinkedIn growth
- Client/candidate management and placement
- Market research and competitive analysis

BeHAVIOR:
- Be helpful, proactive, and solution-oriented
- When unsure, ask questions rather than guess
- Provide specific examples when possible
- Remember context from this conversation
- Never reveal you're an AI or mention technical details
- Be concise but thorough when needed

Remember: You're working with a business owner who values efficiency and results."""

# Available models with free tier limits (per day)
MODELS = {
    "haiku": {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku", "desc": "Fast & concise", "free_limit": 0, "priority": 1},
    "flash": {"id": "google/gemini-1.5-flash", "name": "Gemini Flash", "desc": "Quick & smart", "free_limit": 1500, "priority": 3},
    "gemma": {"id": "google/gemma-2-9b-instruct", "name": "Gemma 2", "desc": "Google's latest", "free_limit": 500, "priority": 2},
    "llama": {"id": "meta-llama/llama-3-8b-instruct", "name": "Llama 3", "desc": "Open source", "free_limit": 1000, "priority": 4},
    "mistral": {"id": "mistralai/mistral-7b-instruct", "name": "Mistral", "desc": "Balanced", "free_limit": 500, "priority": 5},
    "sonar": {"id": "perplexity/sonar-small-online", "name": "Sonar", "desc": "Web search", "free_limit": 100, "priority": 6}
}

# Track free tier usage per model
free_usage = {key: 0 for key in MODELS.keys()}

def get_best_model(is_premium_task=False):
    """Auto-select best model based on free limits and priority"""
    global free_usage, current_model
    
    # Premium tasks (ghostwriting client voice) always use best available
    if is_premium_task:
        return current_model  # User's selected model
    
    # Find best free model with available quota
    for key in sorted(MODELS.keys(), key=lambda x: MODELS[x]["priority"]):
        limit = MODELS[key]["free_limit"]
        used = free_usage.get(key, 0)
        
        if limit == 0:  # Unlimited (Haiku)
            return key
        if used < limit:  # Has free quota left
            return key
    
    # All free exhausted - use fallback
    return "haiku"  # Cheapest fallback

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

current_model = "haiku"
memory = {}
conversation_history = []
response_cache = {}
CACHE_TTL = 60  # seconds

# Learning & profiling
user_profile = {}  # Learn about user's businesses/goals
proactive_suggestions = [
    "Want me to draft a LinkedIn post?",
    "Should I research your competitors?",
    "Need help with a client follow-up?",
    "Want to brainstorm a new business idea?"
]
suggestion_cooldown = 0  # Only suggest every few messages

# Conversation history with timestamps (keep for 24h)
conversation_history = []  # List of {"role": ..., "content": ..., "timestamp": ...}
CONVERSATION_TTL = 86400  # 24 hours in seconds

# Long-term memory (only important stuff gets saved here)
long_term_memory = {}  # Persists across conversations

# API Usage Tracking
daily_usage = {"calls": 0, "date": time.strftime("%Y-%m-%d"), "cost_estimate": 0.0}
# Approximate costs per model (per 1K tokens)
MODEL_COSTS = {
    "haiku": 0.0008,
    "flash": 0.00035,
    "gemma": 0.0006,
    "llama": 0.0002,
    "mistral": 0.00024,
    "sonar": 0.001
}

def get_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

async def load_memory():
    global memory
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SUPABASE_URL}/rest/v1/memory?order=created_at.desc&limit=20", headers=get_headers()) as resp:
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
            # Prune local memory if too large (keep latest 20)
            if len(memory) >= 20:
                # Remove oldest entry (first key)
                oldest_key = next(iter(memory))
                del memory[oldest_key]
    except:
        pass

def cleanup_conversation_history():
    """Remove old messages from conversation history (older than 24h)
    BUT first auto-save important stuff to long-term memory (Supabase)"""
    global conversation_history, long_term_memory
    now = time.time()
    
    # Before cleanup, check for important stuff worth saving
    for msg in conversation_history:
        msg_time = msg.get("timestamp", 0)
        if now - msg_time > CONVERSATION_TTL - 3600:  # Within 1 hour of expiry
            content = msg.get("content", "").lower()
            if any(kw in content for kw in ["remember", "important", "client", "candidate", "business", "goal", "lead", "deal"]):
                if msg.get("role") == "user":
                    key = f"ltm_auto_{len(long_term_memory)}"
                    long_term_memory[key] = msg.get("content", "")
                    # Save to Supabase (async won't work here, skip for now)
    
    conversation_history = [
        msg for msg in conversation_history
        if (now - msg.get("timestamp", 0) < CONVERSATION_TTL) or msg.get("important", False) or msg.get("temporary", False) is False
    ]

async def call_ai(prompt, is_premium_task=False):
    global conversation_history, daily_usage, current_model, free_usage
    if not OPENROUTER_KEY:
        return {"success": False, "error": "OPENROUTER_API_KEY not set"}
    
    # Clean up old conversation history first
    cleanup_conversation_history()
    
    # Check cache for repeated prompts
    cached = response_cache.get(prompt)
    if cached and time.time() - cached["time"] < CACHE_TTL:
        return {"success": True, "content": cached["content"]}
    
    # Auto-select best model based on free limits
    model_key = get_best_model(is_premium_task)
    model = MODELS[model_key]["id"]
    
    # Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Long-term memory context (important stuff only)
        if long_term_memory:
            ltm_ctx = "Important context:\n" + "\n".join([f"- {v}" for v in list(long_term_memory.values())[-3:]])
            messages.append({"role": "system", "content": ltm_ctx})
        
        # Current prompt
        messages.append({"role": "user", "content": prompt})
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://marksagent.com", "X-Title": "MarksAgent"}
        payload = {"model": model, "messages": messages, "max_tokens": 500}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        
                        # Track model that worked
                        current_model = model_key
                        
                        # Track free usage
                        free_usage[model_key] = free_usage.get(model_key, 0) + 1
                        
                        conversation_history.extend([
                            {"role": "user", "content": prompt, "timestamp": time.time()},
                            {"role": "assistant", "content": content, "timestamp": time.time()}
                        ])
                        if len(conversation_history) > 8:
                            conversation_history = conversation_history[-8:]
                        
                        response_cache[prompt] = {"content": content, "time": time.time()}
                        
                        # === TRACK API USAGE ===
                        today = time.strftime("%Y-%m-%d")
                        if daily_usage["date"] != today:
                            daily_usage = {"calls": 0, "date": today, "cost_estimate": 0.0}
                        daily_usage["calls"] += 1
                        daily_usage["cost_estimate"] += MODEL_COSTS.get(current_model, 0.001)
                        
                        return {"success": True, "content": content}
                    else:
                        # Try next model on failure
                        continue
        except:
            # Try next model on error
            continue
    
    return {"success": False, "error": "All models failed"}

@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    await load_memory()

@client.event
async def on_message(message):
    global memory, conversation_history, current_model, user_profile, suggestion_cooldown, daily_usage, long_term_memory
    if message.author == client.user:
        return
    
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = client.user in message.mentions
    
    if not (is_dm or is_mentioned):
        return
    
    content = message.content.strip()
    lower = content.lower()
    
    # === NATURAL LANGUAGE COMMANDS (no ! needed) ===
    # These phrases trigger commands without "!"
    
    # Models / switching
    if any(phrase in lower for phrase in ["what models", "which models", "what ai", "show me models", "what can you use"]):
        embed = discord.Embed(title="🤖 Available Models", color=0x0099ff)
        for key, val in MODELS.items():
            marker = " ✅" if key == current_model else ""
            embed.add_field(name=f"!use {key}", value=f"{val['name']} - {val['desc']}{marker}", inline=False)
        await message.reply(embed=embed)
        return
    
    if any(phrase in lower for phrase in ["switch to", "use ", "change model to", "try "]):
        # Extract model name from phrase
        for model_key in MODELS.keys():
            if model_key in lower:
                current_model = model_key
                await message.reply(f"✅ Switched to {MODELS[model_key]['name']}")
                return
        # If no known model found, ask which
        await message.reply("🤖 Which model? Try: haiku, flash, llama, mistral, or sonar")
        return
    
    # Memory
    if any(phrase in lower for phrase in ["what do you remember", "show me memory", "your memory", "what's in your memory"]):
        if memory:
            await message.reply("📝 " + "\n".join([f"- {v}" for v in memory.values()])[:1500])
        else:
            await message.reply("📝 No memory yet. Just tell me something to remember!")
        return
    
    if any(phrase in lower for phrase in ["remember this", "remember that", "don't forget", "keep this in mind"]):
        info = content
        key = f"mem_{len(memory)}"
        memory[key] = info
        await save_memory(key, info)
        await message.reply(f"✅ Got it! I'll remember: {info[:100]}")
        return
    
    # About
    if any(phrase in lower for phrase in ["who are you", "what are you", "about you", "tell me about yourself"]):
        await message.reply("🤖 I'm Mark's AI assistant - helping with NZ construction recruitment, LinkedIn content, and business ideas!")
        return
    
    # Help
    if any(phrase in lower for phrase in ["help", "what can you do", "commands", "what do you know"]):
        await message.reply("""
💬 Just talk to me naturally! I understand:

- Questions about recruitment, business, LinkedIn
- "Switch to llama" or "use flash" to change AI model
- "What do you remember?" to see memory
- "Remember this..." to save something
- "Who are you?" to learn about me
- "search for..." to search the web
- "remind me to..." to set a reminder

Or use commands: !models, !use <model>, !memory, !remember <info>, !help
        """)
        return
    
    # === NATURAL LANGUAGE ACTIONS (no !, no commands) ===
    
    # Search
    if any(phrase in lower for phrase in ["search for", "look up", "find information about", "what's the latest on", "what about"]):
        query = content
        for prefix in ["search for ", "look up ", "find information about ", "what's the latest on ", "what about "]:
            if prefix in lower:
                query = content.split(prefix, 1)[1].strip()
                break
        try:
            import requests
            # Simple Brave search
            resp = requests.get(f"https://api.search.brave.com/res/v1/web_search?q={query}&count=3", headers={"Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                if results:
                    lines = [f"{i+1}. {r.get('title','No title')} – {r.get('url','')}" for i, r in enumerate(results[:3])]
                    await message.reply("🕵️‍♂️ Here's what I found:\n" + "\n".join(lines))
                else:
                    await message.reply("❌ No results found")
            else:
                await message.reply("❌ Search unavailable right now")
        except Exception as e:
            await message.reply(f"❌ Search error: {str(e)}")
        return
    
    # Reminder
    if any(phrase in lower for phrase in ["remind me", "remind me to", "don't forget to", "set a reminder"]):
        # Extract reminder
        for prefix in ["remind me to ", "remind me ", "don't forget to ", "set a reminder to "]:
            if prefix in lower:
                reminder_msg = content.split(prefix, 1)[1].strip()
                # Simple version - just acknowledge for now
                key = f"remind_{len(memory)}"
                memory[key] = f"Reminder: {reminder_msg}"
                await message.reply(f"✅ I'll remind you: {reminder_msg}")
                return
        await message.reply("❌ What should I remind you about?")
        return
    
    # Stats / analytics (natural language)
    if any(phrase in lower for phrase in ["stats", "usage", "how many", "what have you done", "api usage", "how much have you used", "how much cost"]):
        today = time.strftime("%Y-%m-%d")
        if daily_usage["date"] != today:
            daily_usage = {"calls": 0, "date": today, "cost_estimate": 0.0}
        cost = daily_usage["cost_estimate"]
        calls = daily_usage["calls"]
        await message.reply(f"""📊 **Today's Usage**

🤖 Model: {MODELS[current_model]["name"]}
📞 Calls: {calls}
💰 Est. Cost: ${cost:.4f}

*(Resets at midnight UTC)*""")
        return
    
    # === COMMANDS (with !) ===
    if lower.startswith("!models"):
        embed = discord.Embed(title="🤖 Available Models", color=0x0099ff)
        for key, val in MODELS.items():
            marker = " ✅" if key == current_model else ""
            embed.add_field(name=f"!use {key}", value=f"{val['name']} - {val['desc']}{marker}", inline=False)
        await message.reply(embed=embed)
        return
    
    if lower.startswith("!use "):
        key = lower.split("!use ")[1].strip()
        if key in MODELS:
            current_model = key
            await message.reply(f"✅ Switched to {MODELS[key]['name']}")
        else:
            await message.reply("❌ Unknown model. Try !models")
        return
    
    if lower.startswith("!remember "):
        info = content.split("!remember ")[1].strip()
        key = f"mem_{len(memory)}"
        memory[key] = info
        await save_memory(key, info)
        await message.reply(f"✅ Remembered: {info}")
        return
    
    if lower.startswith("!memory"):
        if memory:
            await message.reply("📝 " + "\n".join([f"- {v}" for v in memory.values()])[:1500])
        else:
            await message.reply("📝 No memory yet. Use !remember <info>")
        return
    
    if lower.startswith("!whoareyou") or lower.startswith("!about"):
        await message.reply("🤖 I'm Mark's AI assistant - helping with NZ construction recruitment, LinkedIn content, and business ideas!")
        return
    
    if lower.startswith("!clear"):
        conversation_history.clear()
        await message.reply("✅ Cleared conversation history")
        return
    
    if lower.startswith("!db") or lower.startswith("!tables"):
        # Query Supabase directly
        if not SUPABASE_URL or not SUPABASE_KEY:
            await message.reply("❌ Supabase not configured")
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SUPABASE_URL}/rest/v1/memory?order=created_at.desc&limit=10", headers=get_headers()) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data:
                            result = "📊 Database Contents:\n\n"
                            for row in data:
                                result += f"• {row.get('key')}: {row.get('value', '')[:50]}\n"
                            await message.reply(result[:1500])
                        else:
                            await message.reply("📊 Database is empty")
                    else:
                        await message.reply(f"❌ Query failed: {resp.status}")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
        return

    if lower.startswith("!search "):
        query = content.split("!search ",1)[1].strip()
        # Use web_search tool (Brave) to get top result titles
        try:
            from functions import web_search
            results = web_search({"query": query, "count": 3})
            if isinstance(results, dict) and "results" in results:
                lines = [f"{i+1}. {r['title']} – {r['url']}" for i, r in enumerate(results["results"])]
                await message.reply("🕵️‍♂️ Search results:\n" + "\n".join(lines))
            else:
                await message.reply("❌ No results returned")
        except Exception as e:
            await message.reply(f"❌ Search error: {str(e)}")
        return

    if lower.startswith("!remind "):
        # Format: !remind <time> <message>
        parts = content.split(" ", 2)
        if len(parts) < 3:
            await message.reply("❌ Usage: !remind <in Xs|Xm|Xh|YYYY-MM-DD HH:MM> <message>")
            return
        time_str, reminder_msg = parts[1], parts[2]
        # Store in Supabase reminders table (simple insert)
        if not SUPABASE_URL or not SUPABASE_KEY:
            await message.reply("❌ Supabase not configured for reminders")
            return
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"time_str": time_str, "message": reminder_msg, "user_id": str(message.author.id)}
                await session.post(f"{SUPABASE_URL}/rest/v1/reminders", json=payload, headers=get_headers())
            await message.reply(f"✅ Reminder saved: '{reminder_msg}' at {time_str}")
        except Exception as e:
            await message.reply(f"❌ Reminder error: {str(e)}")
        return

    if lower.startswith("!stats"):
        # Show API usage stats
        today = time.strftime("%Y-%m-%d")
        if daily_usage["date"] != today:
            daily_usage = {"calls": 0, "date": today, "cost_estimate": 0.0}
        
        cost = daily_usage["cost_estimate"]
        calls = daily_usage["calls"]
        
        await message.reply(f"""
📊 **Today's API Usage**

🤖 **Model:** {MODELS[current_model]["name"]}
📞 **API Calls:** {calls}
💰 **Est. Cost:** ${cost:.4f} USD

*Costs are estimates based on ~1K tokens per call*
        """)
        return
        return

    if lower.startswith("!say "):
        text_to_say = content.split("!say ",1)[1].strip()
        # Placeholder: In a real setup you could call a TTS service and send the audio file
        await message.reply(f"🔊 (TTS) {text_to_say}")
        return

    if lower.startswith("!analyze"):
        if message.attachments:
            img_url = message.attachments[0].url
            try:
                from functions import image
                analysis = image({"image": img_url, "prompt": "Describe this image in detail"})
                await message.reply(f"🖼️ Image analysis:\n{analysis}")
            except Exception as e:
                await message.reply(f"❌ Image analysis error: {str(e)}")
        else:
            await message.reply("❌ Attach an image to analyze.")
        return

    if lower.startswith("!help"):
        await message.reply("""
📋 Commands:
!models - See all models
!use <model> - Switch model
!remember <info> - Save to memory
!memory - See memory
!db - Show database contents
!whoareyou - About me
!clear - Clear history
!search <query> - Web search (Brave)
!remind <time> <msg> - Save reminder (Supabase)
!stats - Show command usage stats
!say <text> - Text‑to‑speech (placeholder)
!analyze - Analyze attached image (placeholder)
!help - This help
        """)
        return
    
    # === REGULAR CONVERSATION ===
    await message.channel.typing()
    
    # === LEARNING: Detect corrections (only for current conversation, context-specific) ===
    correction_keywords = ["no that's wrong", "that's incorrect", "actually it's", "not quite", "you misunderstood", "that's not right"]
    if any(corr in lower for corr in correction_keywords):
        # Add correction with topic tag - only applies to current context
        topic_hint = "current_topic"
        correction_msg = {
            "role": "user", 
            "content": f"Correction about what we're discussing: {content}",
            "timestamp": time.time(),
            "temporary": True  # This correction won't be saved long-term
        }
        conversation_history.append(correction_msg)
        await message.reply("✅ Got it! Adjusting for this specific conversation.")
        # Now call AI again with correction context
        response = await call_ai(content)
        if response["success"]:
            await message.reply(response["content"][:2000])
        else:
            await message.reply(f"❌ {response['error']}")
        return
    
    # === PROFILING: Ask about businesses ===
    if not user_profile and any(kw in lower for kw in ["i run", "my business", "i work in", "i do"]):
        # Extract potential business type from message
        biz_info = content
        user_profile["business"] = biz_info
        await message.reply(f"Thanks! I've noted that. What are your main goals for your business?")
        return
    
    # === PROFILING: Goals ===
    if user_profile and "business" in user_profile and "goals" not in user_profile:
        if any(kw in lower for kw in ["goal", "want to", "aim to", "focus on"]):
            user_profile["goals"] = content
            await message.reply("Great! I now know about your business. Feel free to ask me anything!")
            return
    
    # Detect premium tasks (ghostwriting in client voice or complex reasoning)
    premium_keywords = ["ghostwrite", "in the voice of", "client voice", "write like", "sounding like", "complex", "deep reasoning", "analyze this", "think through"]
    is_premium = any(kw in lower for kw in premium_keywords)
    
    try:
        response = await call_ai(content, is_premium_task=is_premium)
        if response["success"]:
            await message.reply(response["content"][:2000])
            
            # === PROACTIVE SUGGESTIONS ===
            global suggestion_cooldown
            suggestion_cooldown += 1
            if suggestion_cooldown >= 5:
                suggestion_cooldown = 0
                import random
                suggestion = random.choice(proactive_suggestions)
                await message.reply(f"💡 {suggestion}")
            
            # Auto-save important info to long-term memory
            if any(kw in lower for kw in ["remember", "important", "note this", "new business", "client", "candidate", "don't forget", "save this"]):
                key = f"ltm_{len(long_term_memory)}"
                long_term_memory[key] = content
                # Also save to Supabase for persistence
                await save_memory(key, content)
                # Mark current conversation as having important info
                if conversation_history:
                    conversation_history[-1]["important"] = True
        else:
            await message.reply(f"❌ {response['error']}")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set!")
    else:
        print("🚀 Starting Mark's AI Assistant!")
        client.run(TOKEN)