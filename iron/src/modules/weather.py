import requests
import discord

def setup(bot):
    @bot.command(name="weather", description="Get the current weather for a specified city.")
    async def weather(ctx, city: str):
        api_key = "b04cbc71f6c27e64390a3a485a2d347a"  # Replace with your OpenWeatherMap API key
        base_url = "http://api.openweathermap.org/data/2.5/weather?"
        complete_url = f"{base_url}q={city}&appid={api_key}&units=metric"

        response = requests.get(complete_url)
        data = response.json()

        if data["cod"] != "404":
            main = data["main"]
            weather_desc = data["weather"][0]["description"]
            temp = main["temp"]
            humidity = main["humidity"]
            wind_speed = data["wind"]["speed"]

            weather_info = (
                f"**Weather in {city.title()}**\n"
                f"Temperature: {temp}°C\n"
                f"Humidity: {humidity}%\n"
                f"Wind Speed: {wind_speed} m/s\n"
                f"Description: {weather_desc.capitalize()}"
            )
        else:
            weather_info = f"City '{city}' not found."

        await ctx.send(weather_info)