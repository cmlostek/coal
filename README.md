# Discord Bot Commands Documentation

A Discord bot with various utility, Minecraft server monitoring, gambling, and graveyard management features.

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

