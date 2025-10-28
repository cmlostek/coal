# Imports

import discord
import os
import sqlite3 as sql
from dotenv import load_dotenv
from discord.ext.commands import Bot

# Bot Intents

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

# Bot Params

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
MINECRAFT_SERVER_IP = os.getenv('MINECRAFT_SERVER_IP')
MINECRAFT_SERVER_PORT = os.getenv('MINECRAFT_SERVER_PORT')

# Bot Instance

bot = Bot(command_prefix='-', intents=intents, help_command=None)


# On Ready Event

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

    # Initialize the database connection and ensure tables exist
    bot.db = sql.connect('coal_db2.sqlite3', check_same_thread=False)

    # Ensure the death_log table exists
    c = bot.db.cursor()
    c.execute('''
              CREATE TABLE IF NOT EXISTS death_log
              (
                  log_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  cntr    INTEGER,
                  reason  TEXT
              )
              ''')

    # Ensure the balances table exists for gambling
    c.execute('''
              CREATE TABLE IF NOT EXISTS balances
              (
                  user_id INTEGER PRIMARY KEY,
                  balance INTEGER DEFAULT 1000
              )
              ''')
    bot.db.commit()

    print(f'{bot.user} has connected to Discord!')
    print(f'Monitoring Minecraft server: {MINECRAFT_SERVER_IP}')

    # Load modules
    modules = ['utils', 'grave', 'minecraft', 'gambling']
    for module in modules:
        try:
            # Import the module dynamically
            mod = __import__(f'modules.{module}', fromlist=['setup'])
            mod.setup(bot)
            print(f'Loaded module: {module}')
        except Exception as e:
            print(f'Failed to load module {module}: {e}')

# Run the bot

if __name__ == '__main__':
    if not TOKEN or not MINECRAFT_SERVER_IP:
        print("Error: Your bot token or Minecraft server address are not set. Please check your environment variables.")
    else:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("Error: Improper token has been passed. Please check your DISCORD_TOKEN.")
        except KeyboardInterrupt:
            print("Bot stopped by user.")
        except Exception as e:
            print(f"An unexpected error occurred during bot execution: {e}")