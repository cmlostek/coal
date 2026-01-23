import os
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load it here, at the very top level of the file
load_dotenv()


async def setup(bot):
    # This check will tell you EXACTLY if the key is missing in your console
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        print("⚠️ WARNING: OPENWEATHER_API_KEY is still None. Check your .env file!")

    @bot.command(name="weather")
    async def weather(ctx, *, city: str):  # Use *, city to allow spaces in city names
        api_key = os.getenv("OPENWEATHER_API_KEY")

        # Guard clause to prevent the 'NoneType' crash
        if api_key is None:
            return await ctx.send("Bot configuration error: API Key missing.")

        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]
                    await ctx.send(f"The weather in {city.title()} is {temp}°C with {desc}.")
                else:
                    await ctx.send(f"Could not find weather for '{city}'.")

    # Add the command to the bot explicitly if setup() isn't auto-registering
    bot.add_command(weather)