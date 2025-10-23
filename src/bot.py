import discord
import os
from dotenv import load_dotenv
import re
from discord.ext.commands import *

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

bot = Bot(command_prefix='-', intents=intents)

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')


@bot.command()
async def ping(ctx):
    '''Responds with Pong! to test if the bot is responsive.'''
    await ctx.send(round(bot.latency, 2) * 1000)

@bot.command()
async def greet(ctx):
    '''Sends a greeting message to the user.'''
    await ctx.send('Greetings! How can I help you today?')

@bot.command()
async def death(ctx, id, *, reason=None):
    '''
    Logs the death, telling the user that they have died, optionally providing a reason.
    :param reason: The reason for the death
    :return:
    '''
    # Open or create the death count file
    if not os.path.exists('death.txt'):
        with open('death.txt', 'w') as f:
            f.write('0')
    with open('death.txt', 'r') as f:
        num = int(f.read())

    # Increment the death count and log the death
    with open('death.txt', 'w') as f:
        num = num + 1
        f.write(str(num))

    with open('death_log.txt', 'a') as f:
        if id == '0':
            f.write(f'{id} -- {num} - RIP: {reason}. \n')
            await ctx.send(f'{num} - {reason}')
        else:
            user = await bot.fetch_user(id[2:-1])
            if reason:
                f.write(f'{id} -- {num} - You have met a terrible fate, {user}. Reason: {reason}\n')
                await ctx.send(f'{num} - You have met a terrible fate, {user}.\n Reason: {reason}')
                await ctx.message.delete()
            else:
                f.write(f'{id} -- {num} - You have met a terrible fate, {user}.\n')
                await ctx.send(f'{num} - You have met a terrible fate, {user}.')
                await ctx.message.delete()
@death.error
async def death_error(ctx, error):
    if isinstance(error, MissingRequiredArgument):
        await ctx.send('Please provide a user ID to log the death for.')

@bot.command()
async def death_log(ctx, *, user_id=None):
    '''
    Retrieves and sends the death log for a specific user.
    :param user_id: The ID of the user whose death log is to be retrieved
    :return:
    '''
    # If no user_id is provided, use the command invoker's ID
    if user_id is None:
        user_id = ctx.author.id
    try:
        logs = []
        user_logs = []
        with open('death_log.txt', 'r') as f:
            for line in f:
                logs.append(line.split("--"))
        for log in logs:
            if str(user_id) in log[0]:
                user_logs.append(log[1].strip())
        user_logs_count = len(user_logs)
        if user_logs:
            msg = discord.Embed(
                title=f'Death logs for user {ctx.author.name}',
                description=f'Total deaths: {user_logs_count}\n' + '\n'.join(user_logs),
                color=discord.Color.red()
            )
            await ctx.send(embed=msg)
        else:
            await ctx.send(f'No death records found for user <@{user_id}>.')
    except FileNotFoundError:
        await ctx.send('Death log file not found.')


if __name__ == '__main__':
    load_dotenv()
    bot.run(os.getenv('DISCORD_TOKEN'))