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
