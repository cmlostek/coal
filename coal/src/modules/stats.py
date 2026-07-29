"""Stats module - server and user statistics"""

import datetime

import discord
from discord.ext import tasks


def setup(bot):
    """Setup function to register commands with the bot"""

    c = bot.db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS user_stats (
        user_id       BIGINT,
        guild_id      BIGINT,
        messages_sent INTEGER DEFAULT 0,
        voice_seconds INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, guild_id)
    )""")
    bot.db.commit()

    # Track when users joined voice channels. In memory, but a periodic
    # checkpoint flushes accrued time so a restart loses at most a few minutes.
    _voice_joins = {}  # (user_id, guild_id) -> datetime joined/last-checkpointed

    def _credit_voice(user_id, guild_id, secs):
        if secs <= 0:
            return
        try:
            c = bot.db.cursor()
            c.execute(
                """
                INSERT INTO user_stats (user_id, guild_id, messages_sent, voice_seconds)
                VALUES (%s, %s, 0, %s)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET voice_seconds = user_stats.voice_seconds + %s
            """,
                (user_id, guild_id, secs, secs),
            )
            bot.db.commit()
        except Exception as e:
            bot.db.rollback()
            print(f"[stats] voice credit error: {e}")

    def _flush_voice_sessions():
        """Credit accrued time for every active session and reset its start."""
        now = datetime.datetime.utcnow()
        for key, joined in list(_voice_joins.items()):
            secs = int((now - joined).total_seconds())
            if secs > 0:
                _credit_voice(key[0], key[1], secs)
                _voice_joins[key] = now

    async def _on_message_stats(message):
        if message.author.bot or not message.guild:
            return
        try:
            c = bot.db.cursor()
            c.execute(
                """
                INSERT INTO user_stats (user_id, guild_id, messages_sent, voice_seconds)
                VALUES (%s, %s, 1, 0)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET messages_sent = user_stats.messages_sent + 1
            """,
                (message.author.id, message.guild.id),
            )
            bot.db.commit()
        except Exception as e:
            bot.db.rollback()
            print(f"[stats] on_message error: {e}")

    # Use add_listener so we don't overwrite the on_message handler in levels.py
    bot.add_listener(_on_message_stats, "on_message")

    async def _on_voice_update(member, before, after):
        if member.bot:
            return
        key = (member.id, member.guild.id)
        # Joined voice from nothing.
        if before.channel is None and after.channel is not None:
            _voice_joins[key] = datetime.datetime.utcnow()
        # Left voice entirely.
        elif before.channel is not None and after.channel is None:
            joined = _voice_joins.pop(key, None)
            if joined is not None:
                secs = int((datetime.datetime.utcnow() - joined).total_seconds())
                _credit_voice(member.id, member.guild.id, secs)
        # Moved channels / mute-deafen change: keep the session running.
        elif after.channel is not None and key not in _voice_joins:
            _voice_joins[key] = datetime.datetime.utcnow()

    bot.add_listener(_on_voice_update, "on_voice_state_update")

    # Seed sessions for anyone already in voice, then checkpoint periodically.
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for m in vc.members:
                if not m.bot:
                    _voice_joins[(m.id, guild.id)] = datetime.datetime.utcnow()

    @tasks.loop(minutes=5)
    async def _voice_checkpoint():
        _flush_voice_sessions()

    if not _voice_checkpoint.is_running():
        _voice_checkpoint.start()

    def _fmt_duration(secs):
        if secs < 60:
            return f"{secs}s"
        elif secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        elif secs < 86400:
            h, m = secs // 3600, (secs % 3600) // 60
            return f"{h}h {m}m"
        else:
            d, h = secs // 86400, (secs % 86400) // 3600
            return f"{d}d {h}h"

    @bot.command(name="stats", aliases=["userstats", "mystats"])
    async def stats(ctx, user: discord.Member | None = None):
        """View stats for yourself or another user. Usage: -stats [@user]"""
        user = user or ctx.author
        c = bot.db.cursor()
        c.execute(
            "SELECT messages_sent, voice_seconds FROM user_stats WHERE user_id = %s AND guild_id = %s",
            (user.id, ctx.guild.id),
        )
        row = c.fetchone()
        messages = row[0] if row else 0
        voice_secs = row[1] if row else 0

        # Include the user's in-progress voice session, if any.
        key = (user.id, ctx.guild.id)
        if key in _voice_joins:
            voice_secs += int(
                (datetime.datetime.utcnow() - _voice_joins[key]).total_seconds()
            )

        c.execute(
            "SELECT COUNT(*) FROM user_stats WHERE guild_id = %s AND messages_sent > %s",
            (ctx.guild.id, messages),
        )
        msg_rank = c.fetchone()[0] + 1

        c.execute(
            "SELECT COUNT(*) FROM user_stats WHERE guild_id = %s AND voice_seconds > %s",
            (ctx.guild.id, voice_secs),
        )
        voice_rank = c.fetchone()[0] + 1

        created_days = (
            datetime.datetime.now(datetime.timezone.utc) - user.created_at
        ).days
        joined_days = (
            (datetime.datetime.now(datetime.timezone.utc) - user.joined_at).days
            if user.joined_at is not None
            else 0
        )

        color = user.color if user.color.value else discord.Color.blue()
        embed = discord.Embed(title=f"{user.display_name}'s Stats", color=color)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Messages Sent", value=f"{messages:,}", inline=True)
        embed.add_field(name="Chat Rank", value=f"#{msg_rank}", inline=True)
        embed.add_field(name="Voice Time", value=_fmt_duration(voice_secs), inline=True)
        embed.add_field(name="Voice Rank", value=f"#{voice_rank}", inline=True)
        embed.add_field(name="Account Age", value=f"{created_days:,} days", inline=True)
        embed.add_field(name="In Server", value=f"{joined_days:,} days", inline=True)
        embed.add_field(name="Roles", value=str(len(user.roles) - 1), inline=True)
        embed.set_footer(text=ctx.guild.name)
        await ctx.send(embed=embed)

    @bot.command(name="serverstats", aliases=["server", "guildstats", "ss"])
    async def serverstats(ctx):
        """View server statistics."""
        guild = ctx.guild

        text_ch = len(guild.text_channels)
        voice_ch = len(guild.voice_channels)
        cats = len(guild.categories)
        roles = len(guild.roles) - 1  # exclude @everyone

        c = bot.db.cursor()
        c.execute(
            "SELECT user_id, messages_sent FROM user_stats WHERE guild_id = %s ORDER BY messages_sent DESC LIMIT 3",
            (guild.id,),
        )
        top = c.fetchall()

        embed = discord.Embed(
            title=guild.name,
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="Owner",
            value=guild.owner.mention if guild.owner else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Created",
            value=f"<t:{int(guild.created_at.timestamp())}:D>",
            inline=True,
        )
        embed.add_field(name="Members", value=f"{guild.member_count:,}", inline=True)
        embed.add_field(name="Text Channels", value=str(text_ch), inline=True)
        embed.add_field(name="Voice Channels", value=str(voice_ch), inline=True)
        embed.add_field(name="Categories", value=str(cats), inline=True)
        embed.add_field(name="Roles", value=str(roles), inline=True)
        embed.add_field(name="Emojis", value=str(len(guild.emojis)), inline=True)
        embed.add_field(
            name="Boosts",
            value=f"{guild.premium_subscription_count} (Tier {guild.premium_tier})",
            inline=True,
        )

        if top:
            lines = []
            for rank, (uid, msgs) in enumerate(top, 1):
                member = guild.get_member(uid)
                name = member.display_name if member else f"<@{uid}>"
                lines.append(f"**#{rank}** {name} — {msgs:,} msgs")
            embed.add_field(name="Top Chatters", value="\n".join(lines), inline=False)

        embed.set_footer(text=f"Server ID: {guild.id}")
        await ctx.send(embed=embed)

    # ── Paginated activity leaderboard (Messages / Voice via buttons) ─────────

    _medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7

    def _member_name(guild, user_id):
        member = guild.get_member(user_id)
        return member.display_name if member else f"User {user_id}"

    def _messages_leaderboard_embed(guild):
        c = bot.db.cursor()
        c.execute(
            "SELECT user_id, messages_sent FROM user_stats "
            "WHERE guild_id = %s AND messages_sent > 0 "
            "ORDER BY messages_sent DESC LIMIT 10",
            (guild.id,),
        )
        rows = c.fetchall()
        if rows:
            desc = "\n".join(
                f"{_medals[i]} **{_member_name(guild, uid)}** — {msgs:,} messages"
                for i, (uid, msgs) in enumerate(rows)
            )
        else:
            desc = "No message activity tracked yet."
        return discord.Embed(
            title="💬 Message Leaderboard", description=desc, color=0x5865F2
        )

    def _voice_leaderboard_embed(guild):
        _flush_voice_sessions()  # reflect ongoing calls
        c = bot.db.cursor()
        c.execute(
            "SELECT user_id, voice_seconds FROM user_stats "
            "WHERE guild_id = %s AND voice_seconds > 0 "
            "ORDER BY voice_seconds DESC LIMIT 10",
            (guild.id,),
        )
        rows = c.fetchall()
        if rows:
            desc = "\n".join(
                f"{_medals[i]} **{_member_name(guild, uid)}** — {_fmt_duration(secs)}"
                for i, (uid, secs) in enumerate(rows)
            )
        else:
            desc = "No voice activity tracked yet."
        return discord.Embed(
            title="🎙️ Voice Leaderboard", description=desc, color=0x57F287
        )

    class LeaderboardView(discord.ui.View):
        """Button-paginated leaderboard: Messages, Voice."""

        def __init__(self, guild, timeout=120):
            super().__init__(timeout=timeout)
            self.guild = guild
            self.message = None
            self._set_active("messages")

        def _set_active(self, page):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = child.custom_id == page

        async def _show(self, interaction, page):
            builder = (
                _messages_leaderboard_embed
                if page == "messages"
                else _voice_leaderboard_embed
            )
            embed = builder(self.guild)
            self._set_active(page)
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(
            label="Messages",
            emoji="💬",
            style=discord.ButtonStyle.primary,
            custom_id="messages",
        )
        async def messages_btn(self, interaction, button):
            await self._show(interaction, "messages")

        @discord.ui.button(
            label="Voice",
            emoji="🎙️",
            style=discord.ButtonStyle.primary,
            custom_id="voice",
        )
        async def voice_btn(self, interaction, button):
            await self._show(interaction, "voice")

        async def on_timeout(self):
            for child in self.children:
                child.disabled = True
            if self.message:
                try:
                    await self.message.edit(view=self)
                except discord.HTTPException:
                    pass

    @bot.command(name="leaderboard", aliases=["lb", "activity"])
    async def leaderboard(ctx):
        """Server activity leaderboard — Messages / Voice, switchable via buttons."""
        view = LeaderboardView(ctx.guild)
        embed = _messages_leaderboard_embed(ctx.guild)
        view.message = await ctx.send(embed=embed, view=view)
