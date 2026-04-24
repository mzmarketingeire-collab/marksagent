import discord
import os
from llm.router import LLMRouter

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

router = None

@client.event
async def on_ready():
    global router
    print(f'Logged in as {client.user}')
    router = LLMRouter(budget_monitor=None, audit_logger=None)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    prompt = message.content

    await message.channel.send("Thinking...")

    try:
        response = await router.route_request("general", prompt)
        if response["success"]:
            await message.channel.send(response["content"])
        else:
            await message.channel.send("Error: " + response["error"])
    except Exception as e:
        await message.channel.send(f"Error: {str(e)}")

client.run(TOKEN)