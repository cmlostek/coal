"""Graveyard/Death log commands module"""

import io
import discord
from discord.ext import commands


def setup(bot):
    """Setup function to register commands with the bot"""

    @bot.command(name='death', aliases=['die', 'd'])
    async def death(ctx, *args):
        '''
        Logs a death adding a poor soul to the graveyard.
        args: Optional first arg is the id (mention or digits). If omitted, uses the command invoker. Any remaining args are joined as the reason.
        '''
        # IMPORTANT: Replace with your actual death channel ID
        death_channel_id = 1436031058469716058
        death_channel = bot.get_channel(death_channel_id)
        if not death_channel:
            await ctx.send(f"Error: Death channel with ID {death_channel_id} not found.")
            return

        # Determine target user_id_str and reason
        if not args:
            # Case 1: No arguments - use invoker's ID and no reason
            user_id_str = str(ctx.author.id)
            reason = None
        else:
            first = args[0]
            if first == '0' or first.startswith('<@') or first.isdigit():
                # Case 2: First argument is an ID/mention ('0' or digits)
                user_id_str = first
                reason = ' '.join(args[1:]) if len(args) > 1 else None
            else:
                # Case 3: No ID provided (first arg is part of reason) - use invoker's ID
                user_id_str = str(ctx.author.id)
                reason = ' '.join(args)

        # Clean up the ID string to only contain digits if it was a mention
        digits = ''.join(ch for ch in user_id_str if ch.isdigit())
        if not digits:
            # If it was just '0', keep it as '0'
            final_user_id = '0' if user_id_str == '0' else str(ctx.author.id)
        else:
            final_user_id = digits

        # Increment the death count and log the death using the database
        c = bot.db.cursor()
        # Get the next sequential death number (cntr)
        c.execute('SELECT MAX(cntr) FROM death_log')
        row = c.fetchone()
        num = (row[0] if row and row[0] is not None else 0) + 1

        # Insert: letting log_id AUTOINCREMENT, storing user_id, cntr, and reason
        c.execute('INSERT INTO death_log(id, cntr, reason) VALUES (?,?,?)', (final_user_id, num, reason))
        bot.db.commit()

        # Notify channel / user
        if final_user_id == '0':
            await death_channel.send(f'💀 **Death #{num}** - Anonymous\nReason: {reason or "Unknown cause."}')
            await ctx.send('A new soul has entered the graveyard anonymously.')
            print('Death logged and posted.')
        else:
            # try to mention the user
            mention = f'<@{final_user_id}>'

            if reason:
                await death_channel.send(
                    f'💀 **Death #{num}** - You have met a terrible fate, {mention}.\nReason: {reason}')
            else:
                await death_channel.send(f'💀 **Death #{num}** - You have met a terrible fate, {mention}.')

            await ctx.send('A new soul has entered the graveyard.')

    @bot.command(name='revive', aliases=['resurrect', 'undeath', 'r'])
    async def revive(ctx, *args):
        '''
        Revives a user by removing their most recent death from the graveyard.
        :user_id The ID of the user to revive (mention or digits).
        '''
        death_channel_id = 1436031058469716058
        death_channel = bot.get_channel(death_channel_id)
        if not death_channel:
            await ctx.send(f"Error: Death channel with ID {death_channel_id} not found.")
            return

        if not args:
            # Case 1: No arguments - use invoker's ID and no reason
            user_id_str = str(ctx.author.id)
            reason = None
        else:
            first = args[0]
            if first == '0' or first.startswith('<@') or first.isdigit():
                # Case 2: First argument is an ID/mention ('0' or digits)
                user_id_str = first
                reason = ' '.join(args[1:]) if len(args) > 1 else None
            else:
                # Case 3: No ID provided (first arg is part of reason) - use invoker's ID
                user_id_str = str(ctx.author.id)
                reason = ' '.join(args)

        # Clean up the ID string to only contain digits if it was a mention
        digits = ''.join(ch for ch in user_id_str if ch.isdigit())
        if digits:
            target_id_for_query = digits
        else:
            await ctx.send('Invalid user ID provided for revival.')
            return

        if target_id_for_query == '0':
            await ctx.send('Cannot revive anonymous deaths (ID 0).')
            return

        await death_channel.send(
            f'🕊️ A soul has been revived: <@{target_id_for_query}>. \n  They found the reason to live because of {str(reason)}' or 'No reason provided.')

    @bot.command(name='obit', aliases=['obituary', 'death_log', 'deaths', 'log', 'l'])
    async def obit(ctx, *args):
        '''
        Retrieves and sends the obituary for a specific user.
        :args The ID of the user whose obituary is to be retrieved. If None, retrieves the log for the command invoker.
        Use -1 to get the entire log as a file.
        Use 0 to get logs for generic/anonymous deaths.
        '''
        # Determine the target user_id for query
        if not args:
            user_id = str(ctx.author.id)
        else:
            user_id = args[0]

        # Normalize user lookup: prefer digits extracted from mention or id
        digits = ''.join(ch for ch in user_id if ch.isdigit())
        if digits:
            target_id_for_query = digits
        else:
            target_id_for_query = user_id  # Allows for literal '-1' or '0'

        c = bot.db.cursor()

        # Special case: Entire Log (-1)
        if target_id_for_query == '-1':
            # Retrieve all columns. id is now log_id, but the user_id is the second column
            c.execute('SELECT id, cntr, reason FROM death_log ORDER BY cntr')
            rows = c.fetchall()
            if not rows:
                await ctx.send('No death logs found. (The graveyard is empty.)')
                return

            lines = []
            for r in rows:
                # r[0] is user_id, r[1] is cntr, r[2] is reason
                lines.append(f'[{r[1]}] User ID: {r[0]} | Reason: {r[2] or "No reason"}')

            content = '\n'.join(lines)
            fp = io.BytesIO(content.encode('utf-8'))
            await ctx.send('Here is the full death log.', file=discord.File(fp, filename='death_log.txt'))
            return

        # Special case: Anonymous Logs (0)
        elif target_id_for_query == '0':
            c.execute("SELECT cntr, reason FROM death_log WHERE id = '0' ORDER BY cntr")
            rows = c.fetchall()
            if not rows:
                await ctx.send('No anonymous death logs found.')
                return

            lines = [f'**{r[0]}** - {r[1] or "No reason"}' for r in rows]
            msg = discord.Embed(
                title='💀 Anonymous Death Logs (ID 0)',
                description='\n'.join(lines),
                color=discord.Color.dark_red()
            )
            msg.set_footer(text=f'Total Anonymous Deaths: {len(rows)}')
            await ctx.send(embed=msg)
            return

        # Regular User Lookup
        # Search by the exact user_id string
        c.execute('SELECT cntr, reason FROM death_log WHERE id = ? ORDER BY cntr DESC', (target_id_for_query,))
        rows = c.fetchall()

        if rows:
            user_logs_count = len(rows)
            # Get the first 50 entries (since they are ordered descending by cntr, this is the most recent 50)
            recent_rows = rows[:10]
            desc_lines = [f'**{r[0]}** - {r[1] or "Rest In Peace :("}' for r in recent_rows]
            reversed_desc_lines = list(reversed(desc_lines))  # Show oldest first in the embed
            # try to resolve a nice username for the embed title
            title_user = target_id_for_query
            try:
                fetched = await bot.fetch_user(int(target_id_for_query))
                title_user = str(fetched)
            except Exception:
                pass  # Use the digits if fetching user fails

            msg = discord.Embed(
                title=f'💀 Obituary for {title_user}',
                description='\n'.join(desc_lines),
                color=discord.Color.red()
            )
            msg.set_footer(
                text=f'Total deaths: {user_logs_count}.\n Showing last {len(recent_rows)} entries. | May they rest in peace.')
            await ctx.send(embed=msg)

            if user_logs_count >= 100:
                await ctx.send('Holy smokes, that is a lot of deaths... you might want to stop dying! 🤯')
        else:
            await ctx.send('Hmmmm, they don\'t seem dead yet... keep trying! 😉')