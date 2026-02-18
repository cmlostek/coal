"""
modules/tasks.py – Task tracker and assignment manager.

Commands
────────
Tasks
  !task add          – Add a task via modal
  !task list         – View your tasks (paginated)
  !task done <id>    – Mark a task complete
  !task delete <id>  – Delete a task
  !task view <id>    – Detailed view of one task
  !today             – Today's tasks + assignments
  !week              – This week's overview

Assignments (class work)
  !assign add                         – Add via modal
  !assign list [course]               – List assignments
  !assign done <id>                   – Mark complete
  !assign delete <id>                 – Delete
  !assign courses                     – List distinct courses
"""
import discord
from discord.ext import commands
from discord import ui
from datetime import datetime, timezone, timedelta
from typing import Optional
import pytz


# ─── Helpers ─────────────────────────────────────────────────────────────────

PRIORITY_EMOJI = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
STATUS_EMOJI   = {'pending': '⬜', 'in_progress': '🔵', 'completed': '✅', 'submitted': '📤', 'graded': '📝'}

def fmt_due(due_str: Optional[str]) -> str:
    if not due_str:
        return '*no due date*'
    try:
        dt = datetime.fromisoformat(due_str)
        now = datetime.now()
        delta = (dt.date() - now.date()).days
        suffix = ''
        if delta < 0:
            suffix = f' (**{abs(delta)}d overdue**)'
        elif delta == 0:
            suffix = ' (**today**)'
        elif delta == 1:
            suffix = ' (*tomorrow*)'
        elif delta <= 7:
            suffix = f' (*in {delta}d*)'
        return dt.strftime('%b %d, %Y') + suffix
    except Exception:
        return due_str


def chunk_embeds(items, title, color, per_page=8):
    """Split a list of items into pages of Discord embeds."""
    pages = []
    for i in range(0, max(len(items), 1), per_page):
        chunk = items[i:i + per_page]
        embed = discord.Embed(title=title, color=color)
        if not chunk:
            embed.description = '*Nothing here.*'
        else:
            embed.description = '\n'.join(chunk)
        embed.set_footer(text=f'Page {i // per_page + 1} of {max(1, (len(items) - 1) // per_page + 1)}')
        pages.append(embed)
    return pages


# ─── Paginator View ──────────────────────────────────────────────────────────

class Paginator(ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.page = 0
        self._update()

    def _update(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page == len(self.embeds) - 1

    @ui.button(label='◀', style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page -= 1
        self._update()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @ui.button(label='▶', style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page += 1
        self._update()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)


# ─── Task Modals ─────────────────────────────────────────────────────────────

class AddTaskModal(ui.Modal, title='Add Task'):
    task_title = ui.TextInput(label='Title', placeholder='Buy groceries', max_length=200)
    description = ui.TextInput(label='Description (optional)', style=discord.TextStyle.paragraph,
                               required=False, max_length=500)
    due_date = ui.TextInput(label='Due date (YYYY-MM-DD or leave blank)', required=False,
                            placeholder='2025-05-01', max_length=20)
    priority = ui.TextInput(label='Priority (high / medium / low)', default='medium', max_length=10)
    tag = ui.TextInput(label='Tag (optional)', required=False, max_length=50)

    def __init__(self, bot, user_id, guild_id):
        super().__init__()
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        prio = str(self.priority.value).lower().strip()
        if prio not in ('high', 'medium', 'low'):
            prio = 'medium'

        due = str(self.due_date.value).strip() or None
        if due:
            try:
                datetime.fromisoformat(due)
            except ValueError:
                return await interaction.response.send_message('❌ Invalid date. Use YYYY-MM-DD.', ephemeral=True)

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO tasks (user_id, guild_id, title, description, due_date, priority, tag)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (self.user_id, self.guild_id,
                 str(self.task_title.value).strip(),
                 str(self.description.value).strip() or None,
                 due, prio,
                 str(self.tag.value).strip() or None),
            )
            task_id = cur.lastrowid
        await self.bot.db.commit()

        embed = discord.Embed(
            title='✅ Task Added',
            description=f'**#{task_id}** {str(self.task_title.value).strip()}',
            color=0x5865F2,
        )
        embed.add_field(name='Priority', value=f'{PRIORITY_EMOJI[prio]} {prio}', inline=True)
        embed.add_field(name='Due', value=fmt_due(due), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AddAssignmentModal(ui.Modal, title='Add Assignment'):
    title_ = ui.TextInput(label='Assignment Title', max_length=200)
    course = ui.TextInput(label='Course Name', max_length=100)
    due_date = ui.TextInput(label='Due Date (YYYY-MM-DD)', placeholder='2025-05-01', max_length=20)
    points = ui.TextInput(label='Points (optional)', required=False, max_length=10)
    description = ui.TextInput(label='Notes (optional)', style=discord.TextStyle.paragraph,
                               required=False, max_length=500)

    def __init__(self, bot, user_id, guild_id):
        super().__init__()
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        due = str(self.due_date.value).strip()
        try:
            datetime.fromisoformat(due)
        except ValueError:
            return await interaction.response.send_message('❌ Invalid date. Use YYYY-MM-DD.', ephemeral=True)

        pts_raw = str(self.points.value).strip()
        pts = int(pts_raw) if pts_raw.isdigit() else None

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO assignments (user_id, guild_id, title, course, description, due_date, points)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (self.user_id, self.guild_id,
                 str(self.title_.value).strip(),
                 str(self.course.value).strip(),
                 str(self.description.value).strip() or None,
                 due, pts),
            )
            aid = cur.lastrowid
        await self.bot.db.commit()

        embed = discord.Embed(
            title='✅ Assignment Added',
            description=f'**#{aid}** {str(self.title_.value).strip()}',
            color=0xFF6B35,
        )
        embed.add_field(name='Course', value=str(self.course.value).strip(), inline=True)
        embed.add_field(name='Due', value=fmt_due(due), inline=True)
        if pts:
            embed.add_field(name='Points', value=str(pts), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Tasks(commands.Cog):
    """Task and assignment tracking."""

    def __init__(self, bot):
        self.bot = bot

    # ── TASK commands ─────────────────────────────────────────────────────────

    @commands.group(name='task', invoke_without_command=True)
    async def task(self, ctx):
        """Task management. Subcommands: add, list, done, delete, view."""
        embed = discord.Embed(
            title='📋 Task Commands',
            description=(
                '`!task add` – Add a task\n'
                '`!task list` – List your tasks\n'
                '`!task done <id>` – Mark complete\n'
                '`!task delete <id>` – Delete a task\n'
                '`!task view <id>` – Detailed view'
            ),
            color=0x5865F2,
        )
        await ctx.send(embed=embed)

    @task.command(name='add')
    async def task_add(self, ctx):
        """Add a new task via a form."""
        await ctx.interaction.response.send_modal(
            AddTaskModal(self.bot, ctx.author.id, ctx.guild.id)
        ) if ctx.interaction else await ctx.send(
            'Use the button below to add a task.',
            view=_OpenModalView(AddTaskModal, self.bot, ctx.author.id, ctx.guild.id, '📋 Add Task'),
        )

    @task.command(name='list')
    async def task_list(self, ctx, status: str = 'pending'):
        """List your tasks. `status` = pending | completed | all"""
        if status == 'all':
            where = ''
            args = (ctx.author.id, ctx.guild.id)
        elif status == 'completed':
            where = "AND status = 'completed'"
            args = (ctx.author.id, ctx.guild.id)
        else:
            where = "AND status != 'completed'"
            args = (ctx.author.id, ctx.guild.id)

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                f'''SELECT * FROM tasks
                    WHERE user_id = ? AND guild_id = ?
                    {where}
                    ORDER BY
                        CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                        due_date ASC NULLS LAST''',
                args,
            )
            rows = await cur.fetchall()

        lines = []
        for r in rows:
            p_e = PRIORITY_EMOJI.get(r['priority'], '⬜')
            s_e = STATUS_EMOJI.get(r['status'], '⬜')
            due = fmt_due(r['due_date'])
            lines.append(f'{s_e} {p_e} **#{r["id"]}** {r["title"]} — {due}')

        color = 0x5865F2
        title = f'📋 Your Tasks ({status})'
        embeds = chunk_embeds(lines, title, color)
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.send(embed=embeds[0], view=Paginator(embeds))

    @task.command(name='done')
    async def task_done(self, ctx, task_id: int):
        """Mark a task as complete."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT * FROM tasks WHERE id = ? AND user_id = ? AND guild_id = ?',
                (task_id, ctx.author.id, ctx.guild.id),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f'❌ Task #{task_id} not found.')
            if row['status'] == 'completed':
                return await ctx.send(f'Task #{task_id} is already complete.')

            now_str = datetime.now(timezone.utc).isoformat()
            on_time = 1
            if row['due_date']:
                try:
                    due_dt = datetime.fromisoformat(row['due_date'])
                    if due_dt.tzinfo is None:
                        due_dt = due_dt.replace(tzinfo=timezone.utc)
                    on_time = 1 if datetime.now(timezone.utc) <= due_dt else 0
                except Exception:
                    on_time = 1

            await cur.execute(
                'UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?',
                ('completed', now_str, task_id),
            )
            # Update stats
            today = datetime.now(timezone.utc).date().isoformat()
            await cur.execute(
                '''INSERT INTO task_stats (user_id, guild_id, date, tasks_completed, tasks_on_time, tasks_late)
                   VALUES (?, ?, ?, 1, ?, ?)
                   ON CONFLICT DO NOTHING''',
                (ctx.author.id, ctx.guild.id, today, on_time, 1 - on_time),
            )
            await cur.execute(
                '''UPDATE task_stats
                   SET tasks_completed = tasks_completed + 1,
                       tasks_on_time   = tasks_on_time   + ?,
                       tasks_late      = tasks_late      + ?
                   WHERE user_id = ? AND guild_id = ? AND date = ?''',
                (on_time, 1 - on_time, ctx.author.id, ctx.guild.id, today),
            )
        await self.bot.db.commit()

        embed = discord.Embed(
            description=f'✅ Task **#{task_id}** – *{row["title"]}* marked complete! '
                        + ('(on time)' if on_time else '(late)'),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @task.command(name='delete')
    async def task_delete(self, ctx, task_id: int):
        """Delete a task."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT title FROM tasks WHERE id = ? AND user_id = ? AND guild_id = ?',
                (task_id, ctx.author.id, ctx.guild.id),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f'❌ Task #{task_id} not found.')
            await cur.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(description=f'🗑️ Deleted task **#{task_id}** – {row["title"]}', color=discord.Color.red()))

    @task.command(name='view')
    async def task_view(self, ctx, task_id: int):
        """View detailed info for a task."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT * FROM tasks WHERE id = ? AND guild_id = ?', (task_id, ctx.guild.id))
            r = await cur.fetchone()
        if not r:
            return await ctx.send(f'❌ Task #{task_id} not found.')

        embed = discord.Embed(title=f'📋 Task #{r["id"]} — {r["title"]}', color=0x5865F2)
        embed.add_field(name='Status', value=f'{STATUS_EMOJI.get(r["status"], "?")} {r["status"]}', inline=True)
        embed.add_field(name='Priority', value=f'{PRIORITY_EMOJI.get(r["priority"], "?")} {r["priority"]}', inline=True)
        embed.add_field(name='Due', value=fmt_due(r['due_date']), inline=True)
        if r['description']:
            embed.add_field(name='Notes', value=r['description'], inline=False)
        if r['tag']:
            embed.add_field(name='Tag', value=r['tag'], inline=True)
        embed.add_field(name='Created', value=r['created_at'][:10], inline=True)
        if r['completed_at']:
            embed.add_field(name='Completed', value=r['completed_at'][:10], inline=True)
        await ctx.send(embed=embed)

    # ── ASSIGN commands ───────────────────────────────────────────────────────

    @commands.group(name='assign', invoke_without_command=True)
    async def assign(self, ctx):
        """Assignment management. Subcommands: add, list, done, delete, courses."""
        embed = discord.Embed(
            title='📚 Assignment Commands',
            description=(
                '`!assign add` – Add an assignment\n'
                '`!assign list [course]` – List assignments\n'
                '`!assign done <id>` – Mark submitted/complete\n'
                '`!assign delete <id>` – Delete\n'
                '`!assign courses` – List your courses'
            ),
            color=0xFF6B35,
        )
        await ctx.send(embed=embed)

    @assign.command(name='add')
    async def assign_add(self, ctx):
        """Add an assignment via a form."""
        await ctx.send(
            'Use the button below to add an assignment.',
            view=_OpenModalView(AddAssignmentModal, self.bot, ctx.author.id, ctx.guild.id, '📚 Add Assignment'),
        )

    @assign.command(name='list')
    async def assign_list(self, ctx, *, course: str = None):
        """List assignments. Optionally filter by course name."""
        if course:
            async with self.bot.db.cursor() as cur:
                await cur.execute(
                    '''SELECT * FROM assignments
                       WHERE user_id = ? AND guild_id = ? AND course LIKE ? AND status != 'completed'
                       ORDER BY due_date ASC''',
                    (ctx.author.id, ctx.guild.id, f'%{course}%'),
                )
                rows = await cur.fetchall()
        else:
            async with self.bot.db.cursor() as cur:
                await cur.execute(
                    '''SELECT * FROM assignments
                       WHERE user_id = ? AND guild_id = ? AND status != 'completed'
                       ORDER BY due_date ASC''',
                    (ctx.author.id, ctx.guild.id),
                )
                rows = await cur.fetchall()

        lines = []
        for r in rows:
            s_e = STATUS_EMOJI.get(r['status'], '⬜')
            due = fmt_due(r['due_date'])
            pts = f' [{r["points"]}pts]' if r['points'] else ''
            lines.append(f'{s_e} **#{r["id"]}** **{r["course"]}** – {r["title"]}{pts} — {due}')

        title = f'📚 Assignments{" — " + course if course else ""}'
        embeds = chunk_embeds(lines, title, 0xFF6B35)
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.send(embed=embeds[0], view=Paginator(embeds))

    @assign.command(name='done')
    async def assign_done(self, ctx, assign_id: int):
        """Mark an assignment as submitted/complete."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT * FROM assignments WHERE id = ? AND user_id = ? AND guild_id = ?',
                (assign_id, ctx.author.id, ctx.guild.id),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f'❌ Assignment #{assign_id} not found.')

            now_str = datetime.now(timezone.utc).isoformat()
            on_time = 1
            if row['due_date']:
                try:
                    due_dt = datetime.fromisoformat(row['due_date'])
                    if due_dt.tzinfo is None:
                        due_dt = due_dt.replace(tzinfo=timezone.utc)
                    on_time = 1 if datetime.now(timezone.utc) <= due_dt else 0
                except Exception:
                    on_time = 1

            await cur.execute(
                'UPDATE assignments SET status = ?, completed_at = ? WHERE id = ?',
                ('submitted', now_str, assign_id),
            )
            today = datetime.now(timezone.utc).date().isoformat()
            await cur.execute(
                '''INSERT INTO task_stats (user_id, guild_id, date, assignments_completed)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT DO NOTHING''',
                (ctx.author.id, ctx.guild.id, today),
            )
            await cur.execute(
                '''UPDATE task_stats
                   SET assignments_completed = assignments_completed + 1
                   WHERE user_id = ? AND guild_id = ? AND date = ?''',
                (ctx.author.id, ctx.guild.id, today),
            )
        await self.bot.db.commit()

        embed = discord.Embed(
            description=f'📤 Assignment **#{assign_id}** – *{row["title"]}* marked submitted! '
                        + ('(on time)' if on_time else '(late)'),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @assign.command(name='delete')
    async def assign_delete(self, ctx, assign_id: int):
        """Delete an assignment."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT title FROM assignments WHERE id = ? AND user_id = ? AND guild_id = ?',
                (assign_id, ctx.author.id, ctx.guild.id),
            )
            row = await cur.fetchone()
            if not row:
                return await ctx.send(f'❌ Assignment #{assign_id} not found.')
            await cur.execute('DELETE FROM assignments WHERE id = ?', (assign_id,))
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(description=f'🗑️ Deleted assignment **#{assign_id}**', color=discord.Color.red()))

    @assign.command(name='courses')
    async def assign_courses(self, ctx):
        """List all distinct courses with open assignments."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT course, COUNT(*) as cnt FROM assignments
                   WHERE user_id = ? AND guild_id = ? AND status != 'completed'
                   GROUP BY course ORDER BY course''',
                (ctx.author.id, ctx.guild.id),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send('No courses with open assignments found.')
        lines = [f'📖 **{r["course"]}** — {r["cnt"]} assignment(s)' for r in rows]
        embed = discord.Embed(title='📚 Your Courses', description='\n'.join(lines), color=0xFF6B35)
        await ctx.send(embed=embed)

    # ── Today / Week overview ─────────────────────────────────────────────────

    @commands.command(name='today')
    async def today(self, ctx):
        """Show everything due today."""
        today = datetime.now().date().isoformat()
        tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT * FROM tasks
                   WHERE user_id = ? AND guild_id = ?
                     AND status != 'completed'
                     AND due_date >= ? AND due_date < ?
                   ORDER BY priority''',
                (ctx.author.id, ctx.guild.id, today, tomorrow),
            )
            tasks = await cur.fetchall()

            await cur.execute(
                '''SELECT * FROM assignments
                   WHERE user_id = ? AND guild_id = ?
                     AND status != 'completed' AND status != 'submitted'
                     AND due_date >= ? AND due_date < ?
                   ORDER BY due_date''',
                (ctx.author.id, ctx.guild.id, today, tomorrow),
            )
            assigns = await cur.fetchall()

            await cur.execute(
                '''SELECT * FROM tasks
                   WHERE user_id = ? AND guild_id = ?
                     AND status != 'completed'
                     AND (due_date IS NULL OR due_date < ?)
                   ORDER BY due_date ASC NULLS LAST
                   LIMIT 5''',
                (ctx.author.id, ctx.guild.id, today),
            )
            overdue_tasks = await cur.fetchall()

        embed = discord.Embed(
            title=f'📅 Today — {datetime.now().strftime("%A, %B %d")}',
            color=0x5865F2,
        )

        if tasks:
            lines = [f'{PRIORITY_EMOJI.get(r["priority"], "⬜")} **#{r["id"]}** {r["title"]}' for r in tasks]
            embed.add_field(name=f'📋 Tasks Due Today ({len(tasks)})', value='\n'.join(lines), inline=False)

        if assigns:
            lines = [f'📖 **{r["course"]}** – {r["title"]}' for r in assigns]
            embed.add_field(name=f'📚 Assignments Due Today ({len(assigns)})', value='\n'.join(lines), inline=False)

        if overdue_tasks:
            lines = [f'🔴 **#{r["id"]}** {r["title"]} — {fmt_due(r["due_date"])}' for r in overdue_tasks]
            embed.add_field(name='⚠️ Overdue Tasks', value='\n'.join(lines), inline=False)

        if not tasks and not assigns and not overdue_tasks:
            embed.description = '🎉 Nothing due today!'

        await ctx.send(embed=embed)

    @commands.command(name='week')
    async def week(self, ctx):
        """Show everything due this week."""
        today = datetime.now().date()
        end_of_week = (today + timedelta(days=7)).isoformat()
        today_str = today.isoformat()

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''SELECT * FROM tasks
                   WHERE user_id = ? AND guild_id = ?
                     AND status != 'completed'
                     AND due_date >= ? AND due_date <= ?
                   ORDER BY due_date ASC''',
                (ctx.author.id, ctx.guild.id, today_str, end_of_week),
            )
            tasks = await cur.fetchall()

            await cur.execute(
                '''SELECT * FROM assignments
                   WHERE user_id = ? AND guild_id = ?
                     AND status NOT IN ('completed', 'submitted')
                     AND due_date >= ? AND due_date <= ?
                   ORDER BY due_date ASC''',
                (ctx.author.id, ctx.guild.id, today_str, end_of_week),
            )
            assigns = await cur.fetchall()

        embed = discord.Embed(
            title=f'📅 This Week — {today.strftime("%b %d")} to {(today + timedelta(days=7)).strftime("%b %d")}',
            color=0x5865F2,
        )

        if tasks:
            lines = [f'{PRIORITY_EMOJI.get(r["priority"], "⬜")} **#{r["id"]}** {r["title"]} — {fmt_due(r["due_date"])}'
                     for r in tasks]
            embed.add_field(name=f'📋 Tasks ({len(tasks)})', value='\n'.join(lines[:15]), inline=False)

        if assigns:
            lines = [f'📖 **{r["course"]}** – {r["title"]} — {fmt_due(r["due_date"])}'
                     for r in assigns]
            embed.add_field(name=f'📚 Assignments ({len(assigns)})', value='\n'.join(lines[:15]), inline=False)

        if not tasks and not assigns:
            embed.description = '🎉 Nothing due this week!'

        await ctx.send(embed=embed)


# ─── Helper view to open a modal from a button ──────────────────────────────

class _OpenModalView(ui.View):
    def __init__(self, modal_cls, bot, user_id, guild_id, label='Open Form'):
        super().__init__(timeout=60)
        self.modal_cls = modal_cls
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id

        btn = ui.Button(label=label, style=discord.ButtonStyle.primary)
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message('Not your button.', ephemeral=True)
            await interaction.response.send_modal(
                self.modal_cls(self.bot, self.user_id, self.guild_id)
            )
        btn.callback = callback
        self.add_item(btn)


async def setup(bot):
    await bot.add_cog(Tasks(bot))
