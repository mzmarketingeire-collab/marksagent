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

SYSTEM_PROMPT = """You are Mark's versatile AI business assistant."""

MODELS = {
    "google": {"id": "google", "free_limit": 1500},
    "gemini-flash": {"id": "google/gemini-1.5-flash", "free_limit": 2000},
    "gemma": {"id": "google/gemma-2-9b-instruct", "free_limit": 1000},
    "minimax": {"id": "minimax", "free_limit": 2000},
    "haiku": {"id": "anthropic/claude-3-haiku", "free_limit": 0},
    "llama": {"id": "meta-llama/llama-3-8b-instruct", "free_limit": 1000}
}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

conversation_history = []
free_usage = {k: 0 for k in MODELS.keys()}

daily_budget = {
    "date": time.strftime("%Y-%m-%d"),
    "spent": 0.0,
    "max_eur": 1.0,
    "calls": 0
}

def reset_budget():
    today = time.strftime("%Y-%m-%d")
    if daily_budget["date"] != today:
        daily_budget["date"] = today
        daily_budget["spent"] = 0.0
        daily_budget["calls"] = 0


# =========================
# 🔥 FIXED GEMINI CALL
# =========================
async def call_google(prompt):
    if not GOOGLE_AI_KEY:
        return {"success": False, "error": "Missing GOOGLE_API_KEY"}

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": str(prompt)}]
            }
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{url}?key={GOOGLE_AI_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as resp:

                text = await resp.text()

                if resp.status != 200:
                    print("GEMINI ERROR:", resp.status, text)
                    return {"success": False, "error": text}

                data = await resp.json()

                content = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )

                return {"success": True, "content": content, "model": "google"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def call_openrouter(prompt, model_id):
    if not OPENROUTER_KEY:
        return {"success": False, "error": "Missing OpenRouter key"}

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            data = await resp.json()
            content = data["choices"][0]["message"]["content"]
            return {"success": True, "content": content, "model": model_id}


async def call_ai(prompt):
    reset_budget()

    # 1. Try Google FIRST (free)
    result = await call_google(prompt)
    if result["success"]:
        return result

    # 2. Fallback to Claude (ONLY if needed)
    result = await call_openrouter(prompt, MODELS["haiku"]["id"])
    if result["success"]:
        return result

    return {"success": False, "error": "All models failed"}


@client.event
async def on_ready():
    print(f"✅ Bot running as {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if not (isinstance(message.channel, discord.DMChannel) or client.user in message.mentions):
        return

    async with message.channel.typing():
        response = await call_ai(message.content)

        if response["success"]:
            await message.reply(response["content"][:2000])
        else:
            await message.reply(f"❌ {response['error']}")


if __name__ == "__main__":
    client.run(TOKEN)
