import discord
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging

log = logging.getLogger("red.gameping")


class GamePingView(discord.ui.View):
    """View containing Join/Can't Join buttons for game pings"""
    
    def __init__(self, cog, game: str, players_needed: int, role_id: int, 
                 channel_id: int, guild_id: int, author_id: int):
        super().__init__(timeout=1800)  # 30 minutes timeout
        self.cog = cog
        self.game = game
        self.players_needed = players_needed
        self.role_id = role_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.author_id = author_id
        self.joined_users: List[int] = [author_id]  # Auto-add the creator
        self.message: Optional[discord.Message] = None
        self.bot = cog.bot
        
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
        embed = discord.Embed(
            title=f"🎮 Game: {self.game}",
            description=f"Looking for people to play **{self.game}**\nStarted by <@{self.author_id}>",
            color=discord.Color.blue() if players_joined < self.players_needed else discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Players",
            value=f"{players_joined}/{self.players_needed}",
            inline=True
        )
        
        if self.joined_users:
            joined_mentions = [f"<@{uid}>" for uid in self.joined_users]
            embed.add_field(
                name="Joined",
                value="\n".join(joined_mentions[:10]) + 
                      (f"\n*and {len(joined_mentions) - 10} more...*" if len(joined_mentions) > 10 else ""),
                inline=False
            )
            
        embed.set_footer(text="Expires in 30 minutes")
        return embed
        
    async def _game_ready(self, interaction: discord.Interaction):
        """Handle when game has enough players"""
        # Disable buttons
        for item in self.children:
            item.disabled = True
            
        # Send ready message
        channel = interaction.channel
        if channel:
            joined_mentions = " ".join([f"<@{uid}>" for uid in self.joined_users])
            ready_embed = discord.Embed(
                title="🎮 Game Ready!",
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
                channel = self.bot.get_channel(self.channel_id)
                if channel:
                    self.message = await channel.fetch_message(self.message.id)
            except discord.NotFound:
                log.error("Message not found for timeout update")
                return
            except Exception as e:
                log.error(f"Error fetching message: {e}")
                return
                
            embed = discord.Embed(
                title=f"🎮 Game: {self.game} - CANCELLED",
                description="Not enough players joined in time. Game cancelled.",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            
            if self.joined_users:
                joined_mentions = [f"<@{uid}>" for uid in self.joined_users]
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


class GamePing(commands.Cog):
    """
    Create game pings with slash commands and interactive buttons
    """
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.active_views: Dict[int, GamePingView] = {}  # Track active views by message ID
        
        # Guild config
        default_guild = {
            "game_configs": {}  # {game_name: {"role_id": int, "channel_id": int}}
        }
        
        self.config.register_guild(**default_guild)
        
    async def cog_load(self):
        """Called when the cog is loaded"""
        log.info("GamePing cog loaded")
        
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        # Cancel all active views
        for view in self.active_views.values():
            view.stop()
        log.info("GamePing cog unloaded")
        
    @app_commands.command(name="gameping", description="Configure a game ping")
    @app_commands.describe(
        game="Name of the game",
        role="Role to ping for this game",
        channel="Channel where game pings will be sent"
    )
    @app_commands.guild_only()
    async def gameping_slash(
        self, 
        interaction: discord.Interaction,
        game: str,
        role: discord.Role,
        channel: discord.TextChannel
    ):
        """Configure a game ping"""
        # Check permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need Manage Server permission to configure game pings.",
                ephemeral=True
            )
            return
            
        # Save configuration
        guild_config = await self.config.guild(interaction.guild).game_configs()
        guild_config[game.lower()] = {
            "role_id": role.id,
            "channel_id": channel.id,
            "game_display_name": game
        }
        await self.config.guild(interaction.guild).game_configs.set(guild_config)
        
        # Create confirmation embed
        embed = discord.Embed(
            title="✅ Game Ping Configured",
            description=f"Game ping for **{game}** has been configured!",
            color=discord.Color.green()
        )
        embed.add_field(name="Game", value=game, inline=True)
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(
            name="Usage",
            value=f"Players can now use `/ping` and select **{game}** to create a game ping.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="ping", description="Look for players for a game")
    @app_commands.describe(
        game="Select the game you want to play",
        players_needed="Number of players needed (default: 5)"
    )
    @app_commands.guild_only()
    async def game_slash(
        self,
        interaction: discord.Interaction,
        game: str,
        players_needed: Optional[app_commands.Range[int, 1, 50]] = 5
    ):
        """Create a game ping"""
        # Get guild config
        guild_config = await self.config.guild(interaction.guild).game_configs()
        
        # Check if game is configured
        game_lower = game.lower()
        matching_games = [g for g in guild_config.keys() if g.startswith(game_lower)]
        
        if not matching_games:
            await interaction.response.send_message(
                f"No game configuration found for **{game}**. "
                "An admin needs to set it up using `/gameping` first.",
                ephemeral=True
            )
            return
            
        # Use first matching game
        game_key = matching_games[0]
        game_config = guild_config[game_key]
        
        # Get role and channel
        role = interaction.guild.get_role(game_config["role_id"])
        channel = interaction.guild.get_channel(game_config["channel_id"])
        
        if not role:
            await interaction.response.send_message(
                "The configured role for this game no longer exists. "
                "Please ask an admin to reconfigure it.",
                ephemeral=True
            )
            return
            
        if not channel:
            await interaction.response.send_message(
                "The configured channel for this game no longer exists. "
                "Please ask an admin to reconfigure it.",
                ephemeral=True
            )
            return
            
        # Check if user is in the correct channel
        if interaction.channel.id != channel.id:
            await interaction.response.send_message(
                f"Game pings for **{game_config['game_display_name']}** "
                f"must be created in {channel.mention}",
                ephemeral=True
            )
            return
            
        # Create the game ping view
        view = GamePingView(
            cog=self,
            game=game_config['game_display_name'],
            players_needed=players_needed,
            role_id=role.id,
            channel_id=channel.id,
            guild_id=interaction.guild.id,
            author_id=interaction.user.id
        )
        
        # Create initial embed
        embed = await view._create_embed()
        
        # Send the message
        await interaction.response.send_message(
            content=f"{role.mention} - Looking for players!",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )
        
        # Get the message and store it in the view
        view.message = await interaction.original_response()
        
        # Track the view
        self.active_views[view.message.id] = view
        
        # Check if game is already ready (e.g., 1 player game)
        if players_needed == 1:
            # Game is immediately ready
            joined_mentions = f"<@{interaction.user.id}>"
            ready_embed = discord.Embed(
                title="🎮 Game Ready!",
                description=f"**{game_config['game_display_name']}** is ready to start!",
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
            
            # Disable the view
            for item in view.children:
                item.disabled = True
            await view.message.edit(view=view)
            view.stop()
            self.active_views.pop(view.message.id, None)
        
        # Check if game is already ready (e.g., 1 player game)
        if players_needed == 1:
            await view._game_ready(interaction)
        
    @game_slash.autocomplete("game")
    async def game_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for game names"""
        guild_config = await self.config.guild(interaction.guild).game_configs()
        
        choices = []
        for game_key, config in guild_config.items():
            game_name = config.get('game_display_name', game_key)
            if current.lower() in game_name.lower():
                choices.append(
                    app_commands.Choice(name=game_name, value=game_name)
                )
                
        return choices[:25]  # Discord limits to 25 choices
        
    # Text command versions for backwards compatibility
    @commands.group(name="gameping", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def gameping(self, ctx: commands.Context):
        """Configure game pings"""
        await ctx.send_help(ctx.command)
        
    @gameping.command(name="setup")
    async def gameping_setup(
        self,
        ctx: commands.Context,
        game: str,
        role: discord.Role,
        channel: discord.TextChannel
    ):
        """Set up a game ping configuration"""
        # Save configuration
        guild_config = await self.config.guild(ctx.guild).game_configs()
        guild_config[game.lower()] = {
            "role_id": role.id,
            "channel_id": channel.id,
            "game_display_name": game
        }
        await self.config.guild(ctx.guild).game_configs.set(guild_config)
        
        await ctx.send(
            f"✅ Game ping configured!\n"
            f"**Game:** {game}\n"
            f"**Role:** {role.mention}\n"
            f"**Channel:** {channel.mention}"
        )
        
    @gameping.command(name="list")
    async def gameping_list(self, ctx: commands.Context):
        """List all configured game pings"""
        guild_config = await self.config.guild(ctx.guild).game_configs()
        
        if not guild_config:
            await ctx.send("No game pings configured yet!")
            return
            
        embed = discord.Embed(
            title="Configured Game Pings",
            color=discord.Color.blue()
        )
        
        for game_key, config in guild_config.items():
            role = ctx.guild.get_role(config["role_id"])
            channel = ctx.guild.get_channel(config["channel_id"])
            
            embed.add_field(
                name=config.get('game_display_name', game_key),
                value=f"Role: {role.mention if role else 'Deleted'}\n"
                      f"Channel: {channel.mention if channel else 'Deleted'}",
                inline=False
            )
            
        await ctx.send(embed=embed)
        
    @gameping.command(name="remove")
    async def gameping_remove(self, ctx: commands.Context, *, game: str):
        """Remove a game ping configuration"""
        guild_config = await self.config.guild(ctx.guild).game_configs()
        
        game_lower = game.lower()
        if game_lower in guild_config:
            del guild_config[game_lower]
            await self.config.guild(ctx.guild).game_configs.set(guild_config)
            await ctx.send(f"✅ Removed game ping configuration for **{game}**")
        else:
            await ctx.send(f"No configuration found for **{game}**")


async def setup(bot: Red):
    """Load the cog"""
    cog = GamePing(bot)
    await bot.add_cog(cog)