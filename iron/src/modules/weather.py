"""
modules/weather.py – Enhanced weather with current conditions, daily forecast,
                     and 5-day weekly outlook.

Commands
────────
  !weather [location]   – current weather (uses guild default if no location given)
  !forecast [location]  – 5-day forecast
"""
import discord
from discord.ext import commands
import aiohttp
import os
import logging
from datetime import datetime

log = logging.getLogger(__name__)

BASE = 'https://api.openweathermap.org/data/2.5'

CONDITION_EMOJI = {
    'clear':          '☀️',
    'clouds':         '☁️',
    'rain':           '🌧️',
    'drizzle':        '🌦️',
    'thunderstorm':   '⛈️',
    'snow':           '❄️',
    'mist':           '🌫️',
    'smoke':          '🌫️',
    'haze':           '🌫️',
    'dust':           '💨',
    'fog':            '🌫️',
    'sand':           '💨',
    'ash':            '🌋',
    'squall':         '💨',
    'tornado':        '🌪️',
}


def _weather_emoji(condition: str) -> str:
    return CONDITION_EMOJI.get(condition.lower(), '🌡️')


def _c_to_f(c: float) -> float:
    return round(c * 9 / 5 + 32, 1)


def _wind_dir(deg: int) -> str:
    dirs = ['N','NE','E','SE','S','SW','W','NW']
    return dirs[round(deg / 45) % 8]


async def _fetch_current(session, location: str, api_key: str) -> dict | None:
    params = {'q': location, 'appid': api_key, 'units': 'imperial'}
    async with session.get(f'{BASE}/weather', params=params) as r:
        if r.status != 200:
            return None
        return await r.json()


async def _fetch_forecast(session, location: str, api_key: str) -> dict | None:
    params = {'q': location, 'appid': api_key, 'units': 'imperial', 'cnt': 40}
    async with session.get(f'{BASE}/forecast', params=params) as r:
        if r.status != 200:
            return None
        return await r.json()


def _build_current_embed(data: dict) -> discord.Embed:
    city     = data['name']
    country  = data['sys']['country']
    cond     = data['weather'][0]['main']
    desc     = data['weather'][0]['description'].title()
    temp_f   = data['main']['temp']
    temp_c   = _c_to_f.__doc__ and round((temp_f - 32) * 5 / 9, 1)
    feels_f  = data['main']['feels_like']
    humidity = data['main']['humidity']
    wind_spd = data['wind']['speed']
    wind_deg = data['wind'].get('deg', 0)
    vis      = data.get('visibility', 0)
    emoji    = _weather_emoji(cond)

    temp_c_val = round((temp_f - 32) * 5 / 9, 1)

    embed = discord.Embed(
        title=f'{emoji} {city}, {country}',
        description=f'**{desc}**',
        color=_condition_color(cond),
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name='🌡️ Temperature', value=f'{temp_f}°F / {temp_c_val}°C', inline=True)
    embed.add_field(name='🤔 Feels Like', value=f'{feels_f}°F / {round((feels_f-32)*5/9,1)}°C', inline=True)
    embed.add_field(name='💧 Humidity', value=f'{humidity}%', inline=True)
    embed.add_field(name='💨 Wind', value=f'{wind_spd} mph {_wind_dir(wind_deg)}', inline=True)
    embed.add_field(name='👁️ Visibility', value=f'{vis // 1000 if vis else "?"} km', inline=True)
    if 'rain' in data:
        embed.add_field(name='🌧️ Rain (1h)', value=f'{data["rain"].get("1h", 0)} mm', inline=True)

    sunrise = datetime.utcfromtimestamp(data['sys']['sunrise']).strftime('%H:%M UTC')
    sunset  = datetime.utcfromtimestamp(data['sys']['sunset']).strftime('%H:%M UTC')
    embed.add_field(name='🌅 Sunrise / Sunset', value=f'{sunrise} / {sunset}', inline=False)
    embed.set_footer(text='OpenWeatherMap • !forecast for 5-day outlook')
    return embed


