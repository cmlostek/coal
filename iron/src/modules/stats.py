"""
modules/stats.py – Task & assignment completion statistics with matplotlib graphs.

Commands
────────
  !stats           – your completion dashboard with graph
  !stats week      – last 7 days bar chart
  !stats month     – last 30 days chart
  !stats leaderboard – server-wide completion leaderboard
"""
import discord
from discord.ext import commands
import asyncio
import io
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)


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

    @stats.command(name='leaderboard', aliases=['lb', 'top'])
    async def stats_leaderboard(self, ctx):
        """Server-wide task completion leaderboard (last 30 days)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT user_id,
                          SUM(tasks_completed) as done,
                          SUM(tasks_on_time)   as ot,
                          SUM(assignments_completed) as asgn
                   FROM task_stats
                   WHERE guild_id = ? AND date >= ?
                   GROUP BY user_id
                   ORDER BY done DESC
                   LIMIT 10''',
                (ctx.guild.id, cutoff),
            )
            rows = await cur.fetchall()

        if not rows:
            return await ctx.send('No stats data for this server yet.')

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        lines = []
        for i, r in enumerate(rows):
            user = ctx.guild.get_member(r['user_id'])
            name = user.display_name if user else f'User {r["user_id"]}'
            rate = round(r['ot'] / r['done'] * 100) if r['done'] else 0
            lines.append(f'{medals[i]} **{name}** — {r["done"]} tasks ({rate}% on time)')

        embed = discord.Embed(
            title='🏆 Task Leaderboard — Last 30 Days',
            description='\n'.join(lines),
            color=0xF1C40F,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))
