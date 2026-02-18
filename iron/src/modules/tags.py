"""
modules/tags.py – RDanny-style server tag system.

Usage
─────
  !tag <name>           – retrieve a tag
  !tag create <name>    – create via modal
  !tag edit <name>      – edit via modal (owner / admin only)
  !tag delete <name>    – delete (owner / admin only)
  !tag info <name>      – owner, uses, creation date
  !tag raw <name>       – raw content (escaped markdown)
  !tag list             – paginated list of all tags
  !tag search <query>   – search tags by name
  !tag transfer <name> @user – transfer ownership
"""
import discord
from discord.ext import commands
from discord import ui
from datetime import datetime, timezone


# ─── Modals ───────────────────────────────────────────────────────────────────

class TagCreateModal(ui.Modal, title='Create Tag'):
    name    = ui.TextInput(label='Tag name', max_length=50, min_length=1)
    content = ui.TextInput(label='Content', style=discord.TextStyle.paragraph,
                           max_length=2000, min_length=1)

    def __init__(self, bot, guild_id, owner_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        name = str(self.name.value).strip().lower()
        content = str(self.content.value)

        try:
            async with self.bot.db.cursor() as cur:
                await cur.execute(
                    '''INSERT INTO tags (guild_id, name, content, owner_id)
                       VALUES (?, ?, ?, ?)''',
                    (self.guild_id, name, content, self.owner_id),
                )
            await self.bot.db.commit()
        except Exception:
            return await interaction.response.send_message(
                f'❌ A tag named `{name}` already exists in this server.', ephemeral=True
            )

        embed = discord.Embed(
            title='🏷️ Tag Created',
            description=f'Tag **{name}** is ready. Use `!tag {name}` to retrieve it.',
            color=0x57F287,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TagEditModal(ui.Modal, title='Edit Tag'):
    content = ui.TextInput(label='New content', style=discord.TextStyle.paragraph,
                           max_length=2000, min_length=1)

    def __init__(self, bot, tag_id, name):
        super().__init__()
        self.bot = bot
        self.tag_id = tag_id
        self.tag_name = name

    async def on_submit(self, interaction: discord.Interaction):
        new_content = str(self.content.value)
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'UPDATE tags SET content = ? WHERE id = ?',
                (new_content, self.tag_id),
            )
        await self.bot.db.commit()
        await interaction.response.send_message(
            embed=discord.Embed(description=f'✅ Tag **{self.tag_name}** updated.', color=0x57F287),
            ephemeral=True,
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def chunk_pages(items, title, color, per_page=15):
    pages = []
    for i in range(0, max(len(items), 1), per_page):
        chunk = items[i:i + per_page]
        embed = discord.Embed(title=title, color=color)
        embed.description = '\n'.join(chunk) if chunk else '*No tags yet.*'
        embed.set_footer(text=f'Page {i // per_page + 1} of {max(1, (len(items) - 1) // per_page + 1)} '
                              f'• Total: {len(items)}')
        pages.append(embed)
    return pages


class Paginator(ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.page = 0
        self._upd()

    def _upd(self):
        self.prev.disabled = self.page == 0
        self.next.disabled = self.page == len(self.embeds) - 1

    @ui.button(label='◀', style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: ui.Button):
        self.page -= 1; self._upd()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @ui.button(label='▶', style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        self.page += 1; self._upd()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Tags(commands.Cog):
    """Server tag system – store and retrieve reusable text snippets."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_tag(self, guild_id, name):
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT * FROM tags WHERE guild_id = ? AND name = ?',
                (guild_id, name.strip().lower()),
            )
            return await cur.fetchone()

    def _can_manage(self, ctx, tag_row) -> bool:
        """True if the user owns the tag or is an admin."""
        return (
            tag_row['owner_id'] == ctx.author.id
            or ctx.author.guild_permissions.administrator
        )

    # ── Main tag group ────────────────────────────────────────────────────────

    @commands.group(name='tag', invoke_without_command=True)
    async def tag(self, ctx, *, name: str):
        """Retrieve a tag by name."""
        row = await self._get_tag(ctx.guild.id, name)
        if not row:
            return await ctx.send(
                embed=discord.Embed(description=f'❌ No tag named `{name}` found.', color=discord.Color.red())
            )
        # Increment uses
        async with self.bot.db.cursor() as cur:
            await cur.execute('UPDATE tags SET uses = uses + 1 WHERE id = ?', (row['id'],))
        await self.bot.db.commit()
        await ctx.send(row['content'])

    @tag.command(name='create', aliases=['add', 'new'])
    async def tag_create(self, ctx):
        """Create a new tag via a form."""
        view = _OpenModalCreateView(self.bot, ctx.guild.id, ctx.author.id)
        await ctx.send('Fill in the form below to create a tag:', view=view, delete_after=60)

    @tag.command(name='edit', aliases=['update'])
    async def tag_edit(self, ctx, *, name: str):
        """Edit a tag you own (opens a form)."""
        row = await self._get_tag(ctx.guild.id, name)
        if not row:
            return await ctx.send(f'❌ No tag `{name}` found.')
        if not self._can_manage(ctx, row):
            return await ctx.send('❌ You do not own that tag.')
        modal = TagEditModal(self.bot, row['id'], row['name'])
        modal.content.default = row['content']
        view = _OpenModalEditView(modal)
        await ctx.send('Open the editor to update the tag content:', view=view, delete_after=60)

    @tag.command(name='delete', aliases=['remove', 'del'])
    async def tag_delete(self, ctx, *, name: str):
        """Delete a tag (owner or admin only)."""
        row = await self._get_tag(ctx.guild.id, name)
        if not row:
            return await ctx.send(f'❌ No tag `{name}` found.')
        if not self._can_manage(ctx, row):
            return await ctx.send('❌ You do not own that tag.')
        async with self.bot.db.cursor() as cur:
            await cur.execute('DELETE FROM tags WHERE id = ?', (row['id'],))
        await self.bot.db.commit()
        await ctx.send(
            embed=discord.Embed(description=f'🗑️ Tag **{name}** deleted.', color=discord.Color.red())
        )

    @tag.command(name='info')
    async def tag_info(self, ctx, *, name: str):
        """Show metadata for a tag."""
        row = await self._get_tag(ctx.guild.id, name)
        if not row:
            return await ctx.send(f'❌ No tag `{name}` found.')
        owner = ctx.guild.get_member(row['owner_id']) or await self.bot.fetch_user(row['owner_id'])
        embed = discord.Embed(title=f'🏷️ Tag — {row["name"]}', color=0x57F287)
        embed.add_field(name='Owner', value=owner.mention if owner else str(row['owner_id']), inline=True)
        embed.add_field(name='Uses', value=str(row['uses']), inline=True)
        embed.add_field(name='Created', value=row['created_at'][:10], inline=True)
        preview = row['content'][:200] + ('…' if len(row['content']) > 200 else '')
        embed.add_field(name='Content Preview', value=preview, inline=False)
        await ctx.send(embed=embed)

    @tag.command(name='raw')
    async def tag_raw(self, ctx, *, name: str):
        """Show the raw (escaped) content of a tag."""
        row = await self._get_tag(ctx.guild.id, name)
        if not row:
            return await ctx.send(f'❌ No tag `{name}` found.')
        escaped = discord.utils.escape_markdown(row['content'])
        await ctx.send(escaped[:2000])

    @tag.command(name='list', aliases=['all'])
    async def tag_list(self, ctx):
        """List all tags in this server."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT name, uses FROM tags WHERE guild_id = ? ORDER BY uses DESC',
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(
                embed=discord.Embed(description='No tags in this server yet.', color=0x57F287)
            )
        lines = [f'`{r["name"]}` — {r["uses"]} use(s)' for r in rows]
        embeds = chunk_pages(lines, f'🏷️ Tags — {ctx.guild.name}', 0x57F287)
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.send(embed=embeds[0], view=Paginator(embeds))

    @tag.command(name='search', aliases=['find'])
    async def tag_search(self, ctx, *, query: str):
        """Search tags by name."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT name, uses FROM tags WHERE guild_id = ? AND name LIKE ? ORDER BY uses DESC',
                (ctx.guild.id, f'%{query.lower()}%'),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(f'No tags matching `{query}` found.')
        lines = [f'`{r["name"]}` — {r["uses"]} use(s)' for r in rows]
        embeds = chunk_pages(lines, f'🔍 Tag Search: {query}', 0x57F287)
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.send(embed=embeds[0], view=Paginator(embeds))

    @tag.command(name='transfer')
    async def tag_transfer(self, ctx, name: str, new_owner: discord.Member):
        """Transfer tag ownership to another member."""
        row = await self._get_tag(ctx.guild.id, name)
        if not row:
            return await ctx.send(f'❌ No tag `{name}` found.')
        if not self._can_manage(ctx, row):
            return await ctx.send('❌ You do not own that tag.')
        async with self.bot.db.cursor() as cur:
            await cur.execute('UPDATE tags SET owner_id = ? WHERE id = ?', (new_owner.id, row['id']))
        await self.bot.db.commit()
        await ctx.send(
            embed=discord.Embed(
                description=f'✅ Tag **{name}** transferred to {new_owner.mention}.',
                color=0x57F287,
            )
        )

    @tag.command(name='mine')
    async def tag_mine(self, ctx):
        """List tags you own."""
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT name, uses FROM tags WHERE guild_id = ? AND owner_id = ? ORDER BY name',
                (ctx.guild.id, ctx.author.id),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send('You have no tags in this server.')
        lines = [f'`{r["name"]}` — {r["uses"]} use(s)' for r in rows]
        embeds = chunk_pages(lines, '🏷️ Your Tags', 0x57F287)
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await ctx.send(embed=embeds[0], view=Paginator(embeds))


# ─── Helper views ────────────────────────────────────────────────────────────

class _OpenModalCreateView(ui.View):
    def __init__(self, bot, guild_id, owner_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.owner_id = owner_id

    @ui.button(label='Create Tag', style=discord.ButtonStyle.primary, emoji='🏷️')
    async def open_modal(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message('Not your button.', ephemeral=True)
        await interaction.response.send_modal(
            TagCreateModal(self.bot, self.guild_id, self.owner_id)
        )


class _OpenModalEditView(ui.View):
    def __init__(self, modal: TagEditModal):
        super().__init__(timeout=60)
        self._modal = modal

    @ui.button(label='Edit Tag', style=discord.ButtonStyle.primary, emoji='✏️')
    async def open_modal(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(self._modal)


async def setup(bot):
    await bot.add_cog(Tags(bot))
