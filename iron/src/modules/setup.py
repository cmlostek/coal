"""
modules/setup.py – Server configuration wizard.
Run !setup to open the interactive setup panel.
"""
import discord
from discord.ext import commands
from discord import ui
import pytz


# ─── Modals ──────────────────────────────────────────────────────────────────

class SettingsModal(ui.Modal, title='Iron Bot – Server Settings'):
    digest_time = ui.TextInput(
        label='Daily Digest Time (24-hr, e.g. 08:00)',
        placeholder='08:00',
        default='08:00',
        max_length=5,
        required=True,
    )
    timezone = ui.TextInput(
        label='Timezone (e.g. America/New_York)',
        placeholder='America/New_York',
        default='America/New_York',
        max_length=60,
        required=True,
    )
    weather_location = ui.TextInput(
        label='Weather Location (city, state/country)',
        placeholder='New York, NY',
        max_length=100,
        required=False,
    )

    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        tz_val = str(self.timezone.value).strip()
        time_val = str(self.digest_time.value).strip()
        loc_val = str(self.weather_location.value).strip()

        # Validate timezone
        try:
            pytz.timezone(tz_val)
        except pytz.UnknownTimeZoneError:
            await interaction.response.send_message(
                f'❌ Unknown timezone: `{tz_val}`. Use a TZ database name like `America/New_York`.',
                ephemeral=True,
            )
            return

        # Validate time format
        try:
            h, m = time_val.split(':')
            assert 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except Exception:
            await interaction.response.send_message(
                '❌ Invalid time format. Use `HH:MM` (24-hr), e.g. `08:30`.',
                ephemeral=True,
            )
            return

        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO guild_config (guild_id, digest_time, timezone, weather_location)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET
                       digest_time      = excluded.digest_time,
                       timezone         = excluded.timezone,
                       weather_location = excluded.weather_location''',
                (self.guild_id, time_val, tz_val, loc_val or None),
            )
        await self.bot.db.commit()

        embed = discord.Embed(
            title='✅ Settings Saved',
            color=discord.Color.green(),
        )
        embed.add_field(name='Digest Time', value=time_val, inline=True)
        embed.add_field(name='Timezone', value=tz_val, inline=True)
        embed.add_field(name='Weather Location', value=loc_val or '*(not set)*', inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── Views ───────────────────────────────────────────────────────────────────

class SetupView(ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id

    @ui.select(
        cls=ui.ChannelSelect,
        placeholder='1️⃣  Select the daily digest channel',
        channel_types=[discord.ChannelType.text],
    )
    async def digest_select(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        channel = select.values[0]
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO guild_config (guild_id, daily_digest_channel)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET daily_digest_channel = excluded.daily_digest_channel''',
                (self.guild_id, channel.id),
            )
        await self.bot.db.commit()
        await interaction.response.send_message(
            f'✅ Daily digest channel → {channel.mention}', ephemeral=True
        )

    @ui.select(
        cls=ui.ChannelSelect,
        placeholder='2️⃣  Select the reminders channel',
        channel_types=[discord.ChannelType.text],
    )
    async def reminder_select(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        channel = select.values[0]
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO guild_config (guild_id, reminder_channel)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET reminder_channel = excluded.reminder_channel''',
                (self.guild_id, channel.id),
            )
        await self.bot.db.commit()
        await interaction.response.send_message(
            f'✅ Reminders channel → {channel.mention}', ephemeral=True
        )

    @ui.button(label='3️⃣  Open Settings Form', style=discord.ButtonStyle.primary, emoji='⚙️')
    async def open_settings(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SettingsModal(self.bot, self.guild_id))

    @ui.button(label='Mark Setup Complete ✅', style=discord.ButtonStyle.success, row=2)
    async def done(self, interaction: discord.Interaction, button: ui.Button):
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO guild_config (guild_id, setup_complete)
                   VALUES (?, 1)
                   ON CONFLICT(guild_id) DO UPDATE SET setup_complete = 1''',
                (self.guild_id,),
            )
        await self.bot.db.commit()
        embed = discord.Embed(
            title='🎉 Setup Complete!',
            description=(
                'Iron is ready.\n\n'
                '**Key commands:**\n'
                '`!task add` · `!assign add` · `!remind` · `!tag`\n'
                '`!calendar setup` · `!canvas setup` · `!email setup`\n'
                '`!today` · `!week` · `!stats`\n\n'
                'Run `!help` for the full command list.'
            ),
            color=discord.Color.brand_green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Setup(commands.Cog):
    """Interactive server setup and configuration."""

    def __init__(self, bot):
        self.bot = bot

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def get_config(self, guild_id: int):
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT * FROM guild_config WHERE guild_id = ?', (guild_id,))
            return await cur.fetchone()

    # ── Commands ─────────────────────────────────────────────────────────────

    @commands.group(name='setup', invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """Open the interactive setup wizard (admin only)."""
        embed = discord.Embed(
            title='⚙️ Iron Bot Setup',
            description=(
                'Use the controls below to configure Iron for this server.\n\n'
                '**Step 1** – Choose the **daily digest** channel\n'
                '**Step 2** – Choose the **reminders** channel\n'
                '**Step 3** – Fill in time / timezone / weather location\n'
                '**Step 4** – Click *Mark Setup Complete*'
            ),
            color=0x5865F2,
        )
        embed.set_footer(text='Only administrators can run setup.')
        view = SetupView(self.bot, ctx.guild.id)
        await ctx.send(embed=embed, view=view)

    @setup.command(name='view')
    async def setup_view(self, ctx):
        """Show the current server configuration."""
        cfg = await self.get_config(ctx.guild.id)
        if not cfg:
            return await ctx.send('No configuration found. Run `!setup` first.')

        embed = discord.Embed(title='⚙️ Server Configuration', color=0x5865F2)

        digest_ch = ctx.guild.get_channel(cfg['daily_digest_channel']) if cfg['daily_digest_channel'] else None
        remind_ch = ctx.guild.get_channel(cfg['reminder_channel']) if cfg['reminder_channel'] else None

        embed.add_field(name='Digest Channel', value=digest_ch.mention if digest_ch else '*not set*', inline=True)
        embed.add_field(name='Reminder Channel', value=remind_ch.mention if remind_ch else '*not set*', inline=True)
        embed.add_field(name='Digest Time', value=cfg['digest_time'] or '08:00', inline=True)
        embed.add_field(name='Timezone', value=cfg['timezone'] or 'UTC', inline=True)
        embed.add_field(name='Weather Location', value=cfg['weather_location'] or '*not set*', inline=True)
        embed.add_field(name='Setup Complete', value='✅' if cfg['setup_complete'] else '❌', inline=True)
        await ctx.send(embed=embed)

    @setup.command(name='location')
    @commands.has_permissions(administrator=True)
    async def setup_location(self, ctx, *, location: str):
        """Set the weather location. Example: `!setup location Austin, TX`"""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO guild_config (guild_id, weather_location)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET weather_location = excluded.weather_location''',
                (ctx.guild.id, location),
            )
        await self.bot.db.commit()
        await ctx.send(f'✅ Weather location set to **{location}**')

    @setup.command(name='timezone')
    @commands.has_permissions(administrator=True)
    async def setup_timezone(self, ctx, *, tz: str):
        """Set the server timezone. Example: `!setup timezone America/Chicago`"""
        try:
            pytz.timezone(tz)
        except pytz.UnknownTimeZoneError:
            return await ctx.send(f'❌ Unknown timezone `{tz}`. Use a TZ database name.')
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO guild_config (guild_id, timezone)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET timezone = excluded.timezone''',
                (ctx.guild.id, tz),
            )
        await self.bot.db.commit()
        await ctx.send(f'✅ Timezone set to **{tz}**')

    @setup.command(name='time')
    @commands.has_permissions(administrator=True)
    async def setup_time(self, ctx, time: str):
        """Set the daily digest time (24-hr). Example: `!setup time 07:30`"""
        try:
            h, m = time.split(':')
            assert 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except Exception:
            return await ctx.send('❌ Use `HH:MM` format, e.g. `08:00`.')
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                '''INSERT INTO guild_config (guild_id, digest_time)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET digest_time = excluded.digest_time''',
                (ctx.guild.id, time),
            )
        await self.bot.db.commit()
        await ctx.send(f'✅ Daily digest time set to **{time}**')

    @setup.command(name='channel')
    @commands.has_permissions(administrator=True)
    async def setup_channel(self, ctx, kind: str, channel: discord.TextChannel):
        """Set a channel. `kind` = `digest` or `reminder`."""
        if kind not in ('digest', 'reminder'):
            return await ctx.send('`kind` must be `digest` or `reminder`.')
        col = 'daily_digest_channel' if kind == 'digest' else 'reminder_channel'
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                f'''INSERT INTO guild_config (guild_id, {col})
                    VALUES (?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET {col} = excluded.{col}''',
                (ctx.guild.id, channel.id),
            )
        await self.bot.db.commit()
        await ctx.send(f'✅ {kind.capitalize()} channel set to {channel.mention}')


async def setup(bot):
    await bot.add_cog(Setup(bot))
