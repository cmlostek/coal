"""Stats module - server and user statistics"""

import datetime

import discord


def setup(bot):
    """Setup function to register commands with the bot"""

    c = bot.db.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_stats (
        user_id       INTEGER,
        guild_id      INTEGER,
        messages_sent INTEGER DEFAULT 0,
        voice_seconds INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, guild_id)
    )''')
    bot.db.commit()

    # Track when users joined voice channels (in memory, resets on bot restart)
    _voice_joins = {}

    async def _on_message_stats(message):
        if message.author.bot or not message.guild:
            return
        c = bot.db.cursor()
        c.execute('''
            INSERT INTO user_stats (user_id, guild_id, messages_sent, voice_seconds)
            VALUES (?, ?, 1, 0)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET messages_sent = messages_sent + 1
        ''', (message.author.id, message.guild.id))
        bot.db.commit()

    # Use add_listener so we don't overwrite the on_message handler in levels.py
    bot.add_listener(_on_message_stats, 'on_message')

    async def _on_voice_update(member, before, after):
        key = (member.id, member.guild.id)
        if before.channel is None and after.channel is not None:
            _voice_joins[key] = datetime.datetime.utcnow()
        elif before.channel is not None and after.channel is None:
            if key in _voice_joins:
                secs = int((datetime.datetime.utcnow() - _voice_joins.pop(key)).total_seconds())
                c = bot.db.cursor()
                c.execute('''
                    INSERT INTO user_stats (user_id, guild_id, messages_sent, voice_seconds)
                    VALUES (?, ?, 0, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET voice_seconds = voice_seconds + ?
                ''', (member.id, member.guild.id, secs, secs))
                bot.db.commit()

    bot.add_listener(_on_voice_update, 'on_voice_state_update')

    def _fmt_duration(secs):
        if secs < 60:
            return f'{secs}s'
        elif secs < 3600:
            return f'{secs // 60}m {secs % 60}s'
        elif secs < 86400:
            h, m = secs // 3600, (secs % 3600) // 60
            return f'{h}h {m}m'
        else:
            d, h = secs // 86400, (secs % 86400) // 3600
            return f'{d}d {h}h'

    @bot.command(name='stats', aliases=['userstats', 'mystats'])
    async def stats(ctx, user: discord.Member = None):
        """View stats for yourself or another user. Usage: -stats [@user]"""
        user = user or ctx.author
        c = bot.db.cursor()
        c.execute(
            'SELECT messages_sent, voice_seconds FROM user_stats WHERE user_id = ? AND guild_id = ?',
            (user.id, ctx.guild.id)
        )
        row = c.fetchone()
        messages = row[0] if row else 0
        voice_secs = row[1] if row else 0

        c.execute(
            'SELECT COUNT(*) FROM user_stats WHERE guild_id = ? AND messages_sent > ?',
            (ctx.guild.id, messages)
        )
        msg_rank = c.fetchone()[0] + 1

        created_days = (datetime.datetime.now(datetime.timezone.utc) - user.created_at).days
        joined_days = (datetime.datetime.now(datetime.timezone.utc) - user.joined_at).days

        color = user.color if user.color.value else discord.Color.blue()
        embed = discord.Embed(title=f"{user.display_name}'s Stats", color=color)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name='Messages Sent', value=f'{messages:,}', inline=True)
        embed.add_field(name='Chat Rank', value=f'#{msg_rank}', inline=True)
        embed.add_field(name='Voice Time', value=_fmt_duration(voice_secs), inline=True)
        embed.add_field(name='Account Age', value=f'{created_days:,} days', inline=True)
        embed.add_field(name='In Server', value=f'{joined_days:,} days', inline=True)
        embed.add_field(name='Roles', value=str(len(user.roles) - 1), inline=True)
        embed.set_footer(text=ctx.guild.name)
        await ctx.send(embed=embed)

    @bot.command(name='serverstats', aliases=['server', 'guildstats', 'ss'])
    async def serverstats(ctx):
        """View server statistics."""
        guild = ctx.guild

        text_ch = len(guild.text_channels)
        voice_ch = len(guild.voice_channels)
        cats = len(guild.categories)
        roles = len(guild.roles) - 1  # exclude @everyone

        c = bot.db.cursor()
        c.execute(
            'SELECT user_id, messages_sent FROM user_stats WHERE guild_id = ? ORDER BY messages_sent DESC LIMIT 3',
            (guild.id,)
        )
        top = c.fetchall()

        embed = discord.Embed(
            title=guild.name,
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name='Owner', value=guild.owner.mention if guild.owner else 'Unknown', inline=True)
        embed.add_field(name='Created', value=f'<t:{int(guild.created_at.timestamp())}:D>', inline=True)
        embed.add_field(name='Members', value=f'{guild.member_count:,}', inline=True)
        embed.add_field(name='Text Channels', value=str(text_ch), inline=True)
        embed.add_field(name='Voice Channels', value=str(voice_ch), inline=True)
        embed.add_field(name='Categories', value=str(cats), inline=True)
        embed.add_field(name='Roles', value=str(roles), inline=True)
        embed.add_field(name='Emojis', value=str(len(guild.emojis)), inline=True)
        embed.add_field(
            name='Boosts',
            value=f'{guild.premium_subscription_count} (Tier {guild.premium_tier})',
            inline=True
        )

        if top:
            lines = []
            for rank, (uid, msgs) in enumerate(top, 1):
                member = guild.get_member(uid)
                name = member.display_name if member else f'<@{uid}>'
                lines.append(f'**#{rank}** {name} — {msgs:,} msgs')
            embed.add_field(name='Top Chatters', value='\n'.join(lines), inline=False)

        embed.set_footer(text=f'Server ID: {guild.id}')
        await ctx.send(embed=embed)
