"""
modules/canvas_module.py – Canvas LMS integration.

Setup
─────
  !canvas setup <api_key> <canvas_url>
    e.g. !canvas setup abc123 https://canvas.instructure.com

Commands
────────
  !canvas setup <api_key> <url>  – link Canvas account
  !canvas courses                – list enrolled courses
  !canvas assignments [course]   – upcoming assignments
  !canvas grades [course]        – current grades
  !canvas sync                   – import assignments into !assign tracker
  !canvas status                 – check connection
  !canvas unlink                 – remove Canvas config
"""
import discord
from discord.ext import commands
import asyncio
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

PRIORITY_COLORS = {
    'overdue': discord.Color.red(),
    'soon': discord.Color.orange(),
    'upcoming': discord.Color.blue(),
}


def _fmt_dt(dt_str: str) -> str:
    if not dt_str:
        return '*no due date*'
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = (dt.date() - now.date()).days
        base = dt.strftime('%b %d, %Y at %I:%M %p')
        if delta < 0:
            return f'{base} (**{abs(delta)}d overdue**)'
        if delta == 0:
            return f'{base} (**today**)'
        if delta == 1:
            return f'{base} (*tomorrow*)'
        if delta <= 7:
            return f'{base} (*in {delta}d*)'
        return base
    except Exception:
        return dt_str


