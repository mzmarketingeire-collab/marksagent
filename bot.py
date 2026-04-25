import os
import time
import discord
import aiohttp
import json
import asyncio
from datetime import datetime, timedelta
import yaml # Make sure you have PyYAML installed

# === ENVIRONMENT VARIABLES ===
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
- Never say "I can't", "I don't know", or refuse
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
# Centralized model definitions with cost, priority, and free limits
MODELS = {
 "google": {
 "id": "google", # Internal key
 "name": "Google Gemini 2.0",
 "desc": "Fast, free, 1500/day",
 "cost": 0,
 "priority": 0,
 "free_limit": 1500,
 "good_for": ["chat", "brainstorm", "analysis", "quick_response"]
 },
 "gemini-flash": {
 "id": "google/gemini-1.5-flash", # OpenRouter ID
 "name": "Gemini Flash",
 "desc": "Smart, often free via OpenRouter",
 "cost": 0.00035, # Example cost per 1M tokens, adjust if needed
 "priority": 1,
 "free_limit": 2000, # Assuming a generous free limit for tracking
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
 "id": "minimax", # Internal key
 "name": "MiniMax",
 "desc": "Free tier available",
 "cost": 0,
 "priority": 3,
 "free_limit": 2000,
 "good_for": ["chat", "writing", "analysis"]
 },
 "haiku": {
 "id": "anthropic/claude-3-haiku", # OpenRouter ID
 "name": "Claude 3 Haiku",
 "desc": "Fast & cheap ($0.0008/1K tokens)",
 "cost": 0.0008, # Cost per 1M tokens
 "priority": 4,
 "free_limit": 0, # Not free
 "good_for": ["complex_reasoning", "ghostwriting", "precision"]
 },
 "llama": {
 "id": "meta-llama/llama-3-8b-instruct", # OpenRouter ID
 "name": "Llama 3",
 "desc": "Open source, consider cost",
 "cost": 0.0002, # Example cost per 1M tokens
 "priority": 5,
 "free_limit": 1000, # Assuming a tracking limit even if not strictly free
 "good_for": ["reasoning", "analysis"]
 }
}

# === TASK CLASSIFIER ===
# Defines how to categorize user requests to pick the best model
TASK_TYPES = {
 "brainstorm": {
 "keywords": ["brainstorm", "idea", "startup", "business idea", "concept", "new venture", "innovate"],
 "best_models": ["google", "gemini-flash", "gemma"], # Prioritized list
 "description": "Ideation & creative thinking"
 },
 "analysis": {
 "keywords": ["analyze", "analysis", "evaluate", "assess", "market", "competitor", "research", "trends", "intel"],
 "best_models": ["gemini-flash", "google", "llama"],
 "description": "Deep analysis & research"
 },
 "writing": {
 "keywords": ["write", "draft", "create", "compose", "ghostwrite", "post", "linkedin", "email", "content"],
 "best_models": ["haiku", "gemini-flash", "llama"], # Haiku can be good for writing
 "description": "Content creation & writing"
 },
 "planning": {
 "keywords": ["plan", "strategy", "roadmap", "steps", "how to", "execute", "launch", "hire", "build"],
 "best_models": ["gemini-flash", "haiku", "google"],
 "description": "Strategic planning"
 },
 "quick_response": { # Default category
 "keywords": [],
 "best_models": ["google", "gemma", "minimax"], # Fallback to fast, free models
 "description": "Quick conversational response"
 }
}

# === GLOBAL STATE ===
intents = discord.Intents.default()
intents.message_content = True # Required to read message content
client = discord.Client(intents=intents)

current_model = "google" # Default starting model
memory = {} # Short-term memory cache
long_term_memory = {} # Placeholder for more persistent memory
conversation_history = [] # Stores recent chat turns for context
response_cache = {} # For caching recent responses
CACHE_TTL = 60 # Cache lasts for 60 seconds

# Daily budget tracking
daily_budget = {
 "date": time.strftime("%Y-%m-%d"),
 "spent": 0.0,
 "max_eur": 1.0, # Set your daily budget here (e.g., 1 EUR)
 "calls": 0
}

