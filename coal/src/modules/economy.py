"""Economy commands module"""

import random
import discord
from discord import user
from discord.ext import commands
import sqlite3 as sql


def setup(bot):
    """Setup function to register commands with the bot"""

    @bot.command()
    async def balance(ctx, user: discord.Member = None):
        user_id = user.id if user else ctx.author.id

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

    @bot.command(alias = 'bal')
    async def daily(ctx):
        user_id = ctx.author.id
        c = bot.db.cursor()
        c.execute('SELECT balance, last_daily FROM balances WHERE user_id = ?', (user_id,))
        result = c.fetchone()

        if not result:
            await ctx.send("Please run `-balance` first to initialize your account!")
            return

        import datetime
        current_time = datetime.datetime.now().date()
        last_daily = datetime.datetime.strptime(result[1], '%Y-%m-%d').date() if result[1] else None

        if last_daily and current_time <= last_daily:
            await ctx.send("You've already claimed your daily reward today! Come back tomorrow!")
            return

        daily_amount = 500
        c.execute('UPDATE balances SET balance = balance + ?, last_daily = ? WHERE user_id = ?',
                  (daily_amount, current_time.strftime('%Y-%m-%d'), user_id))
        await ctx.send(f"You've received your daily reward of {daily_amount:,} coins!")
        bot.db.commit()

        bot.db.commit()
            

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

        rolls = [random.randint(1, 6) for _ in range(number_of_dice)]
        result = number_of_dice * random.randint(1, 4)
        if sum(rolls) >= result:
            # Add winnings if won
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (bet * 6, user_id))
            await ctx.send(f"Congratulations! You won {bet * 5} coins!")
        else:
            await ctx.send(
                f"You rolled {rolls} which has a sum of {sum(rolls)} which does not meet the score {result} and lost {bet} coins.")
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
        elif bet > 3000:
            await ctx.send("Sorry, I can't bet that much.")
            return

        # Remove bet amount first
        c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (bet, user_id))
        bot.db.commit()

        symbols = ['⭐', '🍒', '🍋', '🍊', '🍉', '7️⃣', '💰', '💎', '💵']
        result = []
        for _ in range(3):
            symbols_copy = symbols.copy()
            random.shuffle(symbols_copy)
            result.append(symbols_copy[0])
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
            winnings = bet * 3
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"You got a star! You won {winnings} coins!")
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            # Two symbols are the same
            winnings = bet * 2
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
            await ctx.send(f"You got a double! You won {winnings} coins!")
        else:
            await ctx.send(f"Sorry, you lost {bet} coins.")
        bot.db.commit()

    @bot.command()
    async def work(ctx):
        '''Work for money!'''
        user_id = ctx.author.id
        c = bot.db.cursor()

        # Check last work time
        c.execute('SELECT balance, last_work FROM balances WHERE user_id = ?', (user_id,))
        result = c.fetchone()

        import datetime
        current_time = datetime.datetime.now()

        if not result:
            c.execute('INSERT INTO balances (user_id, balance, last_work) VALUES (?, ?, ?)',
                          (user_id, 1000, current_time.strftime('%Y-%m-%d %H:%M:%S.%f')))
            bot.db.commit()
        else:
            balance = result[0]
            last_work = datetime.datetime.strptime(result[1], '%Y-%m-%d %H:%M:%S.%f') if result[1] else None

            if last_work and (current_time - last_work).total_seconds() < 3600:
                time_left = 3600 - (current_time - last_work).total_seconds()
                minutes = int(time_left / 60)
                await ctx.send(f"You need to wait {minutes} minutes before working again!")
                return

        earnings = random.randint(0, 500)
        outcome = random.randint(1, 100)
        phrases_success = [
            'Dr. Najjar asked you to complete the slides and you got it done in time and they look good!',
            'You graded 100 assignments in record time!', 'You fixed a critical bug in the codebase and saved the day!',
            'You lead the lab flawlessly and the students all got their assignment reviewed.',
            'You organized a successful event for the department!', 'you ate it UP!!!',
            'You worked your butt of an aced your exams! Congrats!'
        ]

        phrases_failure = [
            'You tried to edit the canvas and broke the entire HTML.',
            'Instead of pushing to the dev branch you pushed to main and now everything is broken.',
            'youre FIREDDDDDD',
            'You accidentally deleted the entire project folder.',
            'You spilled coffee on your keyboard and it stopped working.',
            'You sent an email to the entire university by mistake.'
        ]
        if outcome <= 25:
            await ctx.send(f"{random.choice(phrases_failure)} \n You lost {earnings} coins.")
            c.execute('UPDATE balances SET balance = balance - ?, last_work = ? WHERE user_id = ?',
                          (earnings, current_time.strftime('%Y-%m-%d %H:%M:%S.%f'), user_id))
            bot.db.commit()
        else:
            await ctx.send(f"{random.choice(phrases_success)} \n You earned {earnings} coins.")
            c.execute('UPDATE balances SET balance = balance + ?, last_work = ? WHERE user_id = ?',
                          (earnings, current_time.strftime('%Y-%m-%d %H:%M:%S.%f'), user_id))
            bot.db.commit()
    @bot.command()
    async def a_give(ctx, user: discord.Member, amount: int):
        if amount <= 0:
            await ctx.send("Please enter a positive amount to give.")
            return

        target_id = user.id

        try:
            c = bot.db.cursor()
            # Check if recipient exists in database
            c.execute('SELECT balance FROM balances WHERE user_id = ?', (target_id,))
            recipient_balance = c.fetchone()

            if not recipient_balance:
                # Initialize recipient with starting balance
                c.execute('INSERT INTO balances (user_id, balance) VALUES (?, ?)', (target_id, 1000))

            # Perform the transaction
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (amount, target_id))
            bot.db.commit()

            await ctx.send(f"Successfully granted {amount:,} coins to {user.name}!")

        except sql.Error as e:
            await ctx.send(f"Error processing transaction: {e}")
            print(f"Database error in a_give command: {e}")


    @bot.command()
    async def a_take(ctx, user: discord.Member, amount: float):
        '''Admin command to take a specified amount of coins from another user.'''
        if amount <= 0:
            await ctx.send("Please enter a positive amount to take.")
            return

        user_id = ctx.author.id
        target_id = user.id

        try:
            c = bot.db.cursor()
            # Check recipient's balance
            c.execute('SELECT balance FROM balances WHERE user_id = ?', (target_id,))
            recipient_balance = c.fetchone()

            if not recipient_balance or recipient_balance[0] < amount:
                await ctx.send("The user doesn't have enough coins!")
                return

            # Perform the transaction
            c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (amount, target_id))
            bot.db.commit()

            await ctx.send(f"Successfully took {amount:,} coins from {user.name}!")

        except sql.Error as e:
            await ctx.send(f"Error processing transaction: {e}")
            print(f"Database error in a_take command: {e}")

    @bot.command()
    async def rob(ctx, user_id: int):
        '''Rob another user of a random amount of coins.'''
        c = bot.db.cursor()
        c.execute('SELECT balance FROM balances WHERE user_id = ?', (user_id,))
        result = c.fetchone()

        if not result:
            await ctx.send("The user you are trying to rob does not have an account!")
            return
        else:
            user_balance = result[0]
            outcome = random.randint(1, 100)
            loss = random.randint(100, 1000)
            if outcome <= 75:
                await ctx.send(f"You got caught and were sent to jail! You lost {loss} coins.")
                c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (loss, ctx.author.id))
            else:
                amount = random.randint(1, user_balance)
                c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
                c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (amount, ctx.author.id))
                bot.db.commit()
                await ctx.send(f"You stole {amount:,} coins from {user_id}'s account!")

    @bot.command()
    async def scratch(ctx, bet: int = 100):
        '''Scratch another user of a random amount of coins.'''
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
        elif bet > 3000:
            await ctx.send("Sorry, I can't bet that much.")
            return

        # Remove bet amount first
        c.execute('UPDATE balances SET balance = balance - ? WHERE user_id = ?', (bet, user_id))
        bot.db.commit()

        symbols = ['⭐', '🍒', '🍋', '🍊', '🍉', '7️⃣', '💰', '💎', '💵']
        result = []
        for _ in range(3):
            symbols_copy = symbols.copy()
            random.shuffle(symbols_copy)
            result.append(f"||{symbols_copy[0]}||")
        await ctx.send(f"🎰 Slot machine result: {' | '.join(result)}")

        if result.count('⭐') == 3:
            # jackpot
            winnings = bet * 100
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
        elif result.count('⭐') == 0 and result[0] == result[1] == result[2]:
            # All three symbols are the same and NOT stars
            winnings = bet * 50
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
        elif result.count('⭐') == 1 and (result[0] == result[1] or result[1] == result[2] or result[0] == result[2]):
            # Two symbols are the same and one is a star
            winnings = bet * 10
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
        elif result.count('⭐') == 2 and len(set(result)) == 2:
            # 2 symbols are stars and the third does not matter
            winnings = bet * 5
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
        elif result.count('⭐') == 1 and not (
                result[0] == result[1] or result[1] == result[2] or result[0] == result[2]):
            # One symbol is a star the other 2 are NOT the same
            winnings = bet * 3
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            # Two symbols are the same
            winnings = bet * 2
            c.execute('UPDATE balances SET balance = balance + ? WHERE user_id = ?', (winnings + bet, user_id))
        bot.db.commit()



