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
        router = LLMRouter(models=[GemmaModel(config), GeminiModel(config), MiniMaxModel(config), OpenRouterModel(config)], spend_tracker=spend_tracker)
        print("✅ Router initialized successfully")
        
        # Load memory on startup
        await memory.load_context()
        print("✅ Memory loaded")
    except Exception as e:
        print(f"❌ Router init failed: {e}")
        traceback.print_exc()
        router = None

@bot.event
async def on_message(message):
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
        # Build context from memory
        context = await memory.get_context()
        
        response = await router.route_request(
            mode="general", 
            prompt=f"Context: {context}\n\nUser: {message.content}", 
            user_id=str(message.author.id)
        )
        if response["success"]:
            await message.reply(response["content"][:2000])
            
            # Check if there's new info worth saving
            await memory.check_and_save(response["content"], message.content)
        else:
            await message.reply(f"❌ Error: {response['error']}")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@bot.command(name="ask")
async def ask(ctx, *, question):
    if router is None:
        await ctx.send("❌ Bot not ready. Try again in a moment.")
        return
    await ctx.send("🤔 Thinking...")
    try:
        context = await memory.get_context()
        response = await router.route_request(mode="general", prompt=f"Context: {context}\n\nUser: {question}", user_id=str(ctx.author.id))
        await ctx.send(response["content"] if response["success"] else f"❌ Error: {response['error']}")
        
        if response["success"]:
            await memory.check_and_save(response["content"], question)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="remember")
async def remember(ctx, *, info):
    """Force save info to memory"""
    await memory.force_save(info)
    await ctx.send(f"✅ Remembered: {info}")

@bot.command(name="memory")
async def show_memory(ctx):
    """Show what's in memory"""
    mem = await memory.get_context()
    await ctx.send(f"📝 My memory:\n{mem[:1500]}")

@bot.command(name="forget")
async def forget(ctx, *, item):
    """Remove info from memory"""
    await memory.remove(item)
    await ctx.send(f"🗑️ Forgot: {item}")

@bot.command(name="leads")
async def get_leads(ctx, *, criteria):
    if router is None:
        await ctx.send("❌ Bot not ready. Try again in a moment.")
        return
    await ctx.send("🔍 Searching for leads...")
    try:
        response = await router.route_request(mode="leads", prompt=criteria, user_id=str(ctx.author.id))
        if response["success"]:
            leads = response.get("leads", [])
            if leads:
                await supabase.save_leads(leads, criteria)
            await ctx.send(response["content"])
            
            # Save as new business if relevant
            if "new business" in criteria.lower() or "new client" in criteria.lower():
                await memory.force_save(f"Business lead criteria: {criteria}")
        else:
            await ctx.send(f"❌ Error: {response['error']}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="marketing")
async def marketing_cmd(ctx, *, topic):
    if router is None:
        await ctx.send("❌ Bot not ready. Try again in a moment.")
        return
    await ctx.send("📢 Creating marketing content...")
    try:
        response = await router.route_request(mode="marketing", prompt=topic, user_id=str(ctx.author.id))
        await ctx.send(response["content"] if response["success"] else f"❌ Error: {response['error']}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="budget")
async def check_budget(ctx):
    daily_spend = spend_tracker.get_daily_spend()
    remaining = config.MAX_DAILY_SPEND - daily_spend
    embed = discord.Embed(title="💰 Budget Status", color=0x00ff00)
    embed.add_field(name="Today's Spend", value=f"€{daily_spend:.2f}", inline=True)
    embed.add_field(name="Remaining", value=f"€{remaining:.2f}", inline=True)
    embed.add_field(name="Daily Limit", value=f"€{config.MAX_DAILY_SPEND}", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(title="🤖 AI Assistant Commands", color=0x0099ff)
    embed.add_field(name=f"{config.COMMAND_PREFIX}ask <question>", help="Ask anything", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}remember <info>", help="Force save to memory", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}memory", help="Show what's in memory", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}forget <item>", help="Remove from memory", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}leads <criteria>", help="Generate leads", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}marketing <topic>", help="Create content", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}budget", help="Check spend", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}help", help="This menu", inline=False)
    await ctx.send(embed=embed)

def run():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not set!")
        return
    print("🚀 Starting bot...")
    bot.run(token)

if __name__ == "__main__":
    run()