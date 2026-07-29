"""
modules/stats.py – Task & assignment completion statistics with matplotlib graphs,
plus message and voice-activity tracking.

Commands
────────
  !stats             – your completion dashboard with graph (incl. message/voice rank)
  !stats week        – last 7 days bar chart
  !stats month       – last 30 days chart
  !stats leaderboard – paginated server leaderboard (Tasks / Messages / Voice)
"""
import discord
from discord.ext import commands, tasks
import asyncio
import io
import logging
import time
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)


def _fmt_duration(seconds: int) -> str:
    """Format a number of seconds as a compact human-readable duration."""
    seconds = int(seconds)
    if seconds < 60:
        return f'{seconds}s'
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f'{days}d')
    if hours:
        parts.append(f'{hours}h')
    if minutes and not days:
        parts.append(f'{minutes}m')
    return ' '.join(parts) if parts else f'{sec}s'


def _xp_needed(level: int) -> int:
    """XP required to clear a given level (mirrors levels.py)."""
    return int(10 * (1.5 ** (level - 1)))


def _level_total_xp(level: int, xp: int) -> int:
    return sum(_xp_needed(l) for l in range(1, level)) + xp


def _requires_matplotlib():
    try:
        import matplotlib
        return True
    except ImportError:
        return False


async def _gen_chart(labels, tasks_done, on_time, title: str) -> io.BytesIO:
    """Generate a bar chart and return it as a BytesIO PNG."""
    def _draw():
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np

        x = np.arange(len(labels))
        width = 0.35

        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#2b2d31')
        ax.set_facecolor('#2b2d31')

        bars1 = ax.bar(x - width / 2, tasks_done, width, label='Completed', color='#5865F2', zorder=3)
        bars2 = ax.bar(x + width / 2, on_time, width, label='On Time', color='#57F287', zorder=3)

        ax.set_xlabel('Date', color='white')
        ax.set_ylabel('Tasks', color='white')
        ax.set_title(title, color='white', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha='right', color='white', fontsize=8)
        ax.tick_params(colors='white')
        ax.spines[:].set_color('#40444b')
        ax.yaxis.grid(True, color='#40444b', zorder=0)
        ax.legend(facecolor='#40444b', labelcolor='white')

        for bar in bars1:
            h = bar.get_height()
            if h:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.05, str(int(h)),
                        ha='center', va='bottom', color='white', fontsize=8)
        for bar in bars2:
            h = bar.get_height()
            if h:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.05, str(int(h)),
                        ha='center', va='bottom', color='white', fontsize=8)

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_draw)


