import discord
from redbot.core import commands, app_commands, bank
from redbot.core.bot import Red
import asyncio
from typing import Optional, Dict, List, Set
import logging
import random

log = logging.getLogger("red.dicegame")


class DiceGameView(discord.ui.View):
    """View for dice game betting"""
    
    def __init__(self, cog):
        super().__init__(timeout=30)
        self.cog = cog
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
        
    async def _create_embed(self) -> discord.Embed:
        """Create the embed for the dice game"""
        embed = discord.Embed(
            title="🎲 Animal Dice Game",
            description="Place your bets! Game starts in 30 seconds.",
            color=discord.Color.gold(),
        )
        
        
        # Show current bets
        if self.bets:
            bet_summary = {}
            total_players = len(self.bets)
            
            for user_id, user_bets in self.bets.items():
                for animal, amount in user_bets.items():
                    if animal not in bet_summary:
                        bet_summary[animal] = {"total": 0, "players": 0}
                    bet_summary[animal]["total"] += amount
                    bet_summary[animal]["players"] += 1
            
            bet_text = ""
            for animal in self.animals:
                emoji = self.animal_emojis[animal]
                if animal in bet_summary:
                    total = bet_summary[animal]["total"]
                    players = bet_summary[animal]["players"]
                    bet_text += f"{emoji} **{animal.title()}**: {total} credits ({players} players)\n"
                else:
                    bet_text += f"{emoji} **{animal.title()}**: 0 credits (0 players)\n"
            
            embed.add_field(
                name="Current Bets",
                value=bet_text,
                inline=False
            )
            
            embed.add_field(
                name="Total Players",
                value=str(total_players),
                inline=True
            )
        else:
            embed.add_field(
                name="Current Bets",
                value="No bets placed yet!",
                inline=False
            )
            
        return embed
        
    async def _create_results_embed(self, winning_animals: List[str], payouts: Dict[int, int]) -> discord.Embed:
        """Create the results embed"""
        winning_emojis = [self.animal_emojis[animal] for animal in winning_animals]
        embed = discord.Embed(
            title="🎲 Dice Game Results!",
            description=f"Winning animals: {' '.join(winning_emojis)} **{', '.join([animal.title() for animal in winning_animals])}**",
            color=discord.Color.green(),
        )
        
        if payouts:
            winners_text = ""
            total_payout = 0
            for user_id, payout in payouts.items():
                # Show winner's bet details
                user_bets = self.bets.get(user_id, {})
                bet_details = []
                for animal in user_bets.items():
                    if animal in winning_animals:
                        bet_details.append(f" {animal}")
                
                bet_info = f"{', '.join(bet_details)}" if bet_details else ""
                winners_text += f"<@{user_id}>: +{payout} credits{bet_info}\n"
                total_payout += payout
                
            embed.add_field(
                name="Winners",
                value=winners_text,
                inline=False
            )
            
            embed.add_field(
                name="Total Payout",
                value=f"{total_payout} credits",
                inline=True
            )
        else:
            embed.add_field(
                name="Winners",
                value="No winners this round!",
                inline=False
            )
            
        return embed
        
    async def on_timeout(self):
        """Handle when betting time expires"""
        if not self.message:
            return
            
        try:
            # Roll dice (3 dice, each can land on any animal)
            winning_animals = [random.choice(self.animals) for _ in range(3)]
            
            # Calculate payouts
            payouts = {}
            for user_id, user_bets in self.bets.items():
                total_payout = 0
                for animal, bet_amount in user_bets.items():
                    wins = winning_animals.count(animal)
                    if wins > 0:
                        # Payout is bet_amount * number_of_wins * 2
                        payout = bet_amount * wins * 2
                        total_payout += payout
                        
                if total_payout > 0:
                    payouts[user_id] = total_payout
                    
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
                    
            # Create results embed
            results_embed = await self._create_results_embed(winning_animals, payouts)
            
            # Update message with results
            await self.message.edit(embed=results_embed, view=None)
            
            # Clean up from active games
            if hasattr(self, 'cleanup'):
                self.cleanup()
            
        except Exception as e:
            log.error(f"Error in dice game timeout: {e}")
            
        self.stop()


class DiceGame(commands.Cog):
    """
    Animal dice betting game with 30-second betting rounds
    """
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.active_games: Dict[int, DiceGameView] = {}  # channel_id -> game_view
        
    async def cog_load(self):
        """Called when the cog is loaded"""
        log.info("DiceGame cog loaded")
        
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        # Cancel all active games
        for game in self.active_games.values():
            game.stop()
        log.info("DiceGame cog unloaded")
        
        
        
    @app_commands.command(name="dicegame", description="Place a bet in the dice game (starts game if needed)")
    @app_commands.describe(
        amount="Amount of credits to bet",
        animals="Animals to bet on (space-separated): fish, shrimp, crab, rooster, dragon, tiger"
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
            game_view = DiceGameView(self)
            embed = await game_view._create_embed()
            
            await interaction.response.send_message(
                embed=embed,
                view=game_view
            )
            
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
            embed = await game_view._create_embed()
            await game_view.message.edit(embed=embed)
            
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