import discord
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging

log = logging.getLogger("red.riotgameping")


class RiotGamePingView(discord.ui.View):
    """View containing Join/Can't Join buttons for riot game pings"""
    
    def __init__(self, cog, game: str, players_needed: int, minutes_till_expiry: int, author_id: int):
        super().__init__(timeout=minutes_till_expiry*60)
        self.cog = cog
        self.game = game
        self.players_needed = players_needed + 1 # The author counts as one
        self.author_id = author_id
        self.joined_users: List[int] = [author_id]  # Auto add the author for a game
        self.message: Optional[discord.Message] = None
        self.bot = cog.bot
        self.minutes_till_expiry = minutes_till_expiry
        self.created_at = datetime.utcnow()  # Track when the game ping was created
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user can interact with the buttons"""
        # Check which button was clicked
        custom_id = interaction.data.get("custom_id", "")
        
        # If it's the can't anymore button, check if user has joined
        if "cant_join" in custom_id:
            if interaction.user.id not in self.joined_users:
                await interaction.response.send_message(
                    "You need to join the game first before you can leave!",
                    ephemeral=True
                )
                return False
                
        return True
        
    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, emoji="✅")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle join button clicks"""
        user_id = interaction.user.id
        
        # Check if user already joined
        if user_id in self.joined_users:
            await interaction.response.send_message(
                "You have already joined this game!", ephemeral=True
            )
            return
            
        # Add user to joined list
        self.joined_users.append(user_id)
        
        # Update the message
        embed = await self._create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Check if we have enough players
        if len(self.joined_users) >= self.players_needed:
            await self._game_ready(interaction)
            
    @discord.ui.button(label="Can't Anymore", style=discord.ButtonStyle.danger, emoji="❌", custom_id="cant_join")
    async def cant_join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle can't join button clicks"""
        user_id = interaction.user.id
        
        # Remove user from joined list
        self.joined_users.remove(user_id)
        embed = await self._create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
            
    async def _create_embed(self) -> discord.Embed:
        """Create the embed for the game ping message"""
        players_joined = len(self.joined_users)
        
        # Set color and emoji based on game
        if self.game == "Valorant":
            color = discord.Color.red()
            emoji = "<:emoji:740501303838638092>"
        else:  # League of Legends
            color = discord.Color.blue()
            emoji = "<:emoji:740501304165662750>"
            
        embed = discord.Embed(
            title=f"{emoji} Game: {self.game}",
            description=f"Looking for people to play **{self.game}**\nStarted by <@{self.author_id}>",
            color=color if players_joined < self.players_needed else discord.Color.green(),
            timestamp=self.created_at  # Use creation time instead of current time
        )
        
        embed.add_field(
            name="Players",
            value=f"{players_joined}/{self.players_needed}",
            inline=True
        )
        
        # Show both the author and joined users in the "Joined" field
        all_players = [self.author_id] + self.joined_users
        if all_players:
            joined_mentions = [f"<@{uid}>" for uid in all_players]
            embed.add_field(
                name="Joined",
                value="\n".join(joined_mentions[:10]) + 
                      (f"\n*and {len(joined_mentions) - 10} more...*" if len(joined_mentions) > 10 else ""),
                inline=False
            )
            
        # Calculate remaining time
        elapsed_time = datetime.utcnow() - self.created_at
        remaining_time = timedelta(minutes=self.minutes_till_expiry) - elapsed_time
        remaining_minutes = max(0, int(remaining_time.total_seconds() / 60))
        
        embed.set_footer(text=f"Expires in {remaining_minutes} minutes")
        return embed
        
    async def _game_ready(self, interaction: discord.Interaction):
        """Handle when game has enough players"""
        # Disable buttons
        for item in self.children:
            item.disabled = True
            
        # Send ready message
        channel = interaction.channel
        if channel:
            # Include both author and joined users in the ready message
            all_players = [self.author_id] + self.joined_users
            joined_mentions = " ".join([f"<@{uid}>" for uid in all_players])
            
            # Set emoji based on game
            emoji = "<:emoji:740501303838638092>" if self.game == "Valorant" else "<:emoji:740501304165662750>"
            
            ready_embed = discord.Embed(
                title=f"{emoji} Game Ready!",
                description=f"**{self.game}** is ready to start!",
                color=discord.Color.green()
            )
            ready_embed.add_field(
                name="Players",
                value=joined_mentions
            )
            await channel.send(
                content=f"{joined_mentions} - Your game is ready!",
                embed=ready_embed
            )
            
        # Clean up from active views
        if hasattr(self.cog, 'active_views') and self.message:
            self.cog.active_views.pop(self.message.id, None)
            
        self.stop()
        
    async def on_timeout(self):
        """Handle view timeout"""
        # Ensure we have the message reference
        if not self.message:
            log.error("No message reference found for timeout handling")
            return
            
        try:
            # Fetch the message to ensure it still exists
            try:
                channel = self.message.channel
                if channel:
                    self.message = await channel.fetch_message(self.message.id)
            except discord.NotFound:
                log.error("Message not found for timeout update")
                return
            except Exception as e:
                log.error(f"Error fetching message: {e}")
                return
                
            # Set emoji based on game
            emoji = "<:emoji:740501303838638092>" if self.game == "Valorant" else "<:emoji:740501304165662750>"
                
            embed = discord.Embed(
                title=f"{emoji} Game: {self.game} - CANCELLED",
                description="Not enough players joined in time. Game cancelled.",
                color=discord.Color.red(),
                timestamp=self.created_at  # Use creation time for consistency
            )
            
            # Show both author and joined users in timeout message
            all_players = [self.author_id] + self.joined_users
            if all_players:
                joined_mentions = [f"<@{uid}>" for uid in all_players]
                embed.add_field(
                    name="Players who joined",
                    value="\n".join(joined_mentions[:10]),
                    inline=False
                )
                
            # Create a new view with disabled buttons
            new_view = discord.ui.View()
            button1 = discord.ui.Button(label="Join", style=discord.ButtonStyle.success, 
                                       emoji="✅", disabled=True)
            button2 = discord.ui.Button(label="Can't Anymore", style=discord.ButtonStyle.danger, 
                                       emoji="❌", disabled=True)
            new_view.add_item(button1)
            new_view.add_item(button2)
                
            await self.message.edit(embed=embed, view=new_view)
            log.info(f"Game ping for {self.game} timed out and was cancelled")
            
            # Clean up from active views
            if hasattr(self.cog, 'active_views'):
                self.cog.active_views.pop(self.message.id, None)
        except Exception as e:
            log.error(f"Failed to update timed out game message: {e}")


