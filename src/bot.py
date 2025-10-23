import discord
import os
from dotenv import load_dotenv
from discord.ext.commands import *

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

bot = Bot(command_prefix='-', intents=intents)

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')


@bot.command()
async def ping(ctx):
    '''Responds with the bot latency! Use to test if the bot is responsive.'''
    await ctx.send(round(bot.latency, 2) * 1000)

@bot.command()
async def greet(ctx):
    '''Sends a greeting message to the user.'''
    await ctx.send('Greetings! How can I help you today?')

@bot.command()
async def death(ctx, id, *, reason=None):
    death_channel = bot.get_channel(1422284082955685888)  # Replace with your channel ID
    '''
    Logs the death, telling the user that they have died, optionally providing a reason.
    :param id: The id of the user [REQUIRED]
    :param reason: The reason for the death [OPTIONAL]
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
                f.write(f'{id} -- {num} - {user} has died.. Reason: {reason}\n')
                await death_channel.send(f'{num} - You have met a terrible fate, {user}.\n Reason: {reason}')
                await ctx.message.delete()
            else:
                f.write(f'{id} -- {num} - {user} has died.\n')
                await death_channel.send(f'{num} - You have met a terrible fate, {user}.')
                await ctx.message.delete()
@death.error
async def death_error(ctx, error):
    if isinstance(error, MissingRequiredArgument):
        await ctx.send('Please provide a user ID to log the death for.')

@bot.command()
async def death_log(ctx, *, user_id=None):
    '''
    Retrieves and sends the death log for a specific user.
    :param user_id: The ID of the user whose death log is to be retrieved. If None, retrieves the log for the command invoker. To send the entire log, use 1 as your user_id.
    '''
    # If no user_id is provided, use the command invoker's ID
    if user_id is None:
        user_id = ctx.author.id
    elif user_id == '1':
        try:
            ctx.send(file=discord.File("./death_log.txt"))
        except FileNotFoundError:
            await ctx.send('Death log file not found.')
        return
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

@bot.command()
async def quote(ctx, user_id, *, message):
    quote_channel = bot.get_channel(1421296010231287858)
    user = await bot.fetch_user(user_id[2:-1])
    '''Sends the provided message as a quote.'''
    quote_msg = discord.Embed(
        title=f'{user} ',
        description=message,
        color=discord.Color.blue()
    )
    await ctx.send(embed=quote_msg)
    await ctx.message.delete()

@bot.command()
async def echo(ctx, *, message):
    '''Echoes the provided message back to the user.'''
    await ctx.send(message)
    await ctx.message.delete()

if __name__ == '__main__':
    load_dotenv()
    bot.run(os.getenv('DISCORD_TOKEN'))