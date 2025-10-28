"""Gambling commands module"""

import random
import discord
from discord.ext import commands
import sqlite3 as sql


def setup(bot):
    """Setup function to register commands with the bot"""

    @bot.command()
    async def balance(ctx):
        user_id = ctx.author.id

        try:
            c = bot.db.cursor()
            c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
            result = c.fetchone()

            if result:
                balance = result[0]
                await ctx.send(f'Your current balance is: 💰 {balance:,} coins')
            else:
                # Initialize new user with starting balance of 1000
                c.execute('INSERT INTO balances (user_id, balance) VALUES (?, ?)', (user_id, 1000))
                bot.db.commit()
                await ctx.send('Welcome! Your starting balance is: 💰 1,000 coins')

        except sql.Error as e:
            await ctx.send(f'Error accessing balance: {e}')
            print(f'Database error in balance command: {e}')

    @bot.command()
    async def leaderboard(ctx):
        try:
            c = bot.db.cursor()
            c.execute('SELECT user_id, balance FROM balances ORDER BY balance DESC')
            results = c.fetchall()

            if not results:
                await ctx.send("No balances found!")
                return

            embed = discord.Embed(
                title="💰 Wealth Leaderboard",
                description="Top balances in the server",
                color=discord.Color.gold()
            )

            for i, (user_id, balance) in enumerate(results[:10], 1):
                try:
                    user = await bot.fetch_user(user_id)
                    username = user.name
                except:
                    username = f"User {user_id}"

                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                embed.add_field(
                    name=f"{medal} {username}",
                    value=f"{balance:,} coins",
                    inline=False
                )

            embed.set_footer(text=f"Requested by {ctx.author.name}")
            await ctx.send(embed=embed)

        except sql.Error as e:
            await ctx.send(f"Error accessing leaderboard: {e}")
            print(f"Database error in leaderboard command: {e}")

    @bot.command()
    async def give(ctx, user: discord.Member, amount: int):
        '''Gives a specified amount of coins to another user.'''
        if ctx.author.id == user.id:
            await ctx.send("You can't give yourself coins!")
            return

        if amount <= 0:
            await ctx.send("Please enter a positive amount to give.")
            return

        user_id = ctx.author.id
        target_id = user.id

        try:
            c = bot.db.cursor()
            # Check sender's balance
            c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
            sender_balance = c.fetchone()

            if not sender_balance or sender_balance[0] < amount:
                await ctx.send("You don't have enough coins!")
                return

            # Check if recipient exists in database
            c.execute('SELECT balance FROM balances WHERE user_id = ?', (target_id,))
            recipient_balance = c.fetchone()

            if not recipient_balance:
                # Initialize recipient with starting balance
                c.execute('INSERT INTO balances (user_id, balance) VALUES (?, ?)', (target_id, 1000))

            # Perform the transaction
            c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (amount, target_id))
            bot.db.commit()

            await ctx.send(f"Successfully transferred {amount:,} coins to {user.name}!")

        except sql.Error as e:
            await ctx.send(f"Error processing transaction: {e}")
            print(f"Database error in give command: {e}")

    @bot.command()
    async def coinflip(ctx, flip, bet=100):
        '''Flips a coin and returns the result.'''
        user_id = ctx.author.id
        c = bot.db.cursor()
        c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
        result = c.fetchone()

        if not result:
            c.execute('INSERT INTO balances (user_id, balance) VALUES (?, ?)', (user_id, 1000))
            bot.db.commit()
            balance = 1000
            await ctx.send("Have you been here before? I'll give you a starting balance of 1,000 coins.")
        else:
            balance = result[0]

        if balance < bet:
            await ctx.send("You don't have enough coins for this bet!")
            return

        # Remove bet amount first
        c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (bet, user_id))
        bot.db.commit()

        result = random.choice(['heads', 'tails'])
        if flip.lower() == result:
            # Add winnings if won
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (bet * 2, user_id))
            await ctx.send(f"The coin landed on: **{result}**\nYou won {bet} coins!")
        else:
            await ctx.send(f"The coin landed on: **{result}**\nYou lost {bet} coins!")
        bot.db.commit()

    @bot.command()
    async def roll(ctx, number_of_dice: int = 1, bet=100):
        '''Rolls a dice with a specified number of sides.'''
        user_id = ctx.author.id
        c = bot.db.cursor()
        c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
        result = c.fetchone()

        if not result:
            c.execute('INSERT INTO balances (user_id, balance) VALUES (?, ?)', (user_id, 1000))
            bot.db.commit()
            balance = 1000
            await ctx.send("Have you been here before? I'll give you a starting balance of 1,000 coins.")
        else:
            balance = result[0]

        if balance < bet:
            await ctx.send("You don't have enough coins for this bet!")
            return

        if number_of_dice > 100:
            await ctx.send("Sorry, I can't roll that many dice.")
            return

        # Remove bet amount first
        c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (bet, user_id))
        bot.db.commit()

        rolls = [random.randint(1, 6) for _ in range(6)]
        if sum(rolls) >= (number_of_dice * 3):
            # Add winnings if won
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (bet * 6, user_id))
            await ctx.send(f"Congratulations! You won {bet * 5} coins!")
        else:
            await ctx.send(
                f"You rolled {rolls} which has a sum of {sum(rolls)} which does not meet the score and lost {bet} coins.")
        bot.db.commit()

    @bot.command()
    async def slots(ctx, bet: int = 100):
        '''Rolls a slot machine with a specified number of dice.'''
        # Get user's balance
        user_id = ctx.author.id
        c = bot.db.cursor()
        c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
        result = c.fetchone()

        if not result:
            c.execute('INSERT INTO balances (user_id, balance) VALUES (?, ?)', (user_id, 1000))
            bot.db.commit()
            balance = 1000
            await ctx.send("Have you been here before? I'll give you a starting balance of 1,000 coins.")
        else:
            balance = result[0]

        if balance < bet:
            await ctx.send("You don't have enough coins for this bet!")
            return

        if bet <= 0:
            await ctx.send("Please enter a positive amount to bet.")
            return
        elif bet > 1000:
            await ctx.send("Sorry, I can't bet that much.")
            return

        # Remove bet amount first
        c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (bet, user_id))
        bot.db.commit()

        symbols = ['⭐', '🍒', '🍋', '🍊', '🍉', '7️⃣', '💰', '💎', '💵']
        result = []
        for _ in range(3):
            result.append(random.choice(symbols))
        await ctx.send(f"🎰 Slot machine result: {' | '.join(result)}")

        if result.count('⭐') == 3:
            # jackpot
            winnings = bet * 100
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"You got a JACKPOT! You won {winnings} coins!")
        elif result.count('⭐') == 0 and result[0] == result[1] == result[2]:
            # All three symbols are the same and NOT stars
            winnings = bet * 50
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"Congratulations! You won {winnings} coins!")
        elif result.count('⭐') == 1 and (result[0] == result[1] or result[1] == result[2] or result[0] == result[2]):
            # Two symbols are the same and one is a star
            winnings = bet * 10
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"You got a match with a wild! You won {winnings} coins!")
        elif result.count('⭐') == 2 and len(set(result)) == 2:
            # 2 symbols are stars and the third does not matter
            winnings = bet * 5
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"You got two stars! You won {winnings} coins!")
        elif result.count('⭐') == 1 and not (
                result[0] == result[1] or result[1] == result[2] or result[0] == result[2]):
            # One symbol is a star the other 2 are NOT the same
            winnings = bet * .3
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"You got a star! You won {winnings} coins!")
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            # Two symbols are the same
            winnings = bet * .2
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"You got a double! You won {winnings} coins!")
        else:
            await ctx.send(f"Sorry, you lost {bet} coins.")
        bot.db.commit()