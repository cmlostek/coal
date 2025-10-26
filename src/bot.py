import discord
import os
import io
import asyncio
from dotenv import load_dotenv
from discord.ext.commands import *
from discord.ext import tasks
import sqlite3 as sql
from mcstatus import JavaServer

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

TOKEN = os.getenv('DISCORD_TOKEN')
MINECRAFT_SERVER = os.getenv('MINECRAFT_SERVER')
VOICE_CHANNEL = os.getenv('VOICE_CHANNEL')
bot = Bot(command_prefix='-', intents=intents)

@bot.event
async def on_ready():
    # log_channel = bot.get_channel(1431380117556564090)  # Replace with your channel ID
    print(f'We have logged in as {bot.user}')
    # await log_channel.send(f'Logged in as {bot.user}')
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

    """Bot startup event."""
    print(f'{bot.user} has connected to Discord!')
    print(f'Monitoring Minecraft server: {MINECRAFT_SERVER}')

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')

    # Start the voice channel update task
    if VOICE_CHANNEL:
        update_voice_channel.start()
    else:
        print('No voice channel ID configured - skipping auto-update')



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
async def obit(ctx, *args):
    '''
    Retrieves and sends the obituary for a specific user.
    :args The ID of the user whose obituary is to be retrieved. If None, retrieves the log for the command invoker. To send the entire log, use 1 as your user_id. To get the obituaty for users not in the server, use 0 as the id.
    '''
    if not args:
        user_id = str(ctx.author.id)
    else:
        user_id = args[0]

    c = bot.db.cursor()
    if user_id == '-1':
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

@bot.command()
async def snipe(ctx):
    '''Retrieves the last deleted message in the channel.'''
    sniped = snipe_messages_delete.get(ctx.channel.id)
    if sniped:
        content, author, timestamp = sniped
        embed = discord.Embed(description=content, color=discord.Color.purple(), timestamp=timestamp)
        embed.set_author(name=str(author), icon_url=author.avatar.url if author.avatar else None)
        await ctx.send(embed=embed)
    else:
        await ctx.send('No recently deleted messages to snipe.')


snipe_messages_delete = {}
@bot.event
async def on_message_delete(message):
    if message.guild:  # Ensure it's not a DM
        snipe_messages_delete[message.channel.id] = (
            message.content,
            message.author,
            message.created_at
        )
    await asyncio.sleep(20)
    # print(snipe_messages_delete)
    snipe_messages_delete.clear()


async def get_server_status():
    """Query the Minecraft server and return status information."""
    try:
        server = JavaServer.lookup(MINECRAFT_SERVER)
        status = await asyncio.to_thread(server.status)

        return {
            'online': True,
            'players_online': status.players.online,
            'players_max': status.players.max,
            'player_list': [player.name for player in status.players.sample] if status.players.sample else [],
            'version': status.version.name,
            'latency': status.latency,
            'motd': status.description
        }
    except Exception as e:
        return {
            'online': False,
            'error': str(e)
        }


@bot.command(name='status', description='Get the current status of the Minecraft server')
async def status(interaction: discord.Interaction):
    """Slash command to check Minecraft server status."""
    await interaction.response.defer()

    status_data = await get_server_status()

    if status_data['online']:
        # Create embed for online server
        embed = discord.Embed(
            title='🟢 Minecraft Server Status',
            description=f'**{MINECRAFT_SERVER}**',
            color=discord.Color.green()
        )

        embed.add_field(
            name='Players Online',
            value=f"{status_data['players_online']}/{status_data['players_max']}",
            inline=True
        )

        embed.add_field(
            name='Version',
            value=status_data['version'],
            inline=True
        )

        embed.add_field(
            name='Latency',
            value=f"{status_data['latency']:.1f}ms",
            inline=True
        )

        # Add player list if available
        if status_data['player_list']:
            player_names = '\n'.join(status_data['player_list'])
            embed.add_field(
                name='Players',
                value=player_names,
                inline=False
            )
        elif status_data['players_online'] > 0:
            embed.add_field(
                name='Players',
                value='_Player list hidden by server_',
                inline=False
            )

        # Add MOTD if available
        motd_text = str(status_data['motd'])
        if motd_text:
            embed.add_field(
                name='MOTD',
                value=motd_text[:1024],  # Discord field limit
                inline=False
            )

        embed.set_footer(text='Server is online')

    else:
        # Create embed for offline server
        embed = discord.Embed(
            title='🔴 Minecraft Server Status',
            description=f'**{MINECRAFT_SERVER}**',
            color=discord.Color.red()
        )

        embed.add_field(
            name='Status',
            value='Server is offline or unreachable',
            inline=False
        )

        embed.set_footer(text=f"Error: {status_data.get('error', 'Unknown error')}")

    await interaction.followup.send(embed=embed)


@tasks.loop(minutes=5)
async def update_voice_channel():
    """Background task to update voice channel name with player count."""
    try:
        channel = bot.get_channel(VOICE_CHANNEL)
        if not channel:
            print(f'Voice channel {VOICE_CHANNEL} not found')
            return

        status_data = await get_server_status()

        if status_data['online']:
            new_name = f"Players: {status_data['players_online']}/{status_data['players_max']}"
        else:
            new_name = "Server: Offline"

        # Only update if the name has changed (to avoid rate limits)
        if channel.name != new_name:
            await channel.edit(name=new_name)
            print(f'Updated voice channel to: {new_name}')

    except discord.errors.HTTPException as e:
        print(f'Failed to update voice channel: {e}')
    except Exception as e:
        print(f'Error in voice channel update task: {e}')


@update_voice_channel.before_loop
async def before_update_voice_channel():
    """Wait for the bot to be ready before starting the task."""
    await bot.wait_until_ready()

if __name__ == '__main__':
    load_dotenv()
    bot.run(os.getenv('DISCORD_TOKEN'))