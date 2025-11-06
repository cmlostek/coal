"""Minecraft server status commands module"""

import os
import re
import asyncio
import discord
from discord.ext import commands, tasks
from mcstatus import JavaServer


def setup(bot):
    """Setup function to register commands with the bot"""

    MINECRAFT_SERVER_IP = os.getenv('MINECRAFT_SERVER_IP')
    MINECRAFT_SERVER_PORT = os.getenv('MINECRAFT_SERVER_PORT')
    VOICE_CHANNEL = 1422645848923176990  # Replace this with your test channel ID

    async def get_server_status():
        """Query the Minecraft server and return status information."""
        try:
            server_address = MINECRAFT_SERVER_IP
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

    @bot.command(name='status', description='Get the current status of the Minecraft server')
    async def status(ctx):
        """Command to check Minecraft server status."""
        await ctx.send('Checking server status... one moment.')

        status_data = await get_server_status()

        if status_data['online']:
            # Create embed for online server
            embed = discord.Embed(
                title='🟢 Minecraft Server Status',
                description=f'**{MINECRAFT_SERVER_IP}**',
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
                description=f'**{MINECRAFT_SERVER_IP}**',
                color=discord.Color.red()
            )

            embed.add_field(
                name='Status',
                value='Server is **offline** or unreachable',
                inline=False
            )

            embed.set_footer(text=f"Error: {status_data.get('error', 'Unknown error')}")

        await ctx.send(embed=embed)

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

    # Start the voice channel update task
    if VOICE_CHANNEL:
        update_voice_channel.start()
    else:
        print('No voice channel ID configured - skipping auto-update')

    @bot.command()
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

    @bot.command()
    async def leave(ctx):
        '''Leaves the current voice channel.'''
        if ctx.voice_client is not None:
            await ctx.voice_client.disconnect()
            await ctx.send("Left the voice channel.")
        else:
            await ctx.send("I'm not in a voice channel.")