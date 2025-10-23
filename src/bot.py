import discord
import os
from dotenv import load_dotenv
from discord.ext.commands import *

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

client = discord.Client(intents=intents)
bot = Bot(command_prefix='-', intents=intents)

@bot.event
async def on_ready():
    bot.add_command(death)
    print(f'We have logged in as {client.user}')

@bot.command
async def help(ctx, command_name=None):
    help_message = (
        "Here are the available commands:\n"
        "- `-greet`: The bot will greet you.\n"
        "- `-death [reason]`: The bot will inform you that you've met a terrible fate. Optionally provide a reason."
    )
    if command_name:
        command = bot.get_command(command_name)
        if command:
            await ctx.send(f'Help for `{command_name}`:\n{command.help}')
        else:
            await ctx.send(help_message)
        return

@bot.command()
async def greet(ctx):
    '''Sends a greeting message to the user.'''
    await ctx.send('Greetings! How can I help you today?')

@bot.command()
async def death(ctx, *, reason=None):
    '''
    Logs the death, telling the user that they have died, optionally providing a reason.
    :param reason: The reason for the death
    :return:
    '''
    if reason:
        await ctx.send(f'You have met a terrible fate, {ctx.author.mention}.\nReason: {reason}')
        await ctx.message.delete()

    else:
        await ctx.send(f'You have met a terrible fate, {ctx.author.mention}.')
        await ctx.message.delete()

load_dotenv()
bot.run(os.getenv('DISCORD_TOKEN'))