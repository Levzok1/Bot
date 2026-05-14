from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord.ext import commands

MIN_ACCOUNT_AGE_DAYS = 7
MUTED_ROLE_NAME = "Muted"


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_muted_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        role = discord.utils.get(guild.roles, name=MUTED_ROLE_NAME)
        if role is not None:
            return role
        if guild.me is None or not guild.me.guild_permissions.manage_roles:
            return None

        permissions = discord.Permissions.none()
        try:
            role = await guild.create_role(name=MUTED_ROLE_NAME, permissions=permissions, reason="Создание роли для мута")
        except discord.HTTPException:
            return None

        for channel in guild.channels:
            overwrite = channel.overwrites_for(role)
            if isinstance(channel, discord.TextChannel):
                overwrite.send_messages = False
                overwrite.add_reactions = False
            if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                overwrite.speak = False
                overwrite.connect = False
            try:
                await channel.set_permissions(role, overwrite=overwrite, reason="Muted role setup")
            except discord.HTTPException:
                continue

        return role

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or member.guild is None:
            return

        now = datetime.now(timezone.utc)
        account_age = now - member.created_at
        if account_age >= timedelta(days=MIN_ACCOUNT_AGE_DAYS):
            return

        muted_role = await self.ensure_muted_role(member.guild)
        if muted_role is None:
            return
        if member.guild.me is None or member.top_role >= member.guild.me.top_role:
            return

        try:
            await member.add_roles(muted_role, reason="Анти-рейд: новый аккаунт")
        except discord.HTTPException:
            return

        try:
            await member.send(
                f"Твой аккаунт слишком новый для сервера {member.guild.name}, поэтому тебе временно ограничен доступ."
            )
        except discord.HTTPException:
            pass

        print(
            f"[AntiRaid] Участник {member} ({member.id}) заглушен на сервере {member.guild.name} "
            f"из-за нового аккаунта ({account_age.days} дней)."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiRaid(bot))
