"""Utility commands module"""

import re
import io
import datetime
import asyncio
from PIL import Image
import discord
from discord.ext import commands


def setup(bot):
    """Setup function to register commands with the bot"""

    @bot.command()
    async def help(ctx):
        '''Displays a list of available commands.'''
        embed = discord.Embed(title='Help', description='[Documentation](https://github.com/cmlostek/coal/blob/main/README.md) ',  color=discord.Color.blue())
        embed.add_field(name='Utility', value='`ping`, `greet`, `echo`, `color`, `whois`, `snipe`', inline=False)
        embed.add_field(name='Minecraft', value='`status`', inline=False)
        embed.add_field(name='Economy', value='`balance`, `daily`, `leaderboard`,`coinflip`, `roll`, `slots`, `give`, `rob` `scratch`', inline=False)
        embed.add_field(name='Graveyard', value='`death`, `revive`, `obit`', inline=False)
        embed.add_field(name='levels', value='`rank`, `top`', inline=False)
        await ctx.send(embed=embed)

    @bot.command()
    async def ping(ctx):
        '''Responds with the bot latency! Use to test if the bot is responsive.'''
        await ctx.send(f'Pong! {round(bot.latency * 1000, 2)}ms')

    @bot.command()
    async def greet(ctx):
        '''Sends a greeting message to the user.'''
        await ctx.send('Greetings! How can I help you today? 👋')

    @bot.command()
    async def echo(ctx, *, message):
        '''Echoes the provided message back to the user.'''
        await ctx.send(message)
        await ctx.message.delete()

    @bot.command(name='color',
                 description='Sends an embed where the embed color and the image in the embed is the provided color.',
                 aliases=['colour', 'c'])
    async def color(ctx, hexcode):
        if not hexcode:
            await ctx.send('Please provide a valid hexcode.')
            return

        if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', hexcode):
            await ctx.send('Please provide a valid hexcode.')
            return
        # Create color image
        img = Image.new('RGB', (100, 100), hexcode)
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Create embed with image
        embed = discord.Embed(color=int(hexcode.replace('#', '0x'), 0),
                              description='The color of this embed is: ' + hexcode)
        embed.set_thumbnail(url="attachment://color.png")

        # Send embed with image
        await ctx.send(file=discord.File(img_bytes, filename="color.png"), embed=embed)

    @bot.command(name='whois', description='Fetches information about a user.',
                 aliases=['userinfo', 'uinfo', 'who', 'user', 'w'])
    async def whois(ctx, user: discord.Member = None):
        if not user:
            user = ctx.author
        embed = discord.Embed(title=f'User Info - {user}', color=discord.Color.blue())
        embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
        embed.add_field(name='Username', value=str(user), inline=True)
        embed.add_field(name='User ID', value=user.id, inline=True)
        embed.add_field(name='Account Created', value=user.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name='Joined Server', value=user.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name='Roles', value=', '.join([role.name for role in user.roles]))
        embed.add_field(name='Top Role', value=user.top_role.mention, inline=True)
        embed.set_footer(text=f'Requested by {ctx.author}')
        await ctx.send(embed=embed)

    # Snipe functionality
    snipe_messages_delete = {}

    @bot.event
    async def on_message_delete(message):
        # Ignore DMs or messages without content (e.g., embeds, system messages)
        if message.guild and message.content:
            snipe_messages_delete[message.channel.id] = (
                message.content,
                message.author,
                message.created_at
            )

    @bot.command()
    async def snipe(ctx):
        '''Retrieves the last deleted message in the channel.'''
        sniped_data = snipe_messages_delete.get(ctx.channel.id)

        if sniped_data:
            content, author, timestamp = sniped_data

            embed = discord.Embed(
                description=content,
                color=discord.Color.purple(),
                timestamp=timestamp
            )
            embed.set_author(name=str(author), icon_url=author.avatar.url if author.avatar else None)
            embed.set_footer(text=f'Sniped by {ctx.author.name}')

            # Remove the message immediately after sniping so it can't be sniped again
            del snipe_messages_delete[ctx.channel.id]

            await ctx.send(embed=embed)
        else:
            await ctx.send('No recently deleted messages to snipe. 😔')


    @bot.command()
    async def schedule_send(ctx, channel: discord.TextChannel, date: str, time: str, *, message: str):
        '''Schedules a message to be sent to a channel at a specific date and time
        Format: YYYY-MM-DD HH:MM'''
        try:
            # Parse date and time
            dt_str = f"{date} {time}"
            schedule_time = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

            # Calculate delay in seconds
            now = datetime.datetime.now()
            if schedule_time <= now:
                await ctx.send("Cannot schedule messages in the past!")
                return

            delay = (schedule_time - now).total_seconds()

            # Schedule the message
            async def send_scheduled_message():
                await asyncio.sleep(delay)
                try:
                    await bot.fetch_channel(channel.id)
                    await channel.send(message)
                    await ctx.send(f"Scheduled message has been sent to {channel.mention}")
                except:
                    await ctx.send("Failed to send scheduled message")

            asyncio.create_task(send_scheduled_message())
            await ctx.send(
                f"Message scheduled to be sent to {channel.mention} at {schedule_time.strftime('%Y-%m-%d %H:%M')}")

        except ValueError:
            await ctx.send("Invalid date/time format! Please use YYYY-MM-DD HH:MM")
