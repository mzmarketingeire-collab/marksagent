import os
import discord
from discord.ext import commands
import traceback

from models.router import LLMRouter
from models.gemma import GemmaModel
from models.gemini import GeminiModel
from models.minimax import MiniMaxModel
from models.openrouter import OpenRouterModel
from services.supabase import SupabaseService
from services.github import GitHubService
from services.lead_gen import LeadGenerator
from services.memory import MemoryService
from utils.spend_tracker import SpendTracker
from utils.config import Config

config = Config()
supabase = SupabaseService(config)
github = GitHubService(config)
lead_gen = LeadGenerator(config, supabase)
spend_tracker = SpendTracker(config)
memory = MemoryService(config)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)

router = None

@bot.event
async def on_ready():
    global router
    print(f'✅ Logged in as {bot.user}')
    try:
        router = LLMRouter(
            models=[GemmaModel(config), GeminiModel(config), MiniMaxModel(config), OpenRouterModel(config)],
            spend_tracker=spend_tracker
        )
        await memory.load_context()
        print("✅ Ready - free models first, €1/day budget")
    except Exception as e:
        print(f"❌ Init failed: {e}")
        router = None

@bot.event
async def on_message(message):
    """Responds to DMs and mentions - no prefix needed"""
    if message.author == bot.user:
        return
    
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    
    if not (is_dm or is_mentioned):
        return
    
    if message.content.strip().startswith(config.COMMAND_PREFIX):
        return
    
    await message.channel.typing()
    
    try:
        context = await memory.get_context()
        response = await router.route_request(
            mode="general",
            prompt=f"Memory: {context}\n\nUser: {message.content}",
            user_id=str(message.author.id)
        )
        
        if response["success"]:
            await message.reply(response["content"][:2000])
            await memory.check_and_save(response["content"], message.content)
        else:
            await message.reply(f"❌ {response['error']}")
    except Exception as e:
        await message.reply(f"❌ {str(e)}")

@bot.command(name="ask")
async def ask(ctx, *, question):
    if not router:
        await ctx.send("❌ Bot not ready")
        return
    await ctx.send("🤔 Thinking...")
    
    try:
        context = await memory.get_context()
        response = await router.route_request(
            mode="general",
            prompt=f"Memory: {context}\n\nQuestion: {question}",
            user_id=str(ctx.author.id)
        )
        await ctx.send(response["content"] if response["success"] else f"❌ {response['error']}")
    except Exception as e:
        await ctx.send(f"❌ {str(e)}")

@bot.command(name="think")
async def think(ctx, *, topic):
    """Step-by-step reasoning"""
    if not router:
        await ctx.send("❌ Bot not ready")
        return
    await ctx.send("🧠 Thinking...")
    
    try:
        response = await router.route_request(
            mode="reasoning",
            prompt=f"Think step by step:\n\n{topic}",
            user_id=str(ctx.author.id)
        )
        await ctx.send(response["content"][:2000] if response["success"] else f"❌ {response['error']}")
    except Exception as e:
        await ctx.send(f"❌ {str(e)}")

@bot.command(name="remember")
async def remember(ctx, *, info):
    await memory.force_save(info)
    await ctx.send(f"✅ Remembered: {info}")

@bot.command(name="memory")
async def show_memory(ctx):
    mem = await memory.get_context()
    await ctx.send(f"📝 Memory:\n{mem[:1500]}")

@bot.command(name="forget")
async def forget(ctx, *, item):
    await memory.remove(item)
    await ctx.send(f"🗑️ Forgot: {item}")

@bot.command(name="leads")
async def get_leads(ctx, *, criteria):
    if not router:
        await ctx.send("❌ Bot not ready")
        return
    await ctx.send("🔍 Finding leads...")
    
    try:
        response = await router.route_request(
            mode="leads",
            prompt=f"Find leads: {criteria}",
            user_id=str(ctx.author.id)
        )
        if response["success"]:
            leads = response.get("leads", [])
            if leads:
                await supabase.save_leads(leads, criteria)
        await ctx.send(response["content"] if response["success"] else f"❌ {response['error']}")
    except Exception as e:
        await ctx.send(f"❌ {str(e)}")

@bot.command(name="marketing")
async def marketing_cmd(ctx, *, topic):
    if not router:
        await ctx.send("❌ Bot not ready")
        return
    await ctx.send("📢 Creating content...")
    
    try:
        response = await router.route_request(
            mode="marketing",
            prompt=f"Create marketing: {topic}",
            user_id=str(ctx.author.id)
        )
        await ctx.send(response["content"] if response["success"] else f"❌ {response['error']}")
    except Exception as e:
        await ctx.send(f"❌ {str(e)}")

@bot.command(name="budget")
async def check_budget(ctx):
    daily = spend_tracker.get_daily_spend()
    remaining = config.MAX_DAILY_SPEND - daily
    await ctx.send(f"💰 Today: €{daily:.2f} / €{config.MAX_DAILY_SPEND} (€{remaining:.2f} left)")

@bot.command(name="help")
async def help_command(ctx):
    await ctx.send("""
🤖 MarksAgent Commands

📢 Chat: Just DM or mention me - no prefix needed!
❓ !ask <question>
🧠 !think <topic> - step by step reasoning
💾 !remember <info> - save to memory
📝 !memory - show memory
🗑️ !forget <item> - remove from memory
🔍 !leads <criteria> - find leads
📢 !marketing <topic> - create content
💰 !budget - check spending
""")

def run():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Set DISCORD_TOKEN")
        return
    print("🚀 Starting MarksAgent...")
    bot.run(token)

if __name__ == "__main__":
    run()