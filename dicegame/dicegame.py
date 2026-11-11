import discord
from redbot.core import Config, commands, app_commands, bank
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_number
from typing import Optional, Dict, List
import logging
import random

log = logging.getLogger("red.dicegame")

NO_MENTIONS = discord.AllowedMentions.none()
LEADERBOARD_SIZE = 10
MAX_PLAYERS_SHOWN = 15


class DiceGameView(discord.ui.LayoutView):
    """Components v2 view for dice game betting"""

    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=30)
        self.cog = cog
        self.guild_id = guild_id
        self.ends_at = int(discord.utils.utcnow().timestamp()) + 30
        self.bets: Dict[int, Dict[str, int]] = {}  # user_id -> {animal: amount}
        self.users: Dict[int, discord.User] = {}  # user_id -> user object
        self.message: Optional[discord.Message] = None
        self.bot = cog.bot
        self.animals = ["fish", "shrimp", "crab", "cock", "dragon", "tiger"]
        self.animal_emojis = {
            "fish": "🐟",
            "shrimp": "🦐",
            "crab": "🦀",
            "cock": "🐓",
            "dragon": "🐉",
            "tiger": "🐅"
        }
        self.show_betting()

    def show_betting(self) -> None:
        """Rebuild the layout to show the current bets"""
        totals = {animal: 0 for animal in self.animals}
        for user_bets in self.bets.values():
            for animal, amount in user_bets.items():
                totals[animal] += amount

        # Two rows of three: emoji + total staked on it
        cells = [
            f"{self.animal_emojis[animal]} **{humanize_number(totals[animal])}**"
            if totals[animal]
            else f"{self.animal_emojis[animal]} —"
            for animal in self.animals
        ]
        board = " ".join(cells[:3]) + "\n" + " ".join(cells[3:])

        if self.bets:
            # One small line per player with their total stake, biggest first
            staked = sorted(
                ((user_id, sum(user_bets.values())) for user_id, user_bets in self.bets.items()),
                key=lambda entry: entry[1],
                reverse=True,
            )
            lines = [
                f"-# <@{user_id}> · {humanize_number(amount)}"
                for user_id, amount in staked[:MAX_PLAYERS_SHOWN]
            ]
            if len(staked) > MAX_PLAYERS_SHOWN:
                lines.append(f"-# +{len(staked) - MAX_PLAYERS_SHOWN} more")
            footer = "\n".join(lines)
        else:
            footer = "-# No bets yet · use /dicegame to join"

        self.clear_items()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## 🎲 Animal Dice\n-# Rolling <t:{self.ends_at}:R>"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(board),
                discord.ui.TextDisplay(footer),
                accent_colour=discord.Color.gold(),
            )
        )

    def show_results(self, winning_animals: List[str], payouts: Dict[int, int]) -> None:
        """Rebuild the layout to show the results"""
        # The roll itself is the headline: three big emojis
        dice = " ".join(self.animal_emojis[animal] for animal in winning_animals)
        names = []
        for animal in dict.fromkeys(winning_animals):
            count = winning_animals.count(animal)
            names.append(f"{animal.title()} ×{count}" if count > 1 else animal.title())
        header = f"# {dice}\n-# {' · '.join(names)}"

        if payouts:
            ranked = sorted(payouts.items(), key=lambda entry: entry[1], reverse=True)
            winners_text = "\n".join(
                f"<@{user_id}> **+{humanize_number(payout)}**" for user_id, payout in ranked
            )
            footer = f"-# {humanize_number(sum(payouts.values()))} credits paid out"
        elif self.bets:
            winners_text = "Nobody won this round."
            footer = None
        else:
            winners_text = "Nobody placed a bet."
            footer = None

        items = [
            discord.ui.TextDisplay(header),
            discord.ui.Separator(),
            discord.ui.TextDisplay(winners_text),
        ]
        if footer:
            items.append(discord.ui.TextDisplay(footer))

        self.clear_items()
        self.add_item(
            discord.ui.Container(
                *items,
                accent_colour=discord.Color.green() if payouts else discord.Color.red(),
            )
        )

    async def on_timeout(self):
        """Handle when betting time expires"""
        if not self.message:
            return

        try:
            # Roll dice (3 dice, each can land on any animal)
            winning_animals = [random.choice(self.animals) for _ in range(3)]

            # Calculate payouts and per-user won/lost totals for the leaderboard
            payouts = {}
            stats: Dict[int, Dict[str, int]] = {}  # user_id -> {"won": x, "lost": y}
            for user_id, user_bets in self.bets.items():
                total_payout = 0
                won = 0
                lost = 0
                for animal, bet_amount in user_bets.items():
                    wins = winning_animals.count(animal)
                    if wins > 0:
                        # Payout is bet_amount * number_of_wins * 2
                        payout = bet_amount * wins * 2
                        total_payout += payout
                        won += payout - bet_amount
                    else:
                        lost += bet_amount

                if total_payout > 0:
                    payouts[user_id] = total_payout
                stats[user_id] = {"won": won, "lost": lost}

            # Award payouts
            for user_id, payout in payouts.items():
                try:
                    user = self.users.get(user_id)
                    if user:
                        await bank.deposit_credits(user, payout)
                        log.debug(f"Awarded {payout} credits to user {user_id}")
                    else:
                        log.error(f"Could not find user {user_id} to award payout")
                except Exception as e:
                    log.error(f"Error awarding payout to user {user_id}: {e}")

            # Record leaderboard stats
            for user_id, result in stats.items():
                try:
                    await self.cog.record_result(self.guild_id, user_id, result["won"], result["lost"])
                except Exception as e:
                    log.error(f"Error recording stats for user {user_id}: {e}")

            # Update message with results
            self.show_results(winning_animals, payouts)
            await self.message.edit(view=self, allowed_mentions=NO_MENTIONS)

        except Exception as e:
            log.error(f"Error in dice game timeout: {e}")
        finally:
            # Clean up from active games
            if hasattr(self, 'cleanup'):
                self.cleanup()

        self.stop()