class Stats(commands.Cog):
    """Productivity statistics and completion graphs."""

    def __init__(self, bot):
        self.bot = bot
        # (guild_id, user_id) -> monotonic timestamp when the current voice
        # session started (or was last checkpointed).
        self._voice_sessions: dict[tuple[int, int], float] = {}

    async def cog_load(self):
        # Seed sessions for anyone already in a voice channel when the cog loads.
        now = time.monotonic()
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        self._voice_sessions[(guild.id, member.id)] = now
        self._voice_checkpoint.start()

    async def cog_unload(self):
        self._voice_checkpoint.cancel()
        # Persist whatever voice time has accrued so a reload/shutdown keeps it.
        await self._flush_voice_sessions()

    # ── Activity tracking ─────────────────────────────────────────────────────

    async def _add_messages(self, user_id: int, guild_id: int, amount: int = 1):
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO activity_stats (user_id, guild_id, messages)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, guild_id)
                   DO UPDATE SET messages = messages + excluded.messages''',
                (user_id, guild_id, amount),
            )
        await self.bot.db.commit()

    async def _add_voice_seconds(self, user_id: int, guild_id: int, amount: int):
        if amount <= 0:
            return
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO activity_stats (user_id, guild_id, voice_seconds)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, guild_id)
                   DO UPDATE SET voice_seconds = voice_seconds + excluded.voice_seconds''',
                (user_id, guild_id, amount),
            )
        await self.bot.db.commit()

    async def _flush_voice_sessions(self):
        """Credit accrued time for every active session and reset its start."""
        now = time.monotonic()
        for (guild_id, user_id), started in list(self._voice_sessions.items()):
            elapsed = int(now - started)
            if elapsed > 0:
                await self._add_voice_seconds(user_id, guild_id, elapsed)
                self._voice_sessions[(guild_id, user_id)] = now

    @tasks.loop(minutes=5)
    async def _voice_checkpoint(self):
        await self._flush_voice_sessions()

    @_voice_checkpoint.before_loop
    async def _before_checkpoint(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await self._add_messages(message.author.id, message.guild.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot or not member.guild:
            return
        key = (member.guild.id, member.id)
        # Joined a voice channel (from nothing).
        if before.channel is None and after.channel is not None:
            self._voice_sessions[key] = time.monotonic()
        # Left voice entirely.
        elif before.channel is not None and after.channel is None:
            started = self._voice_sessions.pop(key, None)
            if started is not None:
                await self._add_voice_seconds(member.id, member.guild.id,
                                              int(time.monotonic() - started))
        # Moved between channels / mute-deafen change: keep the session running.
        elif after.channel is not None and key not in self._voice_sessions:
            self._voice_sessions[key] = time.monotonic()

    async def _get_activity(self, user_id: int, guild_id: int):
        """Return (messages, voice_seconds) for a user, including live session."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT messages, voice_seconds FROM activity_stats WHERE user_id=? AND guild_id=?',
                (user_id, guild_id),
            )
            row = await cur.fetchone()
        messages = row['messages'] if row else 0
        voice = row['voice_seconds'] if row else 0
        started = self._voice_sessions.get((guild_id, user_id))
        if started is not None:
            voice += int(time.monotonic() - started)
        return messages, voice

    async def _activity_rank(self, user_id: int, guild_id: int, column: str):
        """1-based rank of a user for the given activity column (None if unranked)."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                f'''SELECT user_id, {column} AS val FROM activity_stats
                    WHERE guild_id=? AND {column} > 0
                    ORDER BY {column} DESC''',
                (guild_id,),
            )
            rows = await cur.fetchall()
        for i, r in enumerate(rows, start=1):
            if r['user_id'] == user_id:
                return i, len(rows)
        return None, len(rows)

    async def _get_stats(self, user_id: int, guild_id: int, days: int):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT date, tasks_completed, tasks_on_time, tasks_late, assignments_completed
                   FROM task_stats
                   WHERE user_id = ? AND guild_id = ? AND date >= ?
                   ORDER BY date ASC''',
                (user_id, guild_id, cutoff),
            )
            return await cur.fetchall()

    @commands.group(name='stats', invoke_without_command=True)
    async def stats(self, ctx):
        """View your productivity stats and graph."""
        rows = await self._get_stats(ctx.author.id, ctx.guild.id, 14)

        total_done  = sum(r['tasks_completed'] for r in rows)
        total_ot    = sum(r['tasks_on_time'] for r in rows)
        total_late  = sum(r['tasks_late'] for r in rows)
        total_asgn  = sum(r['assignments_completed'] for r in rows)
        rate = round(total_ot / total_done * 100, 1) if total_done else 0

        # Pending counts
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE user_id=? AND guild_id=? AND status='pending'",
                (ctx.author.id, ctx.guild.id),
            )
            pending_tasks = (await cur.fetchone())['cnt']
            await cur.execute(
                "SELECT COUNT(*) as cnt FROM assignments WHERE user_id=? AND guild_id=? AND status='pending'",
                (ctx.author.id, ctx.guild.id),
            )
            pending_asgn = (await cur.fetchone())['cnt']

        # Activity totals + server ranks
        messages, voice = await self._get_activity(ctx.author.id, ctx.guild.id)
        msg_rank, msg_total = await self._activity_rank(ctx.author.id, ctx.guild.id, 'messages')
        voice_rank, voice_total = await self._activity_rank(ctx.author.id, ctx.guild.id, 'voice_seconds')
        msg_val = f'{messages:,}' + (f' (#{msg_rank}/{msg_total})' if msg_rank else '')
        voice_val = _fmt_duration(voice) + (f' (#{voice_rank}/{voice_total})' if voice_rank else '')

        embed = discord.Embed(
            title=f'📊 Stats — {ctx.author.display_name}',
            description=f'Last **14 days** • On-time rate: **{rate}%**',
            color=0x1ABC9C,
        )
        embed.add_field(name='✅ Tasks Completed', value=str(total_done), inline=True)
        embed.add_field(name='🟢 On Time', value=str(total_ot), inline=True)
        embed.add_field(name='🔴 Late', value=str(total_late), inline=True)
        embed.add_field(name='📚 Assignments Done', value=str(total_asgn), inline=True)
        embed.add_field(name='⬜ Pending Tasks', value=str(pending_tasks), inline=True)
        embed.add_field(name='⬜ Pending Assigns', value=str(pending_asgn), inline=True)
        embed.add_field(name='💬 Messages', value=msg_val, inline=True)
        embed.add_field(name='🎙️ Voice Time', value=voice_val, inline=True)
        embed.add_field(name='​', value='​', inline=True)

        if not rows:
            embed.set_footer(text='Complete tasks with !task done to start tracking stats.')
            return await ctx.send(embed=embed)

        if not _requires_matplotlib():
            embed.set_footer(text='Install matplotlib for charts: pip install matplotlib')
            return await ctx.send(embed=embed)

        labels = [r['date'][5:] for r in rows]  # MM-DD
        done   = [r['tasks_completed'] for r in rows]
        ot     = [r['tasks_on_time'] for r in rows]

        async with ctx.typing():
            buf = await _gen_chart(labels, done, ot, f'{ctx.author.display_name} — Task Completion (14 days)')

        file = discord.File(buf, filename='stats.png')
        embed.set_image(url='attachment://stats.png')
        await ctx.send(embed=embed, file=file)

    @stats.command(name='week')
    async def stats_week(self, ctx):
        """Bar chart for the last 7 days."""
        rows = await self._get_stats(ctx.author.id, ctx.guild.id, 7)
        if not rows:
            return await ctx.send('No stats data for the last 7 days. Complete some tasks first!')

        if not _requires_matplotlib():
            return await ctx.send('Install matplotlib for charts: `pip install matplotlib`')

        labels = [r['date'][5:] for r in rows]
        done   = [r['tasks_completed'] for r in rows]
        ot     = [r['tasks_on_time'] for r in rows]

        async with ctx.typing():
            buf = await _gen_chart(labels, done, ot, f'{ctx.author.display_name} — Last 7 Days')

        embed = discord.Embed(title='📊 7-Day Task Stats', color=0x1ABC9C)
        embed.set_image(url='attachment://stats.png')
        await ctx.send(embed=embed, file=discord.File(buf, 'stats.png'))

    @stats.command(name='month')
    async def stats_month(self, ctx):
        """Bar chart for the last 30 days."""
        rows = await self._get_stats(ctx.author.id, ctx.guild.id, 30)
        if not rows:
            return await ctx.send('No stats data for the last 30 days.')

        if not _requires_matplotlib():
            return await ctx.send('Install matplotlib for charts: `pip install matplotlib`')

        labels = [r['date'][5:] for r in rows]
        done   = [r['tasks_completed'] for r in rows]
        ot     = [r['tasks_on_time'] for r in rows]

        async with ctx.typing():
            buf = await _gen_chart(labels, done, ot, f'{ctx.author.display_name} — Last 30 Days')

        embed = discord.Embed(title='📊 30-Day Task Stats', color=0x1ABC9C)
        embed.set_image(url='attachment://stats.png')
        await ctx.send(embed=embed, file=discord.File(buf, 'stats.png'))

    # ── Leaderboard embed builders ────────────────────────────────────────────

    # Page order for the unified leaderboard view.
    PAGES = ['levels', 'economy', 'tasks', 'messages', 'voice']

    @staticmethod
    def _member_name(guild, user_id: int) -> str:
        member = guild.get_member(user_id)
        return member.display_name if member else f'User {user_id}'

    async def _levels_leaderboard_embed(self, guild) -> discord.Embed:
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT id, level, xp FROM levels ORDER BY level DESC, xp DESC LIMIT 10'
            )
            rows = await cur.fetchall()

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        if rows:
            lines = [f'{medals[i]} **{self._member_name(guild, r["id"])}** '
                     f'— Level {r["level"]} ({_level_total_xp(r["level"], r["xp"]):,} XP)'
                     for i, r in enumerate(rows)]
            desc = '\n'.join(lines)
        else:
            desc = 'No one has earned XP yet.'
        return discord.Embed(title='⚡ Level Leaderboard',
                             description=desc, color=0x3498DB)

    async def _economy_leaderboard_embed(self, guild) -> discord.Embed:
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT user_id, balance FROM balances ORDER BY balance DESC LIMIT 10'
            )
            rows = await cur.fetchall()

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        if rows:
            lines = [f'{medals[i]} **{self._member_name(guild, r["user_id"])}** '
                     f'— {r["balance"]:,} coins' for i, r in enumerate(rows)]
            desc = '\n'.join(lines)
        else:
            desc = 'No balances recorded yet.'
        return discord.Embed(title='💰 Wealth Leaderboard',
                             description=desc, color=0xF1C40F)

    async def _tasks_leaderboard_embed(self, guild) -> discord.Embed:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT user_id,
                          SUM(tasks_completed) as done,
                          SUM(tasks_on_time)   as ot
                   FROM task_stats
                   WHERE guild_id = ? AND date >= ?
                   GROUP BY user_id
                   HAVING done > 0
                   ORDER BY done DESC
                   LIMIT 10''',
                (guild.id, cutoff),
            )
            rows = await cur.fetchall()

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        if rows:
            lines = []
            for i, r in enumerate(rows):
                rate = round(r['ot'] / r['done'] * 100) if r['done'] else 0
                lines.append(f'{medals[i]} **{self._member_name(guild, r["user_id"])}** '
                             f'— {r["done"]} tasks ({rate}% on time)')
            desc = '\n'.join(lines)
        else:
            desc = 'No task data for this server yet.'
        return discord.Embed(title='🏆 Task Leaderboard — Last 30 Days',
                             description=desc, color=0xF1C40F)

    async def _messages_leaderboard_embed(self, guild) -> discord.Embed:
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT user_id, messages FROM activity_stats
                   WHERE guild_id = ? AND messages > 0
                   ORDER BY messages DESC LIMIT 10''',
                (guild.id,),
            )
            rows = await cur.fetchall()

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        if rows:
            lines = [f'{medals[i]} **{self._member_name(guild, r["user_id"])}** '
                     f'— {r["messages"]:,} messages' for i, r in enumerate(rows)]
            desc = '\n'.join(lines)
        else:
            desc = 'No message activity tracked yet.'
        return discord.Embed(title='💬 Message Leaderboard',
                             description=desc, color=0x5865F2)

    async def _voice_leaderboard_embed(self, guild) -> discord.Embed:
        # Flush live sessions first so the board reflects ongoing calls.
        await self._flush_voice_sessions()
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT user_id, voice_seconds FROM activity_stats
                   WHERE guild_id = ? AND voice_seconds > 0
                   ORDER BY voice_seconds DESC LIMIT 10''',
                (guild.id,),
            )
            rows = await cur.fetchall()

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        if rows:
            lines = [f'{medals[i]} **{self._member_name(guild, r["user_id"])}** '
                     f'— {_fmt_duration(r["voice_seconds"])}' for i, r in enumerate(rows)]
            desc = '\n'.join(lines)
        else:
            desc = 'No voice activity tracked yet.'
        return discord.Embed(title='🎙️ Voice Leaderboard',
                             description=desc, color=0x57F287)

    async def _leaderboard_embed(self, page: str, guild) -> discord.Embed:
        builders = {
            'levels':   self._levels_leaderboard_embed,
            'economy':  self._economy_leaderboard_embed,
            'tasks':    self._tasks_leaderboard_embed,
            'messages': self._messages_leaderboard_embed,
            'voice':    self._voice_leaderboard_embed,
        }
        return await builders[page](guild)

    async def send_leaderboard(self, ctx, page: str = 'levels'):
        """Send the unified paginated leaderboard, opened at the given page."""
        if page not in self.PAGES:
            page = 'levels'
        view = LeaderboardView(self, ctx.guild, start_page=page)
        embed = await self._leaderboard_embed(page, ctx.guild)
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name='leaderboard', aliases=['lb', 'boards'])
    async def leaderboard_cmd(self, ctx):
        """Unified server leaderboard — Levels / Economy / Tasks / Messages / Voice."""
        await self.send_leaderboard(ctx, 'levels')

    @stats.command(name='leaderboard', aliases=['lb', 'top'])
    async def stats_leaderboard(self, ctx):
        """Open the unified leaderboard on the Tasks page."""
        await self.send_leaderboard(ctx, 'tasks')


class LeaderboardView(discord.ui.View):
    """Button-paginated leaderboard: Levels, Economy, Tasks, Messages, Voice."""

    def __init__(self, cog: 'Stats', guild, start_page: str = 'levels', timeout: float = 120):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild = guild
        self.message: discord.Message | None = None
        self._set_active(start_page)

    def _set_active(self, page: str):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = child.custom_id == page

    async def _show(self, interaction: discord.Interaction, page: str):
        embed = await self.cog._leaderboard_embed(page, self.guild)
        self._set_active(page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='Levels', emoji='⚡', style=discord.ButtonStyle.primary, custom_id='levels')
    async def levels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, 'levels')

    @discord.ui.button(label='Economy', emoji='💰', style=discord.ButtonStyle.primary, custom_id='economy')
    async def economy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, 'economy')

    @discord.ui.button(label='Tasks', emoji='🏆', style=discord.ButtonStyle.primary, custom_id='tasks')
    async def tasks_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, 'tasks')

    @discord.ui.button(label='Messages', emoji='💬', style=discord.ButtonStyle.primary, custom_id='messages')
    async def messages_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, 'messages')

    @discord.ui.button(label='Voice', emoji='🎙️', style=discord.ButtonStyle.primary, custom_id='voice')
    async def voice_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, 'voice')

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


async def setup(bot):
    await bot.add_cog(Stats(bot))
