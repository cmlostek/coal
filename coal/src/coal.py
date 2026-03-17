# Imports

import discord
import os
import psycopg2
from dotenv import load_dotenv
from discord.ext.commands import Bot
from mcstatus import JavaServer

# Bot Intents

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent

# Bot Params

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
MINECRAFT_SERVER_IP = os.getenv('MINECRAFT_SERVER_IP')
MINECRAFT_SERVER_PORT = os.getenv('MINECRAFT_SERVER_PORT')
DATABASE_URL = os.getenv('DATABASE_URL')

# Bot Instance

bot = Bot(command_prefix='-' or '!' or '?', intents=intents, help_command=None)


# On Ready Event

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Monitoring Minecraft server: {MINECRAFT_SERVER_IP}')

    # Load modules
    modules = ['utils', 'grave', 'minecraft', 'economy', 'levels', 'tts', 'reminders', 'stats', 'hastebin']
    loaded = 0
    for module in modules:
        try:
            mod = __import__(f'modules.{module}', fromlist=['setup'])
            mod.setup(bot)
            print(f'Loaded module: {module}')
            loaded += 1
        except Exception as e:
            print(f'Failed to load module {module}: {e}')
    if loaded == 0:
        print('No modules loaded.')
    elif loaded == len(modules):
        print('All modules loaded.')
    else:
        print(f'Loaded {loaded} out of {len(modules)} modules.')

    print(f'All databases loaded. All Modules loaded. Ready to go!')

# Run the bot

if __name__ == '__main__':
    if not TOKEN or not MINECRAFT_SERVER_IP or not DATABASE_URL:
        print("Error: DISCORD_TOKEN, MINECRAFT_SERVER_IP, or DATABASE_URL is not set. Please check your environment variables.")
    else:
        try:
            # Connect to DB before starting the event loop so the blocking
            # network call does not freeze the Discord heartbeat.
            print('Connecting to Supabase...')
            bot.db = psycopg2.connect(DATABASE_URL, connect_timeout=10)
            print('Connected to Supabase database.')

            c = bot.db.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS death_log (
                    log_id  SERIAL PRIMARY KEY,
                    id      TEXT,
                    cntr    INTEGER,
                    reason  TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS balances (
                    user_id    BIGINT PRIMARY KEY,
                    balance    INTEGER DEFAULT 1000,
                    last_daily TEXT DEFAULT NULL,
                    last_work  TEXT DEFAULT NULL
                )
            ''')
            bot.db.commit()
            c.close()
            print('Tables ensured.')

            bot.run(TOKEN)
        except psycopg2.OperationalError as e:
            print(f"Error: Could not connect to database: {e}")
        except discord.errors.LoginFailure:
            print("Error: Improper token has been passed. Please check your DISCORD_TOKEN.")
        except KeyboardInterrupt:
            print("Bot stopped by user.")
        except Exception as e:
            print(f"An unexpected error occurred during bot execution: {e}")

