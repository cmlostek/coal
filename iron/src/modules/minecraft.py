"""modules/minecraft.py – Minecraft server status (Cog version)."""
import os
import re
import asyncio
import discord
from discord.ext import commands, tasks
from mcstatus import JavaServer

MINECRAFT_IP   = os.getenv('MINECRAFT_SERVER_IP', '')
MINECRAFT_PORT = int(os.getenv('MINECRAFT_SERVER_PORT', '25565'))
VOICE_CHANNEL  = os.getenv('VOICE_CHANNEL', '')


class Minecraft(commands.Cog):
    """Minecraft server status and voice channel integration."""

    def __init__(self, bot):
        self.bot = bot
        if VOICE_CHANNEL:
            self.update_vc.start()

    def cog_unload(self):
        self.update_vc.cancel()

    async def _get_status(self) -> dict:
        try:
            server = JavaServer.lookup(f'{MINECRAFT_IP}:{MINECRAFT_PORT}')
            st = await asyncio.to_thread(server.status)
            return {
                'online': True,
                'players_online': st.players.online,
                'players_max': st.players.max,
                'player_list': [p.name for p in (st.players.sample or [])],
                'version': st.version.name,
                'latency': st.latency,
                'motd': str(st.description),
            }
        except Exception as exc:
            return {'online': False, 'error': str(exc)}

    @tasks.loop(minutes=5)
    async def update_vc(self):
        """Update voice channel name with player count every 5 minutes."""
        try:
            cid = int(VOICE_CHANNEL)
            ch  = self.bot.get_channel(cid)
            if not ch or ch.type != discord.ChannelType.voice:
                return

            st = await self._get_status()
            new_name = (f"Players: {st['players_online']}/{st['players_max']}"
                        if st['online'] else 'Server: Offline')

            if ch.name != new_name:
                await ch.edit(name=new_name)
        except discord.HTTPException as exc:
            if exc.status not in (403, 429):
                raise
        except Exception:
            pass

    @update_vc.before_loop
    async def before_update_vc(self):
        await self.bot.wait_until_ready()

    @commands.command(name='status')
    async def status(self, ctx):
        """Show Minecraft server status."""
        if not MINECRAFT_IP:
            return await ctx.send('❌ MINECRAFT_SERVER_IP is not configured.')

        async with ctx.typing():
            st = await self._get_status()

        if st['online']:
            embed = discord.Embed(
                title='🟢 Minecraft Server',
                description=f'**{MINECRAFT_IP}**',
                color=discord.Color.green(),
            )
            embed.add_field(name='Players', value=f'{st["players_online"]}/{st["players_max"]}', inline=True)
            embed.add_field(name='Version', value=st['version'], inline=True)
            embed.add_field(name='Latency', value=f'{st["latency"]:.1f}ms', inline=True)
            if st['player_list']:
                embed.add_field(name='Online', value='\n'.join(st['player_list']), inline=False)
            clean_motd = re.sub(r'§[0-9a-fk-or]', '', st['motd'])
            if clean_motd.strip():
                embed.add_field(name='MOTD', value=clean_motd[:1024], inline=False)
        else:
            embed = discord.Embed(
                title='🔴 Minecraft Server — Offline',
                description=f'**{MINECRAFT_IP}**',
                color=discord.Color.red(),
            )
            embed.set_footer(text=st.get('error', 'Server unreachable'))

        await ctx.send(embed=embed)

    @commands.command(name='join')
    async def join(self, ctx, channel: str):
        """Join a voice channel by ID or name."""
        vc = (self.bot.get_channel(int(channel))
              if channel.isdigit()
              else next((c for c in ctx.guild.voice_channels if c.name == channel), None))
        if not vc:
            return await ctx.send(f"Voice channel `{channel}` not found.")
        try:
            await vc.connect()
            await ctx.send(f'Joined **{vc.name}**.')
        except Exception as exc:
            await ctx.send(f'Failed to join: {exc}')

    @commands.command(name='leave')
    async def leave(self, ctx):
        """Leave the current voice channel."""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send('Left the voice channel.')
        else:
            await ctx.send("I'm not in a voice channel.")


async def setup(bot):
    await bot.add_cog(Minecraft(bot))
