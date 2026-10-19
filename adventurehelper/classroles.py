import logging
import sys
from typing import Dict

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta

log = logging.getLogger("red.adventurehelper")

_ = Translator("AdventureHelper", __file__)


class AdventureClassRoles(MixinMeta):
    """Keep a Discord role in sync with each member's Adventure class"""

    def _hero_classes(self):
        adv_cog = self.bot.get_cog("Adventure")
        if adv_cog is None:
            return None
        adv_pkg = type(adv_cog).__module__.rsplit(".", 1)[0]
        return sys.modules[adv_pkg + ".constants"].HeroClasses

    @staticmethod
    def _find_class(hero_classes, name: str):
        name = name.lower()
        for clz in hero_classes:
            if name in (clz.value, clz.class_name.lower()):
                return clz
        return None

    async def _apply_class_role(self, member: discord.Member, class_value: str, class_roles: Dict[str, int]) -> bool:
        """Give the member their class role and remove every other class role.

        Returns True if the member's roles changed. Raises discord.HTTPException on failure.
        """
        roles = {clz: member.guild.get_role(role_id) for clz, role_id in class_roles.items()}
        to_add = roles.get(class_value)
        to_remove = [r for r in roles.values() if r is not None and r != to_add and r in member.roles]
        changed = False
        if to_remove:
            await member.remove_roles(*to_remove, reason=_("Adventure class changed"))
            changed = True
        if to_add is not None and to_add not in member.roles:
            await member.add_roles(to_add, reason=_("Adventure class changed"))
            changed = True
        return changed

    @commands.Cog.listener()
    async def on_adventure_class_change(self, user: discord.abc.User, old_class, new_class) -> None:
        """Update class roles in every server that has them configured.

        Adventure characters are global, so the class change applies wherever the user is a member.
        """
        for guild_id, data in (await self.config.all_guilds()).items():
            class_roles = data.get("class_roles")
            if not class_roles:
                continue
            guild = self.bot.get_guild(guild_id)
            if guild is None or await self.bot.cog_disabled_in_guild(self, guild):
                continue
            member = guild.get_member(user.id)
            if member is None:
                continue
            try:
                await self._apply_class_role(member, new_class.value, class_roles)
            except discord.HTTPException as e:
                log.warning(f"Could not update class roles for {user} in {guild}: {e}")

    @commands.group(name="classrole")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_roles=True)
    async def classrole(self, ctx: commands.Context) -> None:
        """Link Discord roles to Adventure classes"""
        pass

    @classrole.command(name="set")
    async def classrole_set(self, ctx: commands.Context, class_name: str, *, role: discord.Role) -> None:
        """
        Set the role given to members of a class

        Example: `[p]classrole set wizard @Wizards`
        """
        hero_classes = self._hero_classes()
        if hero_classes is None:
            return await ctx.send(_("Adventure cog not found."))
        clz = self._find_class(hero_classes, class_name)
        if clz is None:
            names = ", ".join(c.value for c in hero_classes)
            return await ctx.send(_("Unknown class. Valid classes are: {names}").format(names=names))
        if role.is_default() or role.managed:
            return await ctx.send(_("That role can't be assigned to members."))
        if role >= ctx.guild.me.top_role:
            return await ctx.send(
                _("**{role}** is above my highest role, so I can't assign it. Move it below my role first.").format(
                    role=role.name
                )
            )
        async with self.config.guild(ctx.guild).class_roles() as class_roles:
            class_roles[clz.value] = role.id
        msg = _("Members who become a **{clz}** will now get **{role}**.").format(clz=clz.class_name, role=role.name)
        if not ctx.guild.me.guild_permissions.manage_roles:
            msg += "\n" + _("Warning: I don't have the Manage Roles permission, so I can't assign it yet.")
        await ctx.send(msg)

    @classrole.command(name="clear")
    async def classrole_clear(self, ctx: commands.Context, class_name: str) -> None:
        """Stop giving a role for a class"""
        hero_classes = self._hero_classes()
        if hero_classes is None:
            return await ctx.send(_("Adventure cog not found."))
        clz = self._find_class(hero_classes, class_name)
        if clz is None:
            return await ctx.send(_("Unknown class."))
        async with self.config.guild(ctx.guild).class_roles() as class_roles:
            removed = class_roles.pop(clz.value, None)
        if removed is None:
            return await ctx.send(_("No role is set for **{clz}**.").format(clz=clz.class_name))
        await ctx.send(_("**{clz}** no longer has a role.").format(clz=clz.class_name))

    @classrole.command(name="list")
    async def classrole_list(self, ctx: commands.Context) -> None:
        """Show which role is linked to each class"""
        hero_classes = self._hero_classes()
        if hero_classes is None:
            return await ctx.send(_("Adventure cog not found."))
        class_roles = await self.config.guild(ctx.guild).class_roles()
        lines = []
        for clz in hero_classes:
            role = ctx.guild.get_role(class_roles.get(clz.value, 0))
            lines.append(f"**{clz.class_name}**: {role.name if role else _('not set')}")
        await ctx.send("\n".join(lines))

    @classrole.command(name="sync")
    @commands.bot_has_permissions(manage_roles=True)
    async def classrole_sync(self, ctx: commands.Context) -> None:
        """Give every member the role for their current class

        Use this after setting up class roles so existing players get theirs.
        """
        adv_cog = self.bot.get_cog("Adventure")
        hero_classes = self._hero_classes()
        if adv_cog is None or hero_classes is None:
            return await ctx.send(_("Adventure cog not found."))
        class_roles = await self.config.guild(ctx.guild).class_roles()
        if not class_roles:
            return await ctx.send(_("No class roles are set up. Use `{prefix}classrole set` first.").format(
                prefix=ctx.clean_prefix
            ))

        updated = failed = 0
        async with ctx.typing():
            for user_id, data in (await adv_cog.config.all_users()).items():
                member = ctx.guild.get_member(user_id)
                if member is None or member.bot:
                    continue
                heroclass = data.get("heroclass") or data.get("class") or {}
                clz = hero_classes.from_name(heroclass.get("name", "hero"))
                try:
                    if await self._apply_class_role(member, clz.value, class_roles):
                        updated += 1
                except discord.HTTPException as e:
                    log.warning(f"Could not sync class roles for {member} in {ctx.guild}: {e}")
                    failed += 1

        msg = _("Class roles synced. Updated {updated} members.").format(updated=updated)
        if failed:
            msg += " " + _("Failed for {failed} members (check my role position).").format(failed=failed)
        await ctx.send(msg)