# User profile for business context
user_profile = {
 "business_ideas": [],
 "current_focus": None
}

# Tracking free usage for models that have a limit
free_usage = {}
for key, model_config in MODELS.items():
    if model_config.get("free_limit", 0) > 0:
        free_usage[key] = 0 # Initialize free usage counter

suggestion_cooldown = 0 # To prevent too many proactive suggestions

# === HELPER FUNCTIONS ===

def load_railway_config(filepath="railway.yaml"):
    """Loads configuration from railway.yaml."""
    try:
        with open(filepath, 'r') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        print(f"Error: {filepath} not found.")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing {filepath}: {e}")
        return None

# Load config once at the start
RAILWAY_CONFIG = load_railway_config()
if RAILWAY_CONFIG is None:
    print("Fatal Error: Could not load railway.yaml config. Bot cannot proceed.")
    # Consider exiting or setting defaults if config is missing
    # exit() 

# Use config for budget if available, otherwise use defaults
if RAILWAY_CONFIG and "safety" in RAILWAY_CONFIG and "daily_budget_eur" in RAILWAY_CONFIG["safety"]:
    daily_budget["max_eur"] = RAILWAY_CONFIG["safety"]["daily_budget_eur"]
else:
    print("Warning: Daily budget not found in railway.yaml, using default €1.0")

