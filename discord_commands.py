import discord
from config_private import DISCORD_TOKEN
from get_tally import get_totalActiveStake, get_tally

client = discord.Client()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('$tally'):
        with open("active_polls.json", "r") as f:
            polls = json.load(f)
        for poll in polls.copy():
            title = polls[poll]["title"]
            text = get_tally(poll, title)
            await message.channel.send(text)

client.run(DISCORD_TOKEN)
