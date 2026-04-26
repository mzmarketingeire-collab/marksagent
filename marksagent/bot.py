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

# Default prompt that mirrors Javi's personality
DEFAULT_PROMPT = """You are a helpful, direct AI assistant. 

RULES:
- Be genuinely helpful, not performatively helpful
- Have opinions - you're allowed to disagree and prefer things
- Be resourceful before asking - try to figure it out yourself first
- Be careful with external actions - ask first
- Remember what you're told
- Listen to what the user tells you about their setup

STYLE:
- Concise when needed, thorough when it matters
- Not a corporate drone, not a sycophant
- Skip filler like "Great question!" - just answer
- Think step-by-step for complex problems

If you don't know something, say so but offer to help anyway."""

@bot.event
async def on_ready():
    global router
    print(f'✅ Logged in as {bot.user}')
    try:
        # Initialize router - automatically prioritizes free models
        router = LLMRouter(
            models=[
                GemmaModel(config),      # Free (local)
                GeminiModel(config),     # Free tier
                MiniMaxModel(config),    # Free tier
                OpenRouterModel(config)  # Fallback
            ], 
            spend_tracker=spend_tracker
        )
        print("✅ Router initialized (free models prioritized)")
        
        # Load memory on startup
        await memory.load_context()
        print("✅ Memory loaded")
    except Exception as e:
        print(f"❌ Router init failed: {e}")
        traceback.print_exc()
        router = None

@bot.event
async def on_message(message):
    """Handle messages - responds to DMs and mentions naturally, no command prefix needed"""
    if message.author == bot.user:
        return
    
    # Check if this is a DM or if bot is mentioned
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    
    # Respond to DMs and mentions (no prefix needed)
    if not (is_dm or is_mentioned):
        return
    
    # Skip if it's a command (starts with prefix)
    if message.content.strip().startswith(config.COMMAND_PREFIX):
        return
    
    await message.channel.typing()
    
    try:
        # Get context from memory
        context = await memory.get_context()
        
        # Build prompt with context
        prompt = f"Context from memory:\n{context}\n\nUser message: {message.content}"
        
        response = await router.route_request(
            mode="general", 
            prompt=prompt, 
            user_id=str(message.author.id)
        )
        
        if response["success"]:
            await message.reply(response["content"][:2000])
            
            # Save important info to memory
            await memory.check_and_save(response["content"], message.content)
        else:
            await message.reply(f"❌ Error: {response['error']}")
            
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@bot.command(name="ask")
async def ask(ctx, *, question):
    """Ask anything - works like talking naturally"""
    if router is None:
        await ctx.send("❌ Bot not ready. Try again in a moment.")
        return
    
    await ctx.send("🤔 Thinking...")
    
    try:
        context = await memory.get_context()
        prompt = f"Context from memory:\n{context}\n\nQuestion: {question}"
        
        response = await router.route_request(
            mode="general", 
            prompt=prompt, 
            user_id=str(ctx.author.id)
        )
        
        if response["success"]:
            await ctx.send(response["content"][:2000])
            await memory.check_and_save(response["content"], question)
        else:
            await ctx.send(f"❌ Error: {response['error']}")
            
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="think")
async def think(ctx, *, topic):
    """Think through something step by step"""
    if router is None:
        await ctx.send("❌ Bot not ready. Try again in a moment.")
        return
    
    await ctx.send("🧠 Thinking through this...")
    
    try:
        prompt = f"""Think through this step by step. Show your reasoning.

Topic: {topic}

Think step-by-step:"""
        
        response = await router.route_request(
            mode="reasoning", 
            prompt=prompt, 
            user_id=str(ctx.author.id)
        )
        
        if response["success"]:
            await ctx.send(response["content"][:2000])
        else:
            await ctx.send(f"❌ Error: {response['error']}")
            
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
    """Generate leads based on criteria"""
    if router is None:
        await ctx.send("❌ Bot not ready. Try again in a moment.")
        return
    
    await ctx.send("🔍 Searching for leads...")
    
    try:
        prompt = f"""Generate leads/business prospects based on this criteria:
{criteria}

For each lead, provide: name, company, role, why they're a good fit."""
        
        response = await router.route_request(
            mode="leads", 
            prompt=prompt, 
            user_id=str(ctx.author.id)
        )
        
        if response["success"]:
            leads = response.get("leads", [])
            if leads:
                await supabase.save_leads(leads, criteria)
            await ctx.send(response["content"])
            
            # Save business criteria to memory
            if "new business" in criteria.lower() or "new client" in criteria.lower():
                await memory.force_save(f"Business lead criteria: {criteria}")
        else:
            await ctx.send(f"❌ Error: {response['error']}")
            
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="marketing")
async def marketing_cmd(ctx, *, topic):
    """Create marketing content for a topic"""
    if router is None:
        await ctx.send("❌ Bot not ready. Try again in a moment.")
        return
    
    await ctx.send("📢 Creating marketing content...")
    
    try:
        prompt = f"""Create marketing content for: {topic}

Include:
- A catchy headline
- 2-3 key points
- A call to action"""
        
        response = await router.route_request(
            mode="marketing", 
            prompt=prompt, 
            user_id=str(ctx.author.id)
        )
        
        await ctx.send(response["content"] if response["success"] else f"❌ Error: {response['error']}")
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="budget")
async def check_budget(ctx):
    """Check today's spending"""
    daily_spend = spend_tracker.get_daily_spend()
    remaining = config.MAX_DAILY_SPEND - daily_spend
    
    embed = discord.Embed(title="💰 Budget Status", color=0x00ff00)
    embed.add_field(name="Today's Spend", value=f"€{daily_spend:.2f}", inline=True)
    embed.add_field(name="Remaining", value=f"€{remaining:.2f}", inline=True)
    embed.add_field(name="Daily Limit", value=f"€{config.MAX_DAILY_SPEND}", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="help")
async def help_command(ctx):
    """Show help - responds to DMs/mentions naturally too"""
    embed = discord.Embed(title="🤖 MarksAgent Commands", color=0x0099ff)
    
    # Natural conversation commands
    embed.add_field(name="Just send a message", value="I respond to DMs and mentions naturally", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}ask <question>", value="Ask anything", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}think <topic>", value="Think through something step-by-step", inline=False)
    
    # Memory commands
    embed.add_field(name=f"{config.COMMAND_PREFIX}remember <info>", value="Save info to memory", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}memory", value="Show what's in memory", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}forget <item>", value="Remove from memory", inline=False)
    
    # Project commands
    embed.add_field(name=f"{config.COMMAND_PREFIX}leads <criteria>", value="Generate business leads", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}marketing <topic>", value="Create marketing content", inline=False)
    embed.add_field(name=f"{config.COMMAND_PREFIX}budget", value="Check spending", inline=False)
    
    await ctx.send(embed=embed)

def run():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not set!")
        return
    print("🚀 Starting MarksAgent...")
    bot.run(token)

if __name__ == "__main__":
    run()