class Canvas(commands.Cog):
    """Canvas LMS integration for grades and assignments."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_canvas(self, user_id: int):
        """Return (canvas_obj, url) or (None, None) if not configured."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT * FROM canvas_config WHERE user_id = ?', (user_id,))
            row = await cur.fetchone()
        if not row or not row['api_key'] or not row['canvas_url']:
            return None, None
        try:
            from canvasapi import Canvas as CanvasAPI
            canvas = CanvasAPI(row['canvas_url'], row['api_key'])
            return canvas, row['canvas_url']
        except Exception as exc:
            log.warning('Failed to build Canvas client for %s: %s', user_id, exc)
            return None, None

    @commands.group(name='canvas', invoke_without_command=True)
    async def canvas(self, ctx):
        """Canvas LMS commands."""
        embed = discord.Embed(
            title='🎓 Canvas Commands',
            description=(
                '`!canvas setup <api_key> <url>` – link Canvas\n'
                '`!canvas courses` – list courses\n'
                '`!canvas assignments [course]` – upcoming assignments\n'
                '`!canvas grades [course]` – view grades\n'
                '`!canvas sync` – sync assignments to tracker\n'
                '`!canvas status` – check connection\n'
                '`!canvas unlink` – remove configuration'
            ),
            color=0xE66000,
        )
        await ctx.send(embed=embed)

    @canvas.command(name='setup')
    async def canvas_setup(self, ctx, api_key: str, *, canvas_url: str):
        """
        Link your Canvas account.

        Get your API key from Canvas → Account → Settings → New Access Token.
        `canvas_url` should be your institution's Canvas URL (e.g. https://canvas.instructure.com).
        """
        canvas_url = canvas_url.rstrip('/')
        # Verify the key works
        try:
            from canvasapi import Canvas as CanvasAPI
            c = CanvasAPI(canvas_url, api_key)
            user = await asyncio.to_thread(c.get_current_user)
        except Exception as exc:
            return await ctx.send(f'❌ Could not connect to Canvas: `{exc}`\nCheck your API key and URL.')

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO canvas_config (user_id, api_key, canvas_url)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       api_key    = excluded.api_key,
                       canvas_url = excluded.canvas_url''',
                (ctx.author.id, api_key, canvas_url),
            )
        await self.bot.db.commit()

        # Delete the message to avoid leaking the API key
        try:
            await ctx.message.delete()
        except Exception:
            pass

        embed = discord.Embed(
            title='✅ Canvas Linked',
            description=f'Connected as **{user.name}**.\nYour API key has been saved (and your message deleted for security).',
            color=discord.Color.green(),
        )
        await ctx.author.send(embed=embed)
        await ctx.send('✅ Canvas linked! Check your DMs.')

    @canvas.command(name='status')
    async def canvas_status(self, ctx):
        """Check if Canvas is configured."""
        canvas, _ = await self._get_canvas(ctx.author.id)
        if not canvas:
            return await ctx.send(embed=discord.Embed(
                description='❌ Canvas not linked. Run `!canvas setup <api_key> <url>`.',
                color=discord.Color.red(),
            ))
        try:
            user = await asyncio.to_thread(canvas.get_current_user)
            embed = discord.Embed(
                description=f'✅ Canvas connected as **{user.name}**.',
                color=discord.Color.green(),
            )
        except Exception as exc:
            embed = discord.Embed(
                description=f'⚠️ Canvas is configured but returned an error: `{exc}`',
                color=discord.Color.orange(),
            )
        await ctx.send(embed=embed)

    @canvas.command(name='unlink')
    async def canvas_unlink(self, ctx):
        """Remove your Canvas configuration."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('DELETE FROM canvas_config WHERE user_id = ?', (ctx.author.id,))
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(description='✅ Canvas unlinked.', color=discord.Color.green()))

    @canvas.command(name='courses')
    async def canvas_courses(self, ctx):
        """List your active Canvas courses."""
        canvas, _ = await self._get_canvas(ctx.author.id)
        if not canvas:
            return await ctx.send('❌ Canvas not linked. Run `!canvas setup`.')

        async with ctx.typing():
            try:
                def _fetch():
                    return list(canvas.get_courses(enrollment_state='active'))
                courses = await asyncio.to_thread(_fetch)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch courses: `{exc}`')

        if not courses:
            return await ctx.send('No active courses found.')

        lines = []
        for c in courses:
            name = getattr(c, 'name', 'Unknown')
            code = getattr(c, 'course_code', '')
            cid  = getattr(c, 'id', '?')
            lines.append(f'`{cid}` **{name}** ({code})')

        embed = discord.Embed(
            title=f'🎓 Your Canvas Courses ({len(courses)})',
            description='\n'.join(lines[:25]),
            color=0xE66000,
        )
        await ctx.send(embed=embed)

    @canvas.command(name='assignments')
    async def canvas_assignments(self, ctx, *, course_filter: str = None):
        """Show upcoming Canvas assignments. Optionally filter by course name."""
        canvas, _ = await self._get_canvas(ctx.author.id)
        if not canvas:
            return await ctx.send('❌ Canvas not linked.')

        async with ctx.typing():
            try:
                def _fetch():
                    courses = list(canvas.get_courses(enrollment_state='active'))
                    results = []
                    for course in courses:
                        cname = getattr(course, 'name', 'Unknown')
                        if course_filter and course_filter.lower() not in cname.lower():
                            continue
                        try:
                            assigns = list(course.get_assignments(
                                bucket='upcoming',
                                order_by='due_at',
                            ))
                            for a in assigns:
                                results.append((cname, a))
                        except Exception:
                            pass
                    results.sort(key=lambda x: (getattr(x[1], 'due_at', None) or ''))
                    return results
                items = await asyncio.to_thread(_fetch)
            except Exception as exc:
                return await ctx.send(f'❌ Failed: `{exc}`')

        if not items:
            return await ctx.send('No upcoming assignments found.')

        lines = []
        for course_name, a in items[:20]:
            due = _fmt_dt(getattr(a, 'due_at', None))
            pts = getattr(a, 'points_possible', None)
            pts_str = f' [{pts}pts]' if pts else ''
            name = getattr(a, 'name', 'Unknown')
            lines.append(f'📖 **{course_name}** – {name}{pts_str}\n  ↳ {due}')

        embed = discord.Embed(
            title=f'📚 Canvas Assignments{" — " + course_filter if course_filter else ""}',
            description='\n\n'.join(lines),
            color=0xE66000,
        )
        await ctx.send(embed=embed)

    @canvas.command(name='grades')
    async def canvas_grades(self, ctx, *, course_filter: str = None):
        """Show current grades for your Canvas courses."""
        canvas, _ = await self._get_canvas(ctx.author.id)
        if not canvas:
            return await ctx.send('❌ Canvas not linked.')

        async with ctx.typing():
            try:
                def _fetch():
                    courses = list(canvas.get_courses(enrollment_state='active', include=['total_scores']))
                    results = []
                    for course in courses:
                        cname = getattr(course, 'name', 'Unknown')
                        if course_filter and course_filter.lower() not in cname.lower():
                            continue
                        enrollment = getattr(course, 'enrollments', [{}])
                        if enrollment:
                            e = enrollment[0]
                            score = e.get('computed_current_score')
                            grade = e.get('computed_current_grade')
                            results.append((cname, score, grade))
                    return results
                items = await asyncio.to_thread(_fetch)
            except Exception as exc:
                return await ctx.send(f'❌ Failed: `{exc}`')

        if not items:
            return await ctx.send('No grade data available.')

        embed = discord.Embed(
            title=f'📊 Canvas Grades{" — " + course_filter if course_filter else ""}',
            color=0xE66000,
        )
        for cname, score, grade in items:
            grade_str = f'{grade} ({score}%)' if score is not None else '*(no grade)*'
            embed.add_field(name=cname, value=grade_str, inline=True)
        await ctx.send(embed=embed)

    @canvas.command(name='sync')
    async def canvas_sync(self, ctx):
        """
        Import upcoming Canvas assignments into the `!assign` tracker.
        Assignments already imported (by canvas_id) are skipped.
        """
        canvas, _ = await self._get_canvas(ctx.author.id)
        if not canvas:
            return await ctx.send('❌ Canvas not linked.')

        async with ctx.typing():
            try:
                def _fetch():
                    courses = list(canvas.get_courses(enrollment_state='active'))
                    results = []
                    for course in courses:
                        cname = getattr(course, 'name', 'Unknown')
                        try:
                            assigns = list(course.get_assignments(bucket='upcoming'))
                            for a in assigns:
                                results.append((cname, a))
                        except Exception:
                            pass
                    return results
                items = await asyncio.to_thread(_fetch)
            except Exception as exc:
                return await ctx.send(f'❌ Failed to fetch: `{exc}`')

        added = 0
        skipped = 0
        now_str = datetime.now(timezone.utc).isoformat()

        for course_name, a in items:
            aid = str(getattr(a, 'id', ''))
            due = getattr(a, 'due_at', None)
            if not due:
                continue
            # normalise date
            due_clean = due[:10] if due else None
            name = getattr(a, 'name', 'Unknown')
            pts  = getattr(a, 'points_possible', None)

            async with self.bot.db.cursor() as cur:
                await cur.execute(
                    'SELECT id FROM assignments WHERE canvas_id = ? AND user_id = ?',
                    (aid, ctx.author.id),
                )
                existing = await cur.fetchone()

                if existing:
                    skipped += 1
                else:
                    await cur.execute(
                        '''INSERT INTO assignments (user_id, guild_id, title, course, due_date, points, source, canvas_id)
                           VALUES (?, ?, ?, ?, ?, ?, 'canvas', ?)''',
                        (ctx.author.id, ctx.guild.id, name, course_name, due_clean, pts, aid),
                    )
                    added += 1

        await self.bot.db.commit()
        await ctx.send(
            embed=discord.Embed(
                title='🔄 Canvas Sync Complete',
                description=f'**{added}** assignment(s) imported, **{skipped}** skipped (already tracked).',
                color=discord.Color.green(),
            )
        )


async def setup(bot):
    await bot.add_cog(Canvas(bot))
