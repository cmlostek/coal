"""modules/economy.py – Economy / currency system (Cog version)."""
import random
import discord
from discord.ext import commands
from datetime import datetime


class Economy(commands.Cog):
    """Coins, gambling, and the server economy."""

    def __init__(self, bot):
        self.bot = bot

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_balance(self, user_id: int) -> int:
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
            row = await cur.fetchone()
            if row:
                return row['balance']
            await cur.execute('INSERT INTO balances (user_id, balance) VALUES (?, 1000)', (user_id,))
        await self.bot.db.commit()
        return 1000

    async def _add_balance(self, user_id: int, amount: int):
        await self._get_balance(user_id)  # ensure row exists
        async with self.bot.db.cursor() as cur:
            await cur.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        await self.bot.db.commit()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name='balance', aliases=['bal'])
    async def balance(self, ctx, user: discord.Member = None):
        """Check your or another user's coin balance."""
        target = user or ctx.author
        bal = await self._get_balance(target.id)
        embed = discord.Embed(
            title=f'💰 {target.display_name}\'s Balance',
            description=f'**{bal:,}** coins',
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @commands.command(name='daily')
    async def daily(self, ctx):
        """Claim your daily 500-coin reward."""
        uid = ctx.author.id
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT balance, last_daily FROM balances WHERE user_id = ?', (uid,))
            row = await cur.fetchone()

        if not row:
            await self._get_balance(uid)
            async with self.bot.db.cursor() as cur:
                await cur.execute('SELECT balance, last_daily FROM balances WHERE user_id = ?', (uid,))
                row = await cur.fetchone()

        today = datetime.now().date()
        last_daily = datetime.strptime(row['last_daily'], '%Y-%m-%d').date() if row['last_daily'] else None

        if last_daily and today <= last_daily:
            return await ctx.send(embed=discord.Embed(
                description='You already claimed your daily today. Come back tomorrow!',
                color=discord.Color.red(),
            ))

        amount = 500
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'UPDATE balances SET balance = balance + ?, last_daily = ? WHERE user_id = ?',
                (amount, today.strftime('%Y-%m-%d'), uid),
            )
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(
            description=f'💰 You claimed **{amount:,}** coins! Come back tomorrow for more.',
            color=discord.Color.gold(),
        ))

    @commands.command(name='leaderboard', aliases=['richest'])
    async def leaderboard(self, ctx):
        """Top 10 richest users."""
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT user_id, balance FROM balances ORDER BY balance DESC LIMIT 10')
            rows = await cur.fetchall()

        if not rows:
            return await ctx.send('No balances recorded yet.')

        medals = ['🥇', '🥈', '🥉'] + ['🏅'] * 7
        embed = discord.Embed(title='💰 Wealth Leaderboard', color=discord.Color.gold())
        for i, row in enumerate(rows):
            try:
                user = ctx.guild.get_member(row['user_id']) or await self.bot.fetch_user(row['user_id'])
                name = user.display_name
            except Exception:
                name = f'User {row["user_id"]}'
            embed.add_field(name=f'{medals[i]} {name}', value=f'{row["balance"]:,} coins', inline=False)
        embed.set_footer(text=f'Requested by {ctx.author.display_name}')
        await ctx.send(embed=embed)

    @commands.command(name='give')
    async def give(self, ctx, user: discord.Member, amount: int):
        """Transfer coins to another user."""
        if ctx.author.id == user.id:
            return await ctx.send('You cannot give coins to yourself.')
        if amount <= 0:
            return await ctx.send('Amount must be positive.')
        bal = await self._get_balance(ctx.author.id)
        if bal < amount:
            return await ctx.send(f'You only have **{bal:,}** coins.')
        await self._get_balance(user.id)
        async with self.bot.db.cursor() as cur:
            await cur.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (amount, ctx.author.id))
            await cur.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (amount, user.id))
        await self.bot.db.commit()
        await ctx.send(embed=discord.Embed(
            description=f'💸 Transferred **{amount:,}** coins to {user.mention}.',
            color=discord.Color.green(),
        ))

    @commands.command(name='coinflip', aliases=['cf'])
    async def coinflip(self, ctx, guess: str, bet: int = 100):
        """Guess heads or tails. Win 2x on correct guess."""
        guess = guess.lower()
        if guess not in ('heads', 'tails', 'h', 't'):
            return await ctx.send('Guess must be `heads` or `tails`.')
        guess = 'heads' if guess in ('heads', 'h') else 'tails'
        if bet <= 0:
            return await ctx.send('Bet must be positive.')
        bal = await self._get_balance(ctx.author.id)
        if bal < bet:
            return await ctx.send(f'You only have **{bal:,}** coins.')

        result = random.choice(['heads', 'tails'])
        won = guess == result
        delta = bet if won else -bet

        async with self.bot.db.cursor() as cur:
            await cur.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (delta, ctx.author.id))
        await self.bot.db.commit()

        embed = discord.Embed(
            title=f'🪙 Coin Flip — {result.title()}',
            description=('✅ You won **{:,}** coins!'.format(bet) if won else '❌ You lost **{:,}** coins.'.format(bet)),
            color=discord.Color.green() if won else discord.Color.red(),
        )
        await ctx.send(embed=embed)

    @commands.command(name='roll')
    async def roll(self, ctx, dice: int = 1, bet: int = 100):
        """Roll dice. Sum ≥ dice×3 to win 5× bet."""
        if dice < 1 or dice > 20:
            return await ctx.send('Roll 1–20 dice.')
        if bet <= 0:
            return await ctx.send('Bet must be positive.')
        bal = await self._get_balance(ctx.author.id)
        if bal < bet:
            return await ctx.send(f'You only have **{bal:,}** coins.')

        rolls = [random.randint(1, 6) for _ in range(dice)]
        total = sum(rolls)
        target = dice * 3
        won = total >= target
        delta = bet * 5 if won else -bet

        async with self.bot.db.cursor() as cur:
            await cur.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (delta, ctx.author.id))
        await self.bot.db.commit()

        roll_str = ' + '.join(str(r) for r in rolls) + f' = **{total}**'
        embed = discord.Embed(
            title=f'🎲 Dice Roll (need ≥ {target})',
            description=roll_str,
            color=discord.Color.green() if won else discord.Color.red(),
        )
        embed.add_field(name='Result', value=f'✅ Won **{bet*5:,}** coins!' if won else f'❌ Lost **{bet:,}** coins.')
        await ctx.send(embed=embed)

    @commands.command(name='slots')
    async def slots(self, ctx, bet: int = 100):
        """Spin the slot machine."""
        if bet <= 0 or bet > 3000:
            return await ctx.send('Bet must be between 1 and 3,000 coins.')
        bal = await self._get_balance(ctx.author.id)
        if bal < bet:
            return await ctx.send(f'You only have **{bal:,}** coins.')

        symbols = ['⭐', '🍒', '🍋', '🍊', '🍉', '7️⃣', '💰', '💎', '💵']
        reels = [random.choice(symbols) for _ in range(3)]
        stars = reels.count('⭐')

        if stars == 3:
            multiplier, label = 100, '🎰 **JACKPOT!**'
        elif stars == 0 and reels[0] == reels[1] == reels[2]:
            multiplier, label = 50, '🎉 Triple match!'
        elif stars == 1 and len(set(reels)) == 2:
            multiplier, label = 10, '✨ Wild match!'
        elif stars == 2:
            multiplier, label = 5, '⭐ Two stars!'
        elif stars == 1:
            multiplier, label = 3, '⭐ One star!'
        elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
            multiplier, label = 2, '👀 Pair!'
        else:
            multiplier, label = 0, '😔 No match.'

        delta = bet * multiplier - bet if multiplier else -bet
        async with self.bot.db.cursor() as cur:
            await cur.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (delta, ctx.author.id))
        await self.bot.db.commit()

        embed = discord.Embed(
            title='🎰 Slot Machine',
            description=f'**{" | ".join(reels)}**\n\n{label}',
            color=discord.Color.gold() if delta > 0 else discord.Color.red(),
        )
        if delta > 0:
            embed.add_field(name='Won', value=f'+**{delta:,}** coins')
        else:
            embed.add_field(name='Lost', value=f'**{abs(delta):,}** coins')
        await ctx.send(embed=embed)

    @commands.command(name='work')
    async def work(self, ctx):
        """Work for coins (1-hour cooldown)."""
        uid = ctx.author.id
        async with self.bot.db.cursor() as cur:
            await cur.execute('SELECT balance, last_work FROM balances WHERE user_id = ?', (uid,))
            row = await cur.fetchone()

        if not row:
            await self._get_balance(uid)
            async with self.bot.db.cursor() as cur:
                await cur.execute('SELECT balance, last_work FROM balances WHERE user_id = ?', (uid,))
                row = await cur.fetchone()

        now = datetime.now()
        if row['last_work']:
            try:
                last = datetime.strptime(row['last_work'], '%Y-%m-%d %H:%M:%S.%f')
                secs = (now - last).total_seconds()
                if secs < 3600:
                    mins = int((3600 - secs) / 60)
                    return await ctx.send(embed=discord.Embed(
                        description=f'⏳ You need to wait **{mins}** more minutes before working.',
                        color=discord.Color.red(),
                    ))
            except Exception:
                pass

        success_phrases = [
            'Dr. Najjar asked you to finish the slides and you nailed it!',
            'You graded 100 assignments in record time!',
            'You fixed a critical bug and saved the day!',
            'You aced your exams! Congrats!',
            'You organised a stellar department event!',
        ]
        fail_phrases = [
            'You tried to edit Canvas and broke the HTML.',
            'You pushed to main instead of dev. Everything is on fire.',
            'You spilled coffee on your keyboard.',
            'You accidentally emailed the whole university.',
        ]

        earnings = random.randint(50, 500)
        won = random.randint(1, 100) > 25
        delta = earnings if won else -earnings

        now_str = now.strftime('%Y-%m-%d %H:%M:%S.%f')
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'UPDATE balances SET balance = balance + ?, last_work = ? WHERE user_id = ?',
                (delta, now_str, uid),
            )
        await self.bot.db.commit()

        phrase = random.choice(success_phrases if won else fail_phrases)
        embed = discord.Embed(
            description=f'{phrase}\n\n{"+" if won else ""}{delta:,} coins',
            color=discord.Color.green() if won else discord.Color.red(),
        )
        await ctx.send(embed=embed)

    @commands.command(name='rob')
    async def rob(self, ctx, target: discord.Member):
        """Attempt to rob another user (risky!)."""
        if target.id == ctx.author.id:
            return await ctx.send('You cannot rob yourself.')
        target_bal = await self._get_balance(target.id)
        if target_bal < 100:
            return await ctx.send('That person is too broke to rob.')

        caught = random.randint(1, 100) <= 75
        if caught:
            loss = random.randint(100, 1000)
            await self._add_balance(ctx.author.id, -min(loss, await self._get_balance(ctx.author.id)))
            await ctx.send(embed=discord.Embed(
                description=f'🚔 You got caught and lost **{loss:,}** coins!',
                color=discord.Color.red(),
            ))
        else:
            stolen = random.randint(1, min(target_bal, 500))
            await self._add_balance(target.id, -stolen)
            await self._add_balance(ctx.author.id, stolen)
            await ctx.send(embed=discord.Embed(
                description=f'💸 You stole **{stolen:,}** coins from {target.display_name}!',
                color=discord.Color.green(),
            ))

    # ── Admin commands ─────────────────────────────────────────────────────────

    @commands.command(name='a_give')
    @commands.has_permissions(administrator=True)
    async def a_give(self, ctx, user: discord.Member, amount: int):
        """[Admin] Grant coins without deducting from anyone."""
        if amount <= 0:
            return await ctx.send('Amount must be positive.')
        await self._add_balance(user.id, amount)
        await ctx.send(embed=discord.Embed(
            description=f'✅ Granted **{amount:,}** coins to {user.mention}.',
            color=discord.Color.green(),
        ))

    @commands.command(name='a_take')
    @commands.has_permissions(administrator=True)
    async def a_take(self, ctx, user: discord.Member, amount: int):
        """[Admin] Remove coins from a user."""
        if amount <= 0:
            return await ctx.send('Amount must be positive.')
        await self._add_balance(user.id, -amount)
        await ctx.send(embed=discord.Embed(
            description=f'✅ Removed **{amount:,}** coins from {user.mention}.',
            color=discord.Color.green(),
        ))


async def setup(bot):
    await bot.add_cog(Economy(bot))
