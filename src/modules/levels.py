import discord
from discord.ext import commands
import sqlite3 as sql
import random


def setup(bot):
    '''Setup function to register commands with the bot'''

    # Ensure levels table exists
    c = bot.db.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS levels
                 (
                     id    INTEGER PRIMARY KEY,
                     level INTEGER DEFAULT 1,
                     xp    INTEGER DEFAULT 0
                 )''')
    bot.db.commit()

    def calculate_xp_needed(level):
        '''Calculate XP needed for next level using exponential growth'''
        return int(10 * (1.5 ** (level - 1)))

    async def add_xp(user_id, xp_amount):
        '''Add XP to user and handle level ups'''
        c = bot.db.cursor()

        # Insert or update user record
        c.execute('INSERT OR IGNORE INTO levels (id, level, xp) VALUES (?, 1, 0)', (user_id,))
        c.execute('UPDATE levels SET xp = xp + ? WHERE id = ?', (xp_amount, user_id))

        # Check for level up
        c.execute('SELECT level, xp FROM levels WHERE id = ?', (user_id,))
        current_level, current_xp = c.fetchone()

        while current_xp >= calculate_xp_needed(current_level):
            current_level += 1
            c.execute('UPDATE levels SET level = ? WHERE id = ?', (current_level, user_id))

        bot.db.commit()
        return current_level, current_xp

    @bot.event
    async def on_message(message):
        if not message.author.bot:
            await add_xp(message.author.id, random.randint(1, 3))
        await bot.process_commands(message)

    @bot.command()
    async def rank(ctx, user: discord.Member = None):
        '''Displays a user's level and experience in an embed'''
        user = user or ctx.author
        c = bot.db.cursor()
        c.execute('SELECT level, xp FROM levels WHERE id = ?', (user.id,))
        result = c.fetchone()

        if result:
            level, xp = result
            xp_needed = calculate_xp_needed(level)
            embed = discord.Embed(title=f"{user.name}'s Rank", color=discord.Color.blue())
            embed.add_field(name="Level", value=str(level), inline=True)
            embed.add_field(name="XP", value=f"{xp:,}/{xp_needed:,}", inline=True)
            embed.set_thumbnail(url=user.display_avatar.url)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{user.mention} hasn't earned any XP yet!")

    @bot.command()
    async def top(ctx):
        '''Displays the top 10 users by level and experience'''
        c = bot.db.cursor()
        c.execute('SELECT id, level, xp FROM levels ORDER BY level DESC, xp DESC LIMIT 10')
        results = c.fetchall()

        if results:
            embed = discord.Embed(title='Level Leaderboard', color=discord.Color.gold())
            for rank, (user_id, level, xp) in enumerate(results, start=1):
                user = bot.get_user(user_id)
                username = user.name if user else f'User ID {user_id}'
                embed.add_field(
                    name=f'#{rank}: {username}',
                    value=f'Level {level} - {xp:,} XP',
                    inline=False
                )
            await ctx.send(embed=embed)
        else:
            await ctx.send('No users on the leaderboard yet!')
