import discord
import os
import io
import asyncio
from dotenv import load_dotenv
from discord.ext.commands import *
from discord.ext import tasks
import sqlite3 as sql
from mcstatus import JavaServer
from youtube_dl import YoutubeDL
import nacl as nc  # Required for voice support in discord.py

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

TOKEN = os.getenv('DISCORD_TOKEN')
MINECRAFT_SERVER = 'realones.modpack.gg'
VOICE_CHANNEL = 1422645848923176990
bot = Bot(command_prefix='-', intents=intents)


@bot.event
async def on_ready():
    # log_channel = bot.get_channel(1431380117556564090)  # Replace with your channel ID
    print(f'We have logged in as {bot.user}')
    # await log_channel.send(f'Logged in as {bot.user}')
    # Initialize the database connection and ensure tables exist
    bot.db = sql.connect('db.sql', check_same_thread=False)
    # Ensure the death_log table exists (corrected to use log_id as PK and user_id to store Discord ID)
    c = bot.db.cursor()
    c.execute('''
              CREATE TABLE IF NOT EXISTS death_log
              (
                  log_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,    -- Storing the Discord User ID (or '0' for generic) as TEXT
                  cntr    INTEGER, -- The sequential death count
                  reason  TEXT
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


# ---
@bot.group(name='utils', description='Utility commands / Functions')
async def utils(ctx):
    """Utility command group. Call subcommands like `-utils ping`."""
    if ctx.invoked_subcommand is None:
        await ctx.send('Available utils subcommands: ping, greet')

@utils.command()
async def ping(ctx):
    '''Responds with the bot latency! Use to test if the bot is responsive.'''
    # Latency is returned in seconds, multiply by 1000 for milliseconds
    await ctx.send(f'Pong! {round(bot.latency * 1000, 2)}ms')

@utils.command()
async def greet(ctx):
    '''Sends a greeting message to the user.'''
    await ctx.send('Greetings! How can I help you today? 👋')

@utils.command()
async def echo(ctx, *, message):
    '''Echoes the provided message back to the user.'''
    await ctx.send(message)
    await ctx.message.delete()


@bot.group(name='grave', description='Death logging and obituary commands', aliases=['g'])
async def grave(ctx):
    """Graveyard command group. Call subcommands like `-graveyard death`."""
    if ctx.invoked_subcommand is None:
        await ctx.send('Available graveyard subcommands: death, obit')

@grave.command(name='death', aliases=['die', 'd'])
async def death(ctx, *args):
    '''
    Logs a death adding a poor soul to the graveyard.
    :args Optional first arg is the id (mention or digits). If omitted, uses the command invoker. Any remaining args are joined as the reason.
    '''
    # IMPORTANT: Replace with your actual death channel ID
    death_channel_id = 1422284082955685888
    death_channel = bot.get_channel(death_channel_id)
    if not death_channel:
        await ctx.send(f"Error: Death channel with ID {death_channel_id} not found.")
        return

    # Determine target user_id_str and reason
    if not args:
        # Case 1: No arguments - use invoker's ID and no reason
        user_id_str = str(ctx.author.id)
        reason = None
    else:
        first = args[0]
        if first == '0' or first.startswith('<@') or first.isdigit():
            # Case 2: First argument is an ID/mention ('0' or digits)
            user_id_str = first
            reason = ' '.join(args[1:]) if len(args) > 1 else None
        else:
            # Case 3: No ID provided (first arg is part of reason) - use invoker's ID
            user_id_str = str(ctx.author.id)
            reason = ' '.join(args)

    # Clean up the ID string to only contain digits if it was a mention
    digits = ''.join(ch for ch in user_id_str if ch.isdigit())
    if not digits:
        # If it was just '0', keep it as '0'
        final_user_id = '0' if user_id_str == '0' else str(ctx.author.id)
    else:
        final_user_id = digits

    # Increment the death count and log the death using the database
    c = bot.db.cursor()
    # Get the next sequential death number (cntr)
    c.execute('SELECT MAX(cntr) FROM death_log')
    row = c.fetchone()
    num = (row[0] if row and row[0] is not None else 0) + 1

    # Insert: letting log_id AUTOINCREMENT, storing user_id, cntr, and reason
    c.execute('INSERT INTO death_log(id, cntr, reason) VALUES (?,?,?)', (final_user_id, num, reason))
    bot.db.commit()

    # Notify channel / user
    if final_user_id == '0':
        await death_channel.send(f'💀 **Death #{num}** - Anonymous\nReason: {reason or "Unknown cause."}')
        await ctx.send('A new soul has entered the graveyard anonymously.')
        print('Death logged and posted.')
    else:
        # try to mention the user
        mention = f'<@{final_user_id}>'

        if reason:
            await death_channel.send(f'💀 **Death #{num}** - You have met a terrible fate, {mention}.\nReason: {reason}')
        else:
            await death_channel.send(f'💀 **Death #{num}** - You have met a terrible fate, {mention}.')

        await ctx.send('A new soul has entered the graveyard.')


@grave.command(name = 'obit', aliases=['obituary', 'death_log', 'deaths', 'log', 'l'])
async def obit(ctx, *args):
    '''
    Retrieves and sends the obituary for a specific user.
    :args The ID of the user whose obituary is to be retrieved. If None, retrieves the log for the command invoker.
    Use -1 to get the entire log as a file.
    Use 0 to get logs for generic/anonymous deaths.
    '''
    # Determine the target user_id for query
    if not args:
        user_id = str(ctx.author.id)
    else:
        user_id = args[0]

    # Normalize user lookup: prefer digits extracted from mention or id
    digits = ''.join(ch for ch in user_id if ch.isdigit())
    if digits:
        target_id_for_query = digits
    else:
        target_id_for_query = user_id  # Allows for literal '-1' or '0'

    c = bot.db.cursor()

    # Special case: Entire Log (-1)
    if target_id_for_query == '-1':
        # Retrieve all columns. id is now log_id, but the user_id is the second column
        c.execute('SELECT id, cntr, reason FROM death_log ORDER BY cntr')
        rows = c.fetchall()
        if not rows:
            await ctx.send('No death logs found. (The graveyard is empty.)')
            return

        lines = []
        for r in rows:
            # r[0] is user_id, r[1] is cntr, r[2] is reason
            lines.append(f'[{r[1]}] User ID: {r[0]} | Reason: {r[2] or "No reason"}')

        content = '\n'.join(lines)
        fp = io.BytesIO(content.encode('utf-8'))
        await ctx.send('Here is the full death log.', file=discord.File(fp, filename='death_log.txt'))
        return

    # Special case: Anonymous Logs (0)
    elif target_id_for_query == '0':
        c.execute("SELECT cntr, reason FROM death_log WHERE id = '0' ORDER BY cntr")
        rows = c.fetchall()
        if not rows:
            await ctx.send('No anonymous death logs found.')
            return

        lines = [f'**{r[0]}** - {r[1] or "No reason"}' for r in rows]
        msg = discord.Embed(
            title='💀 Anonymous Death Logs (ID 0)',
            description='\n'.join(lines),
            color=discord.Color.dark_red()
        )
        msg.set_footer(text=f'Total Anonymous Deaths: {len(rows)}')
        await ctx.send(embed=msg)
        return

    # Regular User Lookup
    # Search by the exact user_id string
    c.execute('SELECT cntr, reason FROM death_log WHERE id = ? ORDER BY cntr DESC', (target_id_for_query,))
    rows = c.fetchall()

    if rows:
        user_logs_count = len(rows)
        # Get the first 50 entries (since they are ordered descending by cntr, this is the most recent 50)
        recent_rows = rows[:10]
        desc_lines = [f'**{r[0]}** - {r[1] or "Rest In Peace :("}' for r in recent_rows]
        reversed_desc_lines = list(reversed(desc_lines))  # Show oldest first in the embed
        print(desc_lines)
        # try to resolve a nice username for the embed title
        title_user = target_id_for_query
        try:
            fetched = await bot.fetch_user(int(target_id_for_query))
            title_user = str(fetched)
        except Exception:
            pass  # Use the digits if fetching user fails

        msg = discord.Embed(
            title=f'💀 Obituary for {title_user}',
            description='\n'.join(desc_lines),
            color=discord.Color.red()
        )
        msg.set_footer(
            text=f'Total deaths: {user_logs_count}.\n Showing last {len(recent_rows)} entries. | May they rest in peace.')
        await ctx.send(embed=msg)

        if user_logs_count >= 100:
            await ctx.send('Holy smokes, that is a lot of deaths... you might want to stop dying! 🤯')
    else:
        await ctx.send('Hmmmm, they don\'t seem dead yet... keep trying! 😉')


# ---

@bot.group(name='snipe', description='Message sniping commands')
async def snipe(ctx):
    """Snipe command group. Call subcommands like `-snipe delete`."""
    if ctx.invoked_subcommand is None:
        await ctx.send('Available snipe subcommands: delete')

snipe_messages_delete = {}
@bot.event
async def on_message_delete(message):
    # Ignore DMs or messages without content (e.g., embeds, system messages)
    if message.guild and message.content:
        snipe_messages_delete[message.channel.id] = (
            message.content,
            message.author,
            message.created_at
        )
        # NOTE: Do NOT use an asyncio.sleep here. The message is stored, and
        # a separate mechanism (or time check in snipe command) should handle deletion/expiration.
        # Adding a sleep here delays the processing of all future events until the sleep completes,
        # which can break the bot entirely.


@snipe.command()
async def snipe(ctx):
    '''Retrieves the last deleted message in the channel.'''
    sniped_data = snipe_messages_delete.get(ctx.channel.id)

    if sniped_data:
        content, author, timestamp = sniped_data

        # Check if the message is too old (e.g., older than 60 seconds - ADJUST AS NEEDED)
        # from datetime import datetime, timezone
        # if (datetime.now(timezone.utc) - timestamp).total_seconds() > 60:
        #     del snipe_messages_delete[ctx.channel.id]
        #     await ctx.send('The message was too old to snipe.')
        #     return

        embed = discord.Embed(
            description=content,
            color=discord.Color.purple(),
            timestamp=timestamp
        )
        embed.set_author(name=str(author), icon_url=author.avatar.url if author.avatar else None)
        embed.set_footer(text=f'Sniped by {ctx.author.name}')

        # Remove the message immediately after sniping so it can't be sniped again
        del snipe_messages_delete[ctx.channel.id]

        await ctx.send(embed=embed)
    else:
        await ctx.send('No recently deleted messages to snipe. 😔')


# ---

@bot.group(name='minecraft', description='Minecraft server related commands')
async def minecraft(ctx):
    """Minecraft command group. Call subcommands like `-minecraft status`."""
    if ctx.invoked_subcommand is None:
        await ctx.send('Available minecraft subcommands: status')

async def get_server_status():
    """Query the Minecraft server and return status information."""
    try:
        # Resolve MINECRAFT_SERVER here to handle the case where the env var is not set,
        # though it should be set for the bot to run.
        server_address = MINECRAFT_SERVER
        if not server_address:
            raise ValueError("MINECRAFT_SERVER environment variable is not set.")

        server = JavaServer.lookup(server_address)
        # Use asyncio.to_thread for blocking network calls to keep the main event loop responsive
        status = await asyncio.to_thread(server.status)

        return {
            'online': True,
            'players_online': status.players.online,
            'players_max': status.players.max,
            # Ensure the sample exists before trying to iterate
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


@minecraft.command(name='mstatus',
             description='Get the current status of the Minecraft server')  # Renaming from 'status' to 'mstatus' to avoid conflict with potential slash command alias
async def mstatus(ctx):
    """Command to check Minecraft server status."""
    # This is a prefix command, not a slash command, so it takes a context (ctx)
    await ctx.send('Checking server status... one moment.')

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
            # Clean up MOTD to be more readable in Discord if it contains formatting codes
            import re
            clean_motd = re.sub(r'§[0-9a-fk-or]', '', motd_text)  # Remove Minecraft color/format codes
            embed.add_field(
                name='MOTD',
                value=clean_motd[:1024],  # Discord field limit
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
            value='Server is **offline** or unreachable',
            inline=False
        )

        embed.set_footer(text=f"Error: {status_data.get('error', 'Unknown error')}")

    await ctx.send(embed=embed)


# ---

# NOTE: The provided slash command `status` (which takes an interaction) is now separate from the prefix command `mstatus`.
# The slash command needs to be properly registered with `@bot.tree.command()`.
# I'll update the provided slash command 'status' to use the correct decorator for the updated discord.py v2.x command structure.

@bot.tree.command(name='status', description='Get the current status of the Minecraft server')
async def status_slash(interaction: discord.Interaction):  # Renamed function to avoid conflict with the one above
    """Slash command to check Minecraft server status."""
    await interaction.response.defer()  # Defer the response to handle the potential latency

    status_data = await get_server_status()

    # The rest of the slash command logic is correct and remains as is
    # ... (status_data processing as in your original code) ...
    if status_data['online']:
        embed = discord.Embed(
            title='🟢 Minecraft Server Status',
            description=f'**{MINECRAFT_SERVER}**',
            color=discord.Color.green()
        )
        embed.add_field(name='Players Online', value=f"{status_data['players_online']}/{status_data['players_max']}",
                        inline=True)
        embed.add_field(name='Version', value=status_data['version'], inline=True)
        embed.add_field(name='Latency', value=f"{status_data['latency']:.1f}ms", inline=True)
        if status_data['player_list']:
            player_names = '\n'.join(status_data['player_list'])
            embed.add_field(name='Players', value=player_names, inline=False)
        elif status_data['players_online'] > 0:
            embed.add_field(name='Players', value='_Player list hidden by server_', inline=False)
        motd_text = str(status_data['motd'])
        if motd_text:
            import re
            clean_motd = re.sub(r'§[0-9a-fk-or]', '', motd_text)
            embed.add_field(name='MOTD', value=clean_motd[:1024], inline=False)
        embed.set_footer(text='Server is online')
    else:
        embed = discord.Embed(
            title='🔴 Minecraft Server Status',
            description=f'**{MINECRAFT_SERVER}**',
            color=discord.Color.red()
        )
        embed.add_field(name='Status', value='Server is offline or unreachable', inline=False)
        embed.set_footer(text=f"Error: {status_data.get('error', 'Unknown error')}")

    await interaction.followup.send(embed=embed)


@tasks.loop(minutes=5)
async def update_voice_channel():
    """Background task to update voice channel name with player count."""
    try:
        # VOICE_CHANNEL is a string from env, ensure it's converted to int for get_channel
        channel_id = int(VOICE_CHANNEL)
        channel = bot.get_channel(channel_id)

        if not channel:
            print(f'Voice channel {VOICE_CHANNEL} not found')
            return

        # Check if the channel is actually a voice channel (2) to avoid errors
        if channel.type != discord.ChannelType.voice:
            print(f'Channel {VOICE_CHANNEL} is not a voice channel. Skipping update.')
            update_voice_channel.stop()  # Stop the task if it's the wrong channel type
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
        # Check for 429 (rate limit) or 403 (forbidden/permissions)
        if e.status == 429:
            print(f'Rate limited while updating voice channel name: {e}')
        elif e.status == 403:
            print(f'Permission denied to edit voice channel name: {e}')
            # Consider stopping the loop if permissions are missing
            # update_voice_channel.stop()
        else:
            print(f'Failed to update voice channel (HTTP error): {e}')

    except ValueError:
        print(f'Error: VOICE_CHANNEL environment variable "{VOICE_CHANNEL}" is not a valid integer ID.')
        update_voice_channel.stop()

    except Exception as e:
        print(f'Error in voice channel update task: {e}')


@update_voice_channel.before_loop
async def before_update_voice_channel():
    """Wait for the bot to be ready before starting the task."""
    await bot.wait_until_ready()


@bot.group(name='voice', description='Voice channel commands')
async def voice(ctx):
    """Voice command group. Call subcommands like `-voice join`."""
    if ctx.invoked_subcommand is None:
        await ctx.send('Available voice subcommands: join, leave, play')

@voice.command()
async def join(ctx, channel):
    '''Joins a voice channel specified by ID or name.'''
    voice_channel = None

    # Try to get the channel by ID first
    if channel.isdigit():
        voice_channel = bot.get_channel(int(channel))
    else:
        # Search for the channel by name in the guild
        for ch in ctx.guild.voice_channels:
            if ch.name == channel:
                voice_channel = ch
                break

    if voice_channel is None:
        await ctx.send(f"Voice channel '{channel}' not found.")
        return

    try:
        await voice_channel.connect()
        await ctx.send(f"Joined voice channel: {voice_channel.name}")
    except Exception as e:
        await ctx.send(f"Failed to join voice channel: {e}")

@voice.command()
async def leave(ctx):
    '''Leaves the current voice channel.'''
    if ctx.voice_client is not None:
        await ctx.voice_client.disconnect()
        await ctx.send("Left the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

@voice.command()
async def play(ctx, url, youtube_dl=None):
    '''WIP -- -- Plays audio from a given URL in the voice channel.'''
    if ctx.voice_client is None:
        await ctx.send("I'm not in a voice channel. Use -join command first.")
        return

    try:
        # Using youtube_dl to extract audio
        from youtube_dl import YoutubeDL

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']

        source = await discord.FFmpegOpusAudio.from_probe(audio_url)
        ctx.voice_client.play(source)
        await ctx.send(f'Now playing audio from: {url}')
    except Exception as e:
        await ctx.send(f"Failed to play audio: {e}")





if __name__ == '__main__':
    load_dotenv()
    if not os.getenv('DISCORD_TOKEN'):
        print("Error: DISCORD_TOKEN not found in environment variables. Bot cannot start.")
    else:
        try:
            bot.run(os.getenv('DISCORD_TOKEN'))
        except discord.errors.LoginFailure:
            print("Error: Improper token has been passed. Please check your DISCORD_TOKEN.")
        except KeyboardInterrupt:
            print("Bot stopped by user.")
        except Exception as e:
            print(f"An unexpected error occurred during bot execution: {e}")