class LeaderboardTabButton(discord.ui.Button):
    """Button that switches the leaderboard to a given tab"""

    def __init__(self, layout: "LeaderboardView", tab: str, disabled: bool):
        label, emoji, _ = LeaderboardView.TABS[tab]
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.primary if layout.tab == tab else discord.ButtonStyle.secondary,
            disabled=disabled,
        )
        self.layout = layout
        self.tab = tab

    async def callback(self, interaction: discord.Interaction):
        self.layout.tab = self.tab
        self.layout.build()
        await interaction.response.edit_message(view=self.layout, allowed_mentions=NO_MENTIONS)


class LeaderboardView(discord.ui.LayoutView):
    """Components v2 leaderboard with Won / Lost tabs"""

    # tab -> (button label, emoji, accent colour)
    TABS = {
        "won": ("Most Won", "🏆", discord.Color.green()),
        "lost": ("Most Lost", "💸", discord.Color.red()),
    }
    MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

    def __init__(self, stats: Dict[int, Dict[str, int]], tab: str = "won"):
        super().__init__(timeout=120)
        self.stats = stats  # member_id -> {"won": x, "lost": y}
        self.tab = tab
        self.message: Optional[discord.Message] = None
        self.build()

    def build(self, disabled: bool = False) -> None:
        label, emoji, colour = self.TABS[self.tab]

        ranked = sorted(
            ((member_id, data.get(self.tab, 0)) for member_id, data in self.stats.items()),
            key=lambda entry: entry[1],
            reverse=True,
        )
        ranked = [entry for entry in ranked if entry[1] > 0][:LEADERBOARD_SIZE]

        if ranked:
            lines = []
            for position, (member_id, amount) in enumerate(ranked, start=1):
                rank = self.MEDALS.get(position, f"`#{position}`")
                lines.append(f"{rank} <@{member_id}> — **{humanize_number(amount)}** credits")
            body = "\n".join(lines)
        else:
            body = "Nobody is on this board yet. Play `/dicegame` to get on it!"

        row = discord.ui.ActionRow()
        for tab in self.TABS:
            row.add_item(LeaderboardTabButton(self, tab, disabled))

        self.clear_items()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## 🎲 Dice Game Leaderboard\n### {emoji} {label}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(body),
                discord.ui.Separator(),
                row,
                accent_colour=colour,
            )
        )

    async def on_timeout(self):
        if not self.message:
            return
        self.build(disabled=True)
        try:
            await self.message.edit(view=self, allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass


class DiceGame(commands.Cog):
    """
    Animal dice betting game with 30-second betting rounds
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.active_games: Dict[int, DiceGameView] = {}  # channel_id -> game_view
        self.config = Config.get_conf(self, identifier=0xD1CE6A3E, force_registration=True)
        self.config.register_member(won=0, lost=0)

    async def cog_load(self):
        """Called when the cog is loaded"""
        log.info("DiceGame cog loaded")

    async def cog_unload(self):
        """Called when the cog is unloaded"""
        # Cancel all active games
        for game in self.active_games.values():
            game.stop()
        log.info("DiceGame cog unloaded")

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Delete a user's leaderboard totals"""
        all_members = await self.config.all_members()
        for guild_id, members in all_members.items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()

    async def record_result(self, guild_id: int, user_id: int, won: int, lost: int) -> None:
        """Add a round's winnings/losses to a member's leaderboard totals"""
        async with self.config.member_from_ids(guild_id, user_id).all() as data:
            data["won"] += won
            data["lost"] += lost

    @app_commands.command(name="diceleaderboard", description="Show who has won and lost the most in the dice game")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        """Show the dice game leaderboard"""
        stats = await self.config.all_members(interaction.guild)
        view = LeaderboardView(stats)
        await interaction.response.send_message(view=view, allowed_mentions=NO_MENTIONS)
        view.message = await interaction.original_response()

    @app_commands.command(name="dicegame", description="Place a bet in the dice game (starts game if needed)")
    @app_commands.describe(
        amount="Amount of credits to bet",
        animals="Animals to bet on (space-separated): fish, shrimp, crab, cock, dragon, tiger"
    )
    @app_commands.guild_only()
    async def place_bet(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 1000000],
        animals: str
    ):
        """Place a bet in the dice game (starts game if needed)"""
        channel_id = interaction.channel.id

        # Check if there's an active game in this channel, if not create one
        game_started_now = False
        if channel_id not in self.active_games:
            # Create new game
            game_view = DiceGameView(self, interaction.guild.id)

            await interaction.response.send_message(view=game_view)

            # Store game and message reference
            game_view.message = await interaction.original_response()
            self.active_games[channel_id] = game_view
            game_started_now = True

            # Store cleanup function for later use
            game_view.cleanup = lambda: self.active_games.pop(channel_id, None)

        game_view = self.active_games[channel_id]
        user_id = interaction.user.id

        # Parse animals (split by spaces instead of commas)
        animal_list = [animal.strip().lower() for animal in animals.split()]
        valid_animals = []

        for animal in animal_list:
            if animal in game_view.animals:
                valid_animals.append(animal)
            else:
                error_msg = f"Invalid animal: {animal}. Valid animals are: {', '.join(game_view.animals)}"
                if game_started_now:
                    await interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                return

        if not valid_animals:
            error_msg = "No valid animals specified!"
            if game_started_now:
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)
            return

        # Check if user has enough credits
        try:
            user_balance = await bank.get_balance(interaction.user)
            total_bet = amount * len(valid_animals)

            if user_balance < total_bet:
                error_msg = f"Insufficient credits! You have {user_balance} credits but need {total_bet}."
                if game_started_now:
                    await interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                return

            # Withdraw the bet amount
            await bank.withdraw_credits(interaction.user, total_bet)

        except Exception as e:
            error_msg = f"Error accessing your balance: {e}"
            if game_started_now:
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)
            return

        # Add bets and store user object
        if user_id not in game_view.bets:
            game_view.bets[user_id] = {}

        game_view.users[user_id] = interaction.user

        for animal in valid_animals:
            if animal in game_view.bets[user_id]:
                game_view.bets[user_id][animal] += amount
            else:
                game_view.bets[user_id][animal] = amount

        # Update the game message
        try:
            game_view.show_betting()
            await game_view.message.edit(view=game_view, allowed_mentions=NO_MENTIONS)

            bet_text = f"Bet placed: {amount} credits each on {', '.join([animal.title() for animal in valid_animals])}"
            if game_started_now:
                await interaction.followup.send(bet_text, ephemeral=True)
            else:
                await interaction.response.send_message(bet_text, ephemeral=True)

        except Exception as e:
            log.error(f"Error updating game message: {e}")
            if game_started_now:
                await interaction.followup.send(
                    "Bet placed successfully!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Bet placed successfully!",
                    ephemeral=True
                )


async def setup(bot: Red):
    """Load the cog"""
    cog = DiceGame(bot)
    await bot.add_cog(cog)
