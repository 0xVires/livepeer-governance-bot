import discord
import json
from config_private import DISCORD_TOKEN
from get_tally import get_totalStake, get_tally

client = discord.Client()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!tally'):
        with open("active_polls.json", "r") as f:
            polls = json.load(f)
        if not polls:
            await message.channel.send("There are currently no active polls!")
        else:
            for poll in polls.copy():
                text = get_tally(poll)
                await message.channel.send(text)

client.run(DISCORD_TOKEN)
