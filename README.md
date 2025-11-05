# Discord Bot Commands Documentation

A Discord bot with various utility, Minecraft server monitoring, gambling, and graveyard management features.

## Setup
- Clone the repository.
- Install the dependencies using `pip install -r requirements.txt`.
- Create a `.env` file in the root directory and add the following:
  - `DISCORD_TOKEN`: Your Discord bot token.
  - `DB`: Your database URL.
- Run the bot using `python bot.py`. or `python3 bot.py` if you're using Python 3. You can also host the bot on a hosting platform. 

## Utility Commands

- **help**: Displays a list of available commands and their categories.
  - Usage: `-help`

- **ping**: Tests bot responsiveness by showing latency.
  - Usage: `-ping`

- **greet**: Sends a friendly greeting message.
  - Usage: `-greet`

- **echo**: Repeats the provided message and deletes the original command.
  - Usage: `-echo <message>`

- **color**: Shows a color based on provided hex code.
  - Usage: `-color #HEXCODE`
  - Aliases: `colour`, `c`

- **whois**: Displays information about a user.
  - Usage: `-whois [user]`
  - Aliases: `userinfo`, `uinfo`, `who`, `user`, `w`

- **snipe**: Retrieves the last deleted message in the channel.
  - Usage: `-snipe`

## Minecraft Commands

- **status**: Checks the current status of the Minecraft server.
  - Usage: `-status`

## Economy Commands

- **balance**: Shows your current balance.
  - Usage: `-balance`

- **daily**: Claim your daily reward.
  - Usage: `-daily`

- **work**: Work and see if you get any money
  - UsageL `-work`

- **rob**: Rob a user.
  - Usage: `-rob <user>`
  - Example: `-rob @user`
  - Note: You can't rob yourself!
  - Note: You can't rob a user who doesn't exist in the database. Tell them to do `-balance` to add them to the database. 

- **give**: Give coins to another user.
  - Usage: `-give <user> <amount>`
  - Example: `-give @user 100`
  - Note: You can't give yourself coins!
  - Note: You can't give coins to a user who doesn't exist in the database. Tell them to do `-balance` to add them to the database. 

- **leaderboard**: Displays the gambling leaderboard.
  - Usage: `-leaderboard`

- **coinflip**: Bet on a coin flip.
  - Usage: `-coinflip <amount> <heads/tails>`

- **roll**: Roll dice for a chance to win. Threshold for winning is unknown (:p).
  - Usage: `-roll <amount>`

- **slots**: Play the slot machine.
  - Usage: `-slots <amount>`

## Graveyard Commands

- **death**: Records a player's death.
  - Usage: `-death <reason>`

- **revive**: Removes a death record.
  - Usage: `-revive <user>`

- **obit**: Shows death statistics for a user.
  - Usage: `-obit [user]`

## Levels Commands

- **rank**: Displays a user's level and experience.
  - Usage: `-rank [user]`

- **top**: Displays the top 10 users by level and experience.
  - Usage: `-top`
