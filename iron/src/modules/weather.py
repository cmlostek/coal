import aiohttp
import discord
from discord.ext import commands
import dotenv


def setup(bot):
    @bot.command(name="weather", description="Get the current weather for a specified city.")
    async def weather(ctx, city: str):
        api_key = dotenv.get_key('.env', 'OPENWEATHER_API_KEY')
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": 'imperial'
        }

        # Using aiohttp for non-blocking requests
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    main = data["main"]
                    weather_desc = data["weather"][0]["description"]

                    weather_info = (
                        f"**Weather in {city.title()}**\n"
                        f"Temperature: {main['temp']}°C\n"
                        f"Humidity: {main['humidity']}%\n"
                        f"Description: {weather_desc.capitalize()}"
                    )
                else:
                    weather_info = f"City '{city}' not found or API error."

        await ctx.send(weather_info)