class RiotGamePing(commands.Cog):
    """
    Create game pings for Riot Games (Valorant and League of Legends)
    """
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.active_views: Dict[int, RiotGamePingView] = {}  # Track active views by message ID
        
        # Hardcoded role IDs for Riot games
        self.VALORANT_ROLE_ID = 700130013168664628
        self.LOL_ROLE_ID = 698726804747452456
        
    async def cog_load(self):
        """Called when the cog is loaded"""
        log.info("RiotGamePing cog loaded")
        
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        # Cancel all active views
        for view in self.active_views.values():
            view.stop()
        log.info("RiotGamePing cog unloaded")
        
    @app_commands.command(name="val", description="Look for players for Valorant")
    @app_commands.describe(players_needed="Number of players needed (default: 4)")
    @app_commands.guild_only()
    async def valorant_ping(
        self,
        interaction: discord.Interaction,
        players_needed: Optional[app_commands.Range[int, 1, 10]] = 4
    ):
        """Create a Valorant game ping"""
        await self._create_game_ping(interaction, "Valorant", players_needed, self.VALORANT_ROLE_ID)
        
    @app_commands.command(name="lol", description="Look for players for League of Legends")
    @app_commands.describe(players_needed="Number of players needed (default: 4)")
    @app_commands.guild_only()
    async def lol_ping(
        self,
        interaction: discord.Interaction,
        players_needed: Optional[app_commands.Range[int, 1, 10]] = 4
    ):
        """Create a League of Legends game ping"""
        await self._create_game_ping(interaction, "League of Legends", players_needed, self.LOL_ROLE_ID)
        
    async def _create_game_ping(self, interaction: discord.Interaction, game: str, players_needed: int, minutes_till_expiry: int, role_id: int):
        """Create a game ping for the specified game"""
        # Get the role
        role = interaction.guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message(
                f"The {game} role could not be found. Please contact an admin.",
                ephemeral=True
            )
            return
        
        # Create the game ping view
        view = RiotGamePingView(
            cog=self,
            game=game,
            players_needed=players_needed,
            minutes_till_expiry=minutes_till_expiry,
            author_id=interaction.user.id
        )
        
        # Create initial embed
        embed = await view._create_embed()
        
        # Send the message with role ping
        await interaction.response.send_message(
            content=f"{role.mention} Looking for **{players_needed}** players!",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )
        
        # Get the message and store it in the view
        view.message = await interaction.original_response()
        
        # Track the view
        self.active_views[view.message.id] = view
        
        # Check if game is already ready (e.g., 1 player game with 0 needed)
        if players_needed == 0:
            await view._game_ready(interaction)


async def setup(bot: Red):
    """Load the cog"""
    cog = RiotGamePing(bot)
    await bot.add_cog(cog)