def _condition_color(cond: str) -> discord.Color:
    mapping = {
        'clear': discord.Color.yellow(),
        'clouds': discord.Color.light_grey(),
        'rain': discord.Color.blue(),
        'drizzle': discord.Color.blue(),
        'thunderstorm': discord.Color.dark_grey(),
        'snow': 0xADD8E6,
    }
    return mapping.get(cond.lower(), discord.Color.blurple())


def _build_forecast_embed(data: dict, location: str) -> discord.Embed:
    """Build a 5-day daily summary embed from 3-hr forecast data."""
    # Group by date
    days: dict[str, list] = {}
    for item in data['list']:
        dt = datetime.utcfromtimestamp(item['dt'])
        date_key = dt.strftime('%Y-%m-%d')
        days.setdefault(date_key, []).append(item)

    embed = discord.Embed(
        title=f'📅 5-Day Forecast — {location.title()}',
        color=0x87CEEB,
        timestamp=datetime.utcnow(),
    )

    for date_key in list(days.keys())[:5]:
        items = days[date_key]
        temps = [i['main']['temp'] for i in items]
        conds = [i['weather'][0]['main'] for i in items]
        pop   = max(i.get('pop', 0) for i in items) * 100

        high = max(temps)
        low  = min(temps)
        most_common = max(set(conds), key=conds.count)
        emoji = _weather_emoji(most_common)

        dt = datetime.strptime(date_key, '%Y-%m-%d')
        day_label = dt.strftime('%a %b %d')

        embed.add_field(
            name=f'{emoji} {day_label}',
            value=f'⬆️ {high}°F  ⬇️ {low}°F\n🌧️ Precip: {int(pop)}%',
            inline=True,
        )

    embed.set_footer(text='OpenWeatherMap')
    return embed


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Weather(commands.Cog):
    """Enhanced weather with current conditions and 5-day forecast."""

    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv('OPENWEATHER_API_KEY')
        if not self.api_key:
            log.warning('OPENWEATHER_API_KEY not set – weather commands will not work.')

    async def _resolve_location(self, ctx, location: str | None) -> str | None:
        """Use provided location, or fall back to guild config."""
        if location:
            return location
        async with self.bot.db.cursor() as cur:
            await cur.execute(
                'SELECT weather_location FROM guild_config WHERE guild_id = ?',
                (ctx.guild.id,),
            )
            row = await cur.fetchone()
        if row and row['weather_location']:
            return row['weather_location']
        return None

    @commands.command(name='weather', aliases=['w'])
    async def weather(self, ctx, *, location: str = None):
        """
        Show current weather.

        Usage: `!weather [city]`
        Defaults to the location set in `!setup`.
        """
        if not self.api_key:
            return await ctx.send('❌ Weather API key not configured.')

        loc = await self._resolve_location(ctx, location)
        if not loc:
            return await ctx.send('❌ No location set. Provide one or run `!setup location <city>`.')

        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                data = await _fetch_current(session, loc, self.api_key)

        if not data:
            return await ctx.send(f'❌ Could not find weather for `{loc}`.')

        await ctx.send(embed=_build_current_embed(data))

    @commands.command(name='forecast', aliases=['fc'])
    async def forecast(self, ctx, *, location: str = None):
        """
        Show a 5-day weather forecast.

        Usage: `!forecast [city]`
        Defaults to the location set in `!setup`.
        """
        if not self.api_key:
            return await ctx.send('❌ Weather API key not configured.')

        loc = await self._resolve_location(ctx, location)
        if not loc:
            return await ctx.send('❌ No location set. Provide one or run `!setup location <city>`.')

        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                data = await _fetch_forecast(session, loc, self.api_key)

        if not data:
            return await ctx.send(f'❌ Could not find forecast for `{loc}`.')

        await ctx.send(embed=_build_forecast_embed(data, loc))


async def setup(bot):
    await bot.add_cog(Weather(bot))
