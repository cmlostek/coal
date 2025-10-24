import discord
import os
import io
from dotenv import load_dotenv
from discord.ext.commands import *
import sqlite3 as sql

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

bot = Bot(command_prefix='-', intents=intents)

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    # Initialize the database connection and ensure tables exist
    bot.db = sql.connect('coal_db2.sqlite3', check_same_thread=False)
    # Ensure the death_log table exists (create columns used by the code)
    c = bot.db.cursor()
    c.execute('''
              CREATE TABLE IF NOT EXISTS death_log
              (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  cntr INTEGER,
                  reason TEXT
                  )
              ''')
    bot.db.commit()



@bot.command()
async def ping(ctx):
    '''Responds with the bot latency! Use to test if the bot is responsive.'''
    await ctx.send(round(bot.latency, 2) * 1000)

@bot.command()
async def greet(ctx):
    '''Sends a greeting message to the user.'''
    await ctx.send('Greetings! How can I help you today?')

@bot.command()
async def death(ctx, *args):
    '''
    Logs a death adding a poor soul to the graveyard.
    :args Optional first arg is the id (mention or digits). If omitted, uses the command invoker. Any remaining args are joined as the reason.
    '''
    death_channel = bot.get_channel(1422284082955685888)  # Replace with your channel ID
    # Determine target id and reason
    if not args:
        user_id_str = str(ctx.author.id)
        reason = None
    else:
        first = args[0]
        if first == '0' or first.startswith('<@') or first.isdigit():
            user_id_str = first
            reason = ' '.join(args[1:]) if len(args) > 1 else None
        else:
            # No id provided; treat all args as the reason and use invoker's id
            user_id_str = str(ctx.author.id)
            reason = ' '.join(args)

        # Increment the death count and log the death using the database
        c = bot.db.cursor()
        # Get the next sequential death number from the death_log table
        c.execute('SELECT MAX(cntr) FROM death_log')
        row = c.fetchone()
        num = (row[0] if row and row[0] is not None else 0) + 1
        c.execute('INSERT INTO death_log(id, cntr, reason) VALUES (?,?,?)', (user_id_str, num, reason))
        bot.db.commit()

        # Notify channel / user as before (no file writes)
        if user_id_str == '0':
            await death_channel.send(f'{num} - {reason}')
            await ctx.send('A new soul has entered the graveyard.')
            print('Death logged and posted.')
        else:
            # extract digits for user lookup
            digits = ''.join(ch for ch in user_id_str if ch.isdigit())
            try:
                user = await bot.fetch_user(int(digits))
            except Exception:
                user = user_id_str  # fallback to raw string if fetch fails
            if reason:
                await death_channel.send(f'{num} - You have met a terrible fate, <@{digits}>.\n Reason: {reason}')
                await ctx.send('A new soul has entered the graveyard.')
            else:
                await death_channel.send(f'{num} - You have met a terrible fate, <@{digits}>.')
                await ctx.send('A new soul has entered the graveyard.')

@bot.command()
async def obituary(ctx, *args):
    '''
    Retrieves and sends the obituary for a specific user.
    :args The ID of the user whose obituary is to be retrieved. If None, retrieves the log for the command invoker. To send the entire log, use 1 as your user_id. To get the obituaty for users not in the server, use 0 as the id.
    '''
    if not args:
        user_id = str(ctx.author.id)
    else:
        user_id = args[0]

    c = bot.db.cursor()
    if user_id == '1':
        c.execute('SELECT id, cntr, reason FROM death_log ORDER BY cntr')
        rows = c.fetchall()
        if not rows:
            await ctx.send('No death logs found. (The graveyard is empty.)')
            return
        lines = []
        for r in rows:
            lines.append(f'{r[0]} - {r[1]} - {r[2] or "No reason"}')
        content = '\n'.join(lines)
        fp = io.BytesIO(content.encode('utf-8'))
        await ctx.send(file=discord.File(fp, filename='death_log.txt'))
        return
    elif user_id == '0':
            # Return rows where the stored id is exactly '0'
            c.execute("SELECT cntr, reason FROM death_log WHERE id = '0' ORDER BY cntr")
            rows = c.fetchall()
            if not rows:
                await ctx.send('No death logs found for id 0.')
                return
            lines = [f'{r[0]} - {r[1] or "No reason"}' for r in rows]
            msg = discord.Embed(
                title='Death logs for user id 0',
                description='\n'.join(lines),
                color=discord.Color.red()
            )
            msg.set_footer(text=f'May they rest in peace.')
            await ctx.send(embed=msg)
            return

    # Normalize user lookup: prefer digits extracted from mention or id
    digits = ''.join(ch for ch in user_id if ch.isdigit())
    if digits:
        pattern = f'%{digits}%'
    else:
        # fallback to matching the raw string (e.g. '0' or weird input)
        pattern = f'%{user_id}%'

    # Normalize user lookup: prefer digits extracted from mention or id
    digits = ''.join(ch for ch in user_id if ch.isdigit())
    if digits:
        pattern = f'%{digits}%'
    else:
        # fallback to matching the raw string (e.g. '0' or weird input)
        pattern = f'%{user_id}%'

    c.execute('SELECT cntr, reason FROM death_log WHERE id LIKE ? ORDER BY id', (pattern,))
    rows = c.fetchall()
    if rows:
        user_logs_count = len(rows)
        if user_logs_count > 50:
            rows = rows[-50:]  # show only last 50 entries
        desc_lines = [f'{r[0]} - {r[1] or "Rest In Peace :("}' for r in rows]

        # try to resolve a nice username for the embed title
        title_user = user_id
        if digits:
            try:
                fetched = await bot.fetch_user(int(digits))
                title_user = str(fetched)
            except Exception:
                title_user = digits

        msg = discord.Embed(
            title=f'Death logs for user {title_user}',
            description=f'Total deaths: {user_logs_count}\n' + '\n'.join(desc_lines),
            color=discord.Color.red()
        )
        msg.set_footer(text=f'May they rest in peace.')
        await ctx.send(embed=msg)
        if user_logs_count >=100:
            await ctx.send('Holy smokes, that is a lot of deaths...')
    else:
        await ctx.send('Hmmmm, they dont seem dead...')


# @bot.command()
# async def quote(ctx, user_id, *, message):
#     quote_channel = bot.get_channel(1421296010231287858)
#     user = await bot.fetch_user(user_id[2:-1])
#     '''Sends the provided message as a quote.'''
#     quote_msg = discord.Embed(
#         title=f'{user} ',
#         description=message,
#         color=discord.Color.blue()
#     )
#     await ctx.send(embed=quote_msg)
#     await ctx.message.delete()

@bot.command()
async def echo(ctx, *, message):
    '''Echoes the provided message back to the user.'''
    await ctx.send(message)
    await ctx.message.delete()

if __name__ == '__main__':
    load_dotenv()
    bot.run(os.getenv('DISCORD_TOKEN'))