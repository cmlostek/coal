"""Polls module.

``-poll`` opens a modal form (question, options, close time, multi-select) and
posts a native Discord poll (``discord.Poll``) built from the answers. Discord
itself owns voting, vote counts, and auto-closing — no database is used here.
"""

import math
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import ui

MIN_OPTIONS = 2
MAX_OPTIONS = 10
MIN_DURATION_HOURS = 1
MAX_DURATION_HOURS = 32 * 24  # Discord's cap: 32 days.

_DURATION_RE = re.compile(
    r'(\d+)\s*(w(?:eek)?s?|d(?:ay)?s?|h(?:(?:ou)?r)?s?|m(?:in(?:ute)?s?)?|s(?:ec(?:ond)?s?)?)',
    re.IGNORECASE,
)


def _parse_duration_seconds(s):
    """Parse '1h30m', '2d', '3w' style strings into total seconds. None if invalid."""
    matches = _DURATION_RE.findall(s)
    if not matches:
        return None
    total = 0
    for amount, unit in matches:
        u = unit[0].lower()
        n = int(amount)
        if u == 's':
            total += n
        elif u == 'm':
            total += n * 60
        elif u == 'h':
            total += n * 3600
        elif u == 'd':
            total += n * 86400
        elif u == 'w':
            total += n * 604800
    return total if total > 0 else None


def parse_close_time(s):
    """Resolve a close-time string to whole hours from now, clamped to Discord's limits.

    Accepts absolute timestamps ('2026-10-05 18:00', '2026-10-05T18:00', '2026-10-05')
    or relative shorthand ('2h', '1d12h', '30m'). Returns (hours, warning) where
    warning is a string if the value had to be clamped, else None. Returns
    (None, error) if the string couldn't be parsed at all.
    """
    s = s.strip()

    dt = None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue

    if dt is not None:
        seconds = (dt - datetime.now(timezone.utc)).total_seconds()
    else:
        seconds = _parse_duration_seconds(s)
        if seconds is None:
            return None, (
                "Couldn't parse that close time. Use a duration like `2h`, `1d12h`, `30m`, "
                "or a date like `2026-10-05 18:00`."
            )

    hours = math.ceil(seconds / 3600)
    warning = None
    if hours < MIN_DURATION_HOURS:
        hours = MIN_DURATION_HOURS
        warning = f'Close time was in the past or too soon, so I set it to {MIN_DURATION_HOURS} hour.'
    elif hours > MAX_DURATION_HOURS:
        hours = MAX_DURATION_HOURS
        warning = f'Discord polls can run at most 32 days, so I capped it at {MAX_DURATION_HOURS} hours.'
    return hours, warning


class PollModal(ui.Modal, title='Create a Poll'):
    question = ui.TextInput(label='Question', max_length=300, placeholder='Best pizza topping?')
    options = ui.TextInput(
        label='Options (one per line, 2-10)',
        style=discord.TextStyle.paragraph,
        placeholder='Pepperoni\nMushroom\nPineapple',
        max_length=500,
    )
    close_time = ui.TextInput(
        label='Closes in (e.g. 2h, 1d12h) or a date',
        placeholder='e.g. 24h or 2026-10-05 18:00',
        max_length=40,
    )
    multiple = ui.TextInput(
        label='Allow multiple answers? (yes/no)',
        default='no',
        max_length=5,
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw_options = [line.strip() for line in str(self.options.value).splitlines()]
        opts = [o for o in raw_options if o]
        if len(opts) < MIN_OPTIONS:
            await interaction.response.send_message(
                f'A poll needs at least {MIN_OPTIONS} options.', ephemeral=True
            )
            return
        if len(opts) > MAX_OPTIONS:
            await interaction.response.send_message(
                f'A poll can have at most {MAX_OPTIONS} options (you gave {len(opts)}).', ephemeral=True
            )
            return

        hours, time_msg = parse_close_time(str(self.close_time.value))
        if hours is None:
            await interaction.response.send_message(time_msg, ephemeral=True)
            return

        allow_multiple = str(self.multiple.value).strip().lower() in ('yes', 'y', 'true', '1')

        poll = discord.Poll(
            question=str(self.question.value).strip(),
            duration=timedelta(hours=hours),
            multiple=allow_multiple,
        )
        for opt in opts:
            poll.add_answer(text=opt[:55])

        await interaction.response.send_message(poll=poll)
        if time_msg:
            await interaction.followup.send(time_msg, ephemeral=True)


class _OpenPollModalView(ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    @ui.button(label='📊 Create Poll', style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Not your poll form.', ephemeral=True)
            return
        await interaction.response.send_modal(PollModal())


def setup(bot):
    """Setup function to register commands with the bot"""

    @bot.command(name='poll')
    async def poll(ctx):
        """Create a poll. Opens a form for the question, options, close time, and multi-select."""
        await ctx.send(
            'Click below to fill out your poll.',
            view=_OpenPollModalView(ctx.author.id),
        )
