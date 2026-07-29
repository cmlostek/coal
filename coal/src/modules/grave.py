"""Graveyard / Death log commands module.

Stateless: the graveyard channel itself is the source of truth. Every death is
a bot message of the form ``💀 **Death #N** … <@id> … Reason: …``. The death
count and obituaries are parsed from channel history on demand, so no database
is used here. (The legacy ``death_log`` table is left in place but unused.)
"""

import io
import re

import discord


# Channel that holds the death messages (the graveyard).
DEATH_CHANNEL_ID = 1422284082955685888

# Parsing helpers for the bot's own death messages.
_DEATH_RE = re.compile(r"Death #(\d+)")
_MENTION_RE = re.compile(r"<@!?(\d+)>")
_REASON_RE = re.compile(r"Reason:\s*(.+)", re.DOTALL)


def setup(bot):
    """Setup function to register commands with the bot"""

    def _channel():
        return bot.get_channel(DEATH_CHANNEL_ID)

    def _parse_death(message):
        """Return (num, user_id, reason) for a bot death message, else None.

        ``user_id`` is the digit string of the mentioned user, ``'0'`` for an
        anonymous death, or ``None`` if attribution can't be determined.
        Revive (🕊️) and other messages have no ``Death #N`` and return None.
        """
        content = message.content or ""
        m = _DEATH_RE.search(content)
        if not m:
            return None
        num = int(m.group(1))
        mention = _MENTION_RE.search(content)
        if mention:
            user_id = mention.group(1)
        elif "Anonymous" in content:
            user_id = "0"
        else:
            user_id = None
        rm = _REASON_RE.search(content)
        reason = rm.group(1).strip() if rm else None
        return num, user_id, reason

    async def _iter_deaths(channel, limit=None):
        """Yield parsed (num, user_id, reason) for bot death messages, newest first."""
        async for message in channel.history(limit=limit, oldest_first=False):
            if bot.user is None or message.author.id != bot.user.id:
                continue
            parsed = _parse_death(message)
            if parsed is not None:
                yield parsed

    async def _next_death_number(channel):
        """Highest existing death number + 1 (1 if there are none)."""
        # Newest-first: the first death message we hit holds the max number, so
        # we can stop immediately. Bounded so an empty graveyard with lots of
        # chatter doesn't page through the entire channel.
        async for num, _uid, _reason in _iter_deaths(channel, limit=500):
            return num + 1
        return 1

    def _parse_target(ctx, args):
        """Resolve the target id from args: '0', digits, mention, or invoker."""
        if not args:
            return str(ctx.author.id)
        first = args[0]
        if first == "0" or first.startswith("<@") or first.isdigit():
            digits = "".join(ch for ch in first if ch.isdigit())
            return digits if digits else ("0" if first == "0" else str(ctx.author.id))
        return str(ctx.author.id)

    @bot.command(name="death", aliases=["die", "d"])
    async def death(ctx, *args):
        """
        Logs a death adding a poor soul to the graveyard.
        args: Optional first arg is the id (mention or digits). If omitted, uses the command invoker. Any remaining args are joined as the reason.
        """
        death_channel = _channel()
        if not death_channel:
            await ctx.send(f"Error: Death channel with ID {DEATH_CHANNEL_ID} not found.")
            return

        # Determine target user id and reason.
        if not args:
            final_user_id = str(ctx.author.id)
            reason = None
        else:
            first = args[0]
            if first == "0" or first.startswith("<@") or first.isdigit():
                final_user_id = _parse_target(ctx, args)
                reason = " ".join(word.strip(".,!%;:'\"") for word in args[1:]) if len(args) > 1 else None
            else:
                final_user_id = str(ctx.author.id)
                reason = " ".join(word.strip(".,!%;:'\"") for word in args)

        # Next sequential number is derived from the channel, not a database.
        try:
            num = await _next_death_number(death_channel)
        except discord.Forbidden:
            await ctx.send("Error: I need permission to read the graveyard's message history.")
            return

        # Notify channel / user.
        if final_user_id == "0":
            await death_channel.send(f'💀 **Death #{num}** - Anonymous\nReason: {reason or "Unknown cause."}')
            await ctx.send("A new soul has entered the graveyard anonymously.")
            print("Death logged and posted.")
        else:
            mention = f"<@{final_user_id}>"
            if reason:
                await death_channel.send(
                    f"💀 **Death #{num}** - You have met a terrible fate, {mention}.\nReason: {reason}")
            else:
                await death_channel.send(f"💀 **Death #{num}** - You have met a terrible fate, {mention}.")
            await ctx.send("A new soul has entered the graveyard.")

    @bot.command()
    async def kill(ctx, *args):
        """
        Kills the specified user. Adding a death to their log.
        """
        await ctx.send(f"{ctx.author.mention} has killed {args[0]} for reason {args[1]}.")
        await ctx.invoke(death, args[0], args[1])

    @bot.command(name="revive", aliases=["resurrect", "undeath", "r"])
    async def revive(ctx, *args):
        """
        Revives a user by announcing their return in the graveyard.
        :user_id The ID of the user to revive (mention or digits).
        """
        death_channel = _channel()
        if not death_channel:
            await ctx.send(f"Error: Death channel with ID {DEATH_CHANNEL_ID} not found.")
            return

        if not args:
            user_id_str = str(ctx.author.id)
            reason = None
        else:
            first = args[0]
            if first == "0" or first.startswith("<@") or first.isdigit():
                user_id_str = first
                reason = " ".join(args[1:]) if len(args) > 1 else None
            else:
                user_id_str = str(ctx.author.id)
                reason = " ".join(args)

        digits = "".join(ch for ch in user_id_str if ch.isdigit())
        if digits:
            target_id_for_query = digits
        else:
            await ctx.send("Invalid user ID provided for revival.")
            return

        if target_id_for_query == "0":
            await ctx.send("Cannot revive anonymous deaths (ID 0).")
            return

        await death_channel.send(
            f"🕊️ A soul has been revived: <@{target_id_for_query}>. \n  They found the reason to live because of {str(reason)}" or "No reason provided.")

    @bot.command(name="obit", aliases=["obituary", "death_log", "deaths", "log", "l"])
    async def obit(ctx, *args):
        """
        Retrieves and sends the obituary for a specific user by parsing the graveyard.
        :args The ID of the user whose obituary is to be retrieved. If None, retrieves the log for the command invoker.
        Use -1 to get the entire log as a file.
        Use 0 to get logs for generic/anonymous deaths.
        """
        death_channel = _channel()
        if not death_channel:
            await ctx.send(f"Error: Death channel with ID {DEATH_CHANNEL_ID} not found.")
            return

        # Determine the target user_id for query.
        if not args:
            user_id = str(ctx.author.id)
        else:
            user_id = args[0]

        # Check the literal special tokens before stripping digits, otherwise
        # '-1' would collapse to '1' and lose its "full log" meaning.
        if user_id in ("-1", "0"):
            target_id_for_query = user_id
        else:
            digits = "".join(ch for ch in user_id if ch.isdigit())
            target_id_for_query = digits if digits else user_id

        try:
            # Special case: Entire Log (-1)
            if target_id_for_query == "-1":
                entries = [(num, uid, reason) async for (num, uid, reason) in _iter_deaths(death_channel)]
                if not entries:
                    await ctx.send("No death logs found. (The graveyard is empty.)")
                    return
                entries.sort(key=lambda e: e[0])  # by death number, ascending
                lines = [f'[{num}] User ID: {uid or "Unknown"} | Reason: {reason or "No reason"}'
                         for num, uid, reason in entries]
                fp = io.BytesIO("\n".join(lines).encode("utf-8"))
                await ctx.send("Here is the full death log.", file=discord.File(fp, filename="death_log.txt"))
                return

            # Special case: Anonymous Logs (0)
            if target_id_for_query == "0":
                rows = [(num, reason) async for (num, uid, reason) in _iter_deaths(death_channel) if uid == "0"]
                if not rows:
                    await ctx.send("No anonymous death logs found.")
                    return
                rows.sort(key=lambda r: r[0])
                lines = [f'**{num}** - {reason or "No reason"}' for num, reason in rows]
                msg = discord.Embed(
                    title="💀 Anonymous Death Logs (ID 0)",
                    description="\n".join(lines),
                    color=discord.Color.dark_red(),
                )
                msg.set_footer(text=f"Total Anonymous Deaths: {len(rows)}")
                await ctx.send(embed=msg)
                return

            # Regular User Lookup
            rows = [(num, reason) async for (num, uid, reason) in _iter_deaths(death_channel)
                    if uid == target_id_for_query]
        except discord.Forbidden:
            await ctx.send("Error: I need permission to read the graveyard's message history.")
            return

        if rows:
            user_logs_count = len(rows)
            rows.sort(key=lambda r: r[0])  # oldest first for display
            recent_rows = rows[-10:]  # most recent 10 by number
            desc_lines = [f'**{num}** - {reason or "Rest In Peace :("}' for num, reason in recent_rows]
            # Resolve a nice username for the embed title.
            title_user = target_id_for_query
            try:
                fetched = await bot.fetch_user(int(target_id_for_query))
                title_user = str(fetched)
            except Exception:
                pass

            msg = discord.Embed(
                title=f"💀 Obituary for {title_user}",
                description="\n".join(desc_lines),
                color=discord.Color.red(),
            )
            msg.set_footer(
                text=f"Total deaths: {user_logs_count}.\n Showing last {len(recent_rows)} entries. | May they rest in peace.")
            await ctx.send(embed=msg)

            if user_logs_count >= 100:
                await ctx.send("Holy smokes, that is a lot of deaths... you might want to stop dying! 🤯")
        else:
            await ctx.send("Hmmmm, they don't seem dead yet... keep trying! 😉")