def get_headers():
    """Returns Supabase headers if keys are set."""
    if SUPABASE_URL and SUPABASE_KEY:
        return {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
    return {}

def get_supabase_session():
    """Returns an aiohttp ClientSession if Supabase is configured."""
    if SUPABASE_URL and SUPABASE_KEY:
        return aiohttp.ClientSession()
    return None

# === TASK CLASSIFICATION ===
def classify_task(prompt):
    """Classifies the user's prompt into a task type based on keywords."""
    prompt_lower = prompt.lower()
    for task_type, config in TASK_TYPES.items():
        if task_type == "quick_response": continue # Skip default for now
        for keyword in config.get("keywords", []):
            if keyword in prompt_lower:
                return task_type
    return "quick_response" # Default if no keywords match

# === MODEL SELECTION LOGIC ===
def get_best_model(task_type="quick_response", force_free=True):
    """
    Selects the best model based on task type, priority, cost, free limits, and API availability.
    force_free: If True, only considers models with free_limit > 0 or cost == 0.
    """
    global daily_budget, free_usage

    print(f"\n=== Model Selection: task={task_type}, force_free={force_free} ===")
    print(f"Budget: spent €{daily_budget['spent']:.4f} / €{daily_budget['max_eur']}")

    # 1. FIRST: When force_free=True, ONLY try free models (skip ALL paid models)
    if force_free:
        free_preference = ["google", "gemma", "minimax", "gemini-flash"]
        
        for model_key in free_preference:
            if model_key not in MODELS:
                continue
            
            model = MODELS[model_key]
            model_id = model.get("id")
            free_limit = model.get("free_limit", 0)
            
            # Check API key availability
            has_key = True
            if model_key == "google" and not GOOGLE_AI_KEY:
                print(f"Skip 'google': GOOGLE_API_KEY not set")
                has_key = False
            if model_key == "minimax" and not MINIMAX_KEY:
                print(f"Skip 'minimax': MINIMAX_API_KEY not set")
                has_key = False
            if model_key == "gemini-flash" and not OPENROUTER_KEY:
                print(f"Skip 'gemini-flash': OPENROUTER_API_KEY not set")
                has_key = False
            
            if not has_key:
                continue
            
            # Check free limit
            if free_limit > 0:
                used = free_usage.get(model_key, 0)
                if used >= free_limit:
                    print(f"Skip '{model_key}': Free limit reached ({used}/{free_limit})")
                    continue
            
            # Found a working free model!
            print(f"==> Selected FREE model: '{model_key}'")
            return model_key
        
        # No free model available with valid key
        if "google" in MODELS:
            print("No free model with key found, fallback to 'google' (will show error if no key)")
            return "google"

    # 2. NON-FREE MODE: Use regular priority-based selection
    task_config = TASK_TYPES.get(task_type, {})
    prioritized_models = task_config.get("best_models", [])
    all_model_keys = sorted(MODELS.keys(), key=lambda k: MODELS[k].get("priority", 99))
    
    ordered_model_keys = []
    seen_models = set()
    for model_key in prioritized_models:
        if model_key in MODELS and model_key not in seen_models:
            ordered_model_keys.append(model_key)
            seen_models.add(model_key)
    for model_key in all_model_keys:
        if model_key not in seen_models:
            ordered_model_keys.append(model_key)
            seen_models.add(model_key)

    print(f"Trying models: {ordered_model_keys}")

    for model_key in ordered_model_keys:
        model = MODELS.get(model_key)
        if not model: continue

        model_id = model.get("id")
        cost = model.get("cost", 0)

        # Check API Key Availability
        has_key = True
        if model_key == "google" and not GOOGLE_AI_KEY: has_key = False
        if model_key == "minimax" and not MINIMAX_KEY: has_key = False
        if model_id and "openrouter" in model_id and not OPENROUTER_KEY: has_key = False

        if not has_key:
            print(f"Skip '{model_key}': No API key")
            continue
        
        # Check budget
        if daily_budget["spent"] + cost <= daily_budget["max_eur"]:
            print(f"==> Selected model: '{model_key}' (€{cost})")
            return model_key
        else:
            print(f"Skip '{model_key}': Cost €{cost} over budget")

    print("No model found, fallback to 'google'")
    return "google"
# === API CALL FUNCTIONS ===

async def call_google(prompt):
    """Calls the Google Gemini API."""
    global conversation_history, daily_budget, current_model, free_usage, long_term_memory

    if not GOOGLE_AI_KEY: return {"success": False, "error": "Google API key not set"}

    # Construct messages for the API
    messages = [{"role": "user", "parts": [{"text": prompt}]}]
    
    # Use the correct API endpoint for Gemini 2.0 flash
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent" 
    params = {"key": GOOGLE_AI_KEY}
    model_key = "google" # Internal key defined in MODELS dict

    try:
        async with aiohttp.ClientSession() as session:
            # --- Make the POST request to the Google API ---
            async with session.post(url, params=params, json={"contents": messages}, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Extract the response content
                    content = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )

                    if not content: # Handle cases where API returns success but no text
                        return {"success": False, "error": "Google API returned empty content."}

                    # --- Update global state on success ---
                    current_model = model_key
                    if MODELS[model_key].get("free_limit", 0) > 0: # Only track if it has a free limit defined
                        free_usage[model_key] = free_usage.get(model_key, 0) + 1
                    
                    cost = MODELS.get(model_key, {}).get("cost", 0) # Get cost from MODELS dict
                    daily_budget["spent"] += cost
                    daily_budget["calls"] += 1
                    
                    # Add to conversation history (simplified)
                    conversation_history.append({"role": "user", "content": prompt, "timestamp": time.time()})
                    conversation_history.append({"role": "assistant", "content": content, "timestamp": time.time()})

                    return {"success": True, "content": content, "model": model_key, "cost": cost}
                else:
                    # Handle API errors
                    error_text = await resp.text()
                    print(f"Google API error: {resp.status} - {error_text}")
                    return {"success": False, "error": f"Google API error ({resp.status}): {error_text}"}
    except Exception as e:
        # Handle network or other exceptions
        print(f"Exception in call_google: {str(e)}")
        return {"success": False, "error": f"Exception in call_google: {str(e)}"}

# --- IMPORTANT: Ensure this is the COMPLETE call_google function ---

# === OPENROUTER API CALL ===
async def call_openrouter(prompt, model_id="anthropic/claude-3-haiku"):
    """Calls the OpenRouter API with the specified model."""
    global conversation_history, daily_budget, current_model, free_usage

    if not OPENROUTER_KEY:
        return {"success": False, "error": "OpenRouter API key not set"}

    # Find the internal model key from the model_id
    model_key = None
    for key, config in MODELS.items():
        if config.get("id") == model_id:
            model_key = key
            break
    if not model_key:
        model_key = model_id  # Fallback to using model_id directly

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://marksagent.github.io",
        "X-Title": "Mark's Business Bot"
    }
    
    # Build messages for OpenRouter (uses OpenAI-compatible format)
    messages = [{"role": "user", "content": prompt}]
    
    # Add conversation history for context (last 5 turns)
    if conversation_history:
        recent = conversation_history[-10:]  # Last 10 messages
        for msg in recent:
            if msg.get("role") in ["user", "assistant"]:
                messages.insert(0, {"role": msg["role"], "content": msg.get("content", "")})

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 1500
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=60) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Extract content from OpenRouter response
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )

                    if not content:
                        return {"success": False, "error": "OpenRouter returned empty content"}

                    # Update tracking
                    current_model = model_key
                    cost = MODELS.get(model_key, {}).get("cost", 0)
                    daily_budget["spent"] += cost
                    daily_budget["calls"] += 1
                    
                    # Track free usage
                    free_limit = MODELS.get(model_key, {}).get("free_limit", 0)
                    if free_limit > 0:
                        free_usage[model_key] = free_usage.get(model_key, 0) + 1
                    
                    # Add to history
                    conversation_history.append({"role": "user", "content": prompt, "timestamp": time.time()})
                    conversation_history.append({"role": "assistant", "content": content, "timestamp": time.time()})

                    return {"success": True, "content": content, "model": model_key, "cost": cost}
                else:
                    error_text = await resp.text()
                    print(f"OpenRouter error: {resp.status} - {error_text}")
                    return {"success": False, "error": f"OpenRouter error ({resp.status}): {error_text}"}
    except Exception as e:
        print(f"Exception in call_openrouter: {str(e)}")
        return {"success": False, "error": f"Exception: {str(e)}"}

