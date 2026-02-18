"""Hastebin module - upload text to a pastebin-style service"""

import aiohttp
import discord

HASTE_URL = 'https://haste.zneix.eu'


def setup(bot):
    """Setup function to register commands with the bot"""

    @bot.command(name='haste', aliases=['hastebin', 'paste', 'pb'])
    async def haste(ctx, *, content: str = None):
        """Upload text or a code block to hastebin.
        Usage: -haste <text>  or  -haste ```lang\\ncode```"""

        if content:
            # Strip triple-backtick code blocks
            if content.startswith('```') and content.endswith('```'):
                lines = content.split('\n')
                # Remove opening ```lang line and closing ``` line
                content = '\n'.join(lines[1:-1]) if len(lines) > 2 else content[3:-3]
        elif ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.size > 1_000_000:
                await ctx.send('Attachment is too large (max 1 MB).')
                return
            try:
                content = (await attachment.read()).decode('utf-8')
            except UnicodeDecodeError:
                await ctx.send('Could not read attachment as text.')
                return
        else:
            await ctx.send(
                'Provide text to upload. Usage: `-haste <text>` or `-haste \\`\\`\\`code\\`\\`\\``'
            )
            return

        if not content.strip():
            await ctx.send('Cannot upload empty content.')
            return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f'{HASTE_URL}/documents',
                    data=content.encode('utf-8'),
                    headers={'Content-Type': 'text/plain; charset=utf-8'},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        await ctx.send(f'Upload failed (HTTP {resp.status}). Try again later.')
                        return
                    data = await resp.json()
                    key = data.get('key')
                    if not key:
                        await ctx.send('Unexpected response from hastebin.')
                        return

                    url = f'{HASTE_URL}/{key}'
                    embed = discord.Embed(
                        title='Uploaded to Hastebin',
                        description=url,
                        color=discord.Color.green()
                    )
                    embed.set_footer(text=f'Uploaded by {ctx.author.display_name}')
                    await ctx.send(embed=embed)
            except aiohttp.ClientError as e:
                await ctx.send(f'Could not connect to hastebin: {e}')
            except TimeoutError:
                await ctx.send('Hastebin timed out. Try again later.')
