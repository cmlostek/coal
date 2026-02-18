"""modules/utils.py – General utility commands (Cog version)."""
import re
import io
import asyncio
import datetime
from PIL import Image
import discord
from discord.ext import commands


class Utils(commands.Cog):
    """General utility and moderation tools."""

    def __init__(self, bot):
        self.bot = bot
        self._snipe: dict[int, tuple] = {}  # channel_id → (content, author, timestamp)

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild and message.content:
            self._snipe[message.channel.id] = (message.content, message.author, message.created_at)

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name='help')
    async def help(self, ctx):
        """Show all available commands."""
        embed = discord.Embed(
            title='Iron Bot — Command Reference',
            description='Prefix: `!` · `-` · `?`',
            color=0x5865F2,
        )
        embed.add_field(
            name='⚙️ Setup',
            value='`!setup` · `!setup view` · `!setup location` · `!setup timezone` · `!setup time`',
            inline=False,
        )
        embed.add_field(
            name='📋 Tasks',
            value='`!task add/list/done/delete/view` · `!today` · `!week`',
            inline=False,
        )
        embed.add_field(
            name='📚 Assignments',
            value='`!assign add/list/done/delete/courses`',
            inline=False,
        )
        embed.add_field(
            name='⏰ Reminders',
            value='`!remind <time> to <message>` · `!reminders` · `!reminders delete <id>`',
            inline=False,
        )
        embed.add_field(
            name='🏷️ Tags',
            value='`!tag <name>` · `!tag create/edit/delete/list/info/raw/search/transfer`',
            inline=False,
        )
        embed.add_field(
            name='📅 Calendar',
            value='`!calendar setup/code/today/week/next/status/unlink`',
            inline=False,
        )
        embed.add_field(
            name='🎓 Canvas',
            value='`!canvas setup/courses/assignments/grades/sync/status/unlink`',
            inline=False,
        )
        embed.add_field(
            name='📧 Email',
            value='`!email setup/check/sleep/status/unlink`',
            inline=False,
        )
        embed.add_field(
            name='🌤️ Weather',
            value='`!weather [city]` · `!forecast [city]`',
            inline=False,
        )
        embed.add_field(
            name='📊 Stats',
            value='`!stats` · `!stats week` · `!stats month` · `!stats leaderboard`',
            inline=False,
        )
        embed.add_field(
            name='💰 Economy',
            value='`!balance` · `!daily` · `!work` · `!coinflip` · `!slots` · `!roll` · `!give` · `!rob`',
            inline=False,
        )
        embed.add_field(
            name='⚡ Levels',
            value='`!rank` · `!top`',
            inline=False,
        )
        embed.add_field(
            name='💀 Graveyard',
            value='`!death` · `!revive` · `!obit`',
            inline=False,
        )
        embed.add_field(
            name='🎮 Minecraft',
            value='`!status` · `!join` · `!leave`',
            inline=False,
        )
        embed.add_field(
            name='🔧 Utility',
            value='`!ping` · `!whois` · `!color` · `!snipe` · `!echo` · `!schedule`',
            inline=False,
        )
        embed.set_footer(text='Use !setup to configure channels, timezone, and connected services.')
        await ctx.send(embed=embed)

    @commands.command(name='ping')
    async def ping(self, ctx):
        """Check bot latency."""
        await ctx.send(
            embed=discord.Embed(
                description=f'🏓 Pong! **{round(self.bot.latency * 1000, 2)} ms**',
                color=discord.Color.green(),
            )
        )

    @commands.command(name='echo')
    async def echo(self, ctx, *, message: str):
        """Echo a message and delete the original."""
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(message)

    @commands.command(name='color', aliases=['colour'])
    async def color(self, ctx, hexcode: str):
        """Show a colour swatch. Example: `!color #5865F2`"""
        if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', hexcode):
            return await ctx.send('❌ Invalid hex code. Example: `#5865F2`')
        img = Image.new('RGB', (200, 200), hexcode)
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        embed = discord.Embed(
            description=f'Colour: `{hexcode}`',
            color=int(hexcode.replace('#', '0x'), 16),
        )
        embed.set_thumbnail(url='attachment://color.png')
        await ctx.send(file=discord.File(buf, 'color.png'), embed=embed)

    @commands.command(name='whois', aliases=['userinfo', 'uinfo', 'who'])
    async def whois(self, ctx, user: discord.Member = None):
        """Display information about a user."""
        user = user or ctx.author
        embed = discord.Embed(title=f'👤 {user}', color=discord.Color.blue())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name='Username', value=str(user), inline=True)
        embed.add_field(name='ID', value=str(user.id), inline=True)
        embed.add_field(name='Account Created', value=user.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name='Joined Server', value=user.joined_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name='Top Role', value=user.top_role.mention, inline=True)
        roles = [r.mention for r in user.roles if r.name != '@everyone']
        embed.add_field(name=f'Roles ({len(roles)})', value=' '.join(roles[:10]) or 'None', inline=False)
        embed.set_footer(text=f'Requested by {ctx.author}')
        await ctx.send(embed=embed)

    @commands.command(name='snipe')
    async def snipe(self, ctx):
        """Retrieve the last deleted message in this channel."""
        data = self._snipe.get(ctx.channel.id)
        if not data:
            return await ctx.send('No recently deleted messages to snipe.')
        content, author, ts = data
        del self._snipe[ctx.channel.id]
        embed = discord.Embed(description=content, color=discord.Color.purple(), timestamp=ts)
        embed.set_author(name=str(author), icon_url=author.display_avatar.url)
        embed.set_footer(text=f'Sniped by {ctx.author}')
        await ctx.send(embed=embed)

    @commands.command(name='schedule')
    async def schedule(self, ctx, channel: discord.TextChannel, date: str, time: str, *, message: str):
        """
        Schedule a message.

        Usage: `!schedule #channel 2025-05-01 14:30 Hello world!`
        """
        try:
            dt = datetime.datetime.strptime(f'{date} {time}', '%Y-%m-%d %H:%M')
        except ValueError:
            return await ctx.send('❌ Invalid format. Use `YYYY-MM-DD HH:MM`.')
        now = datetime.datetime.now()
        if dt <= now:
            return await ctx.send('❌ Cannot schedule messages in the past.')
        delay = (dt - now).total_seconds()

        async def _send():
            await asyncio.sleep(delay)
            try:
                await channel.send(message)
            except Exception:
                pass

        asyncio.create_task(_send())
        embed = discord.Embed(
            description=f'⏰ Scheduled to {channel.mention} at `{dt.strftime("%Y-%m-%d %H:%M")}`',
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Utils(bot))