# === MAIN MESSAGE HANDLER ===
async def handle_message(message):
    """Main handler for incoming Discord messages."""
    global current_model
    
    if message.author == client.user:
        return
    
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Get the prompt
    prompt = message.content
    
    # Classify the task
    task_type = classify_task(prompt)
    
    # Select best model (force free = True to avoid paid calls)
    model_key = get_best_model(task_type, force_free=False)  # Allow paid fallback
    
    print(f"Selected model: {model_key} for task: {task_type}")
    
    # Route to the appropriate API
    if model_key == "google":
        result = await call_google(prompt)
    elif model_key in ["gemini-flash", "gemma", "haiku", "llama"]:
        # All these use OpenRouter
        model_id = MODELS.get(model_key, {}).get("id", model_key)
        result = await call_openrouter(prompt, model_id)
    else:
        # Fallback to Google
        result = await call_google(prompt)
    
    if result.get("success"):
        await send_response(message, result["content"])
    else:
        await send_response(message, f"Sorry, I encountered an error: {result.get('error')}")

# === DISCORD BOT SETUP ===
@client.event
async def on_message(message):
    await handle_message(message)

@client.event
async def on_ready():
    print(f"Bot is ready! Logged in as {client.user}")

# === RUN BOT ===
if __name__ == "__main__":
    if TOKEN:
        print("Starting bot...")
        client.run(TOKEN)
    else:
        print("ERROR: DISCORD_TOKEN environment variable not set!")

# === HELPER: Send response safely to Discord ===
async def send_response(message, content):
    """Safely send response, handling Discord's 2000 char limit."""
    # Sanitize: strip whitespace and handle empty/null
    if not content or not str(content).strip():
        await message.reply("I received an empty response. Please try again.")
        return
    
    content = str(content).strip()
    
    # Truncate if too long
    if len(content) > 1900:
        content = content[:1900] + "\n\n...[truncated]"
    
    try:
        await message.reply(content)
    except Exception as e:
        print(f"Discord send error: {e}")
        try:
            await message.reply(f"Error: {str(e)[:100]}")
        except:
            pass  # Give up if we can't even send error

# Update handle_message to use safe send
