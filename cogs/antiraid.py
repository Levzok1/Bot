import discord
from discord.ext import commands
from datetime import datetime, timedelta

MIN_ACCOUNT_AGE_DAYS = 7  # минимальный возраст аккаунта
AUTO_MUTE_REASON = "Анти-рейд: слишком новый аккаунт"


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_muted_role(self, guild: discord.Guild) -> discord.Role:
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if muted_role is None:
            muted_role = await guild.create_role(name="Muted")
            # минимальные ограничения по каналам можно будет настроить руками
        return muted_role

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # проверка возраста аккаунта
        now = datetime.utcnow()
        account_age = now - member.created_at.replace(tzinfo=None)

        if account_age < timedelta(days=MIN_ACCOUNT_AGE_DAYS):
            muted_role = await self.ensure_muted_role(member.guild)
            try:
                await member.add_roles(muted_role, reason=AUTO_MUTE_REASON)
            except discord.HTTPException:
                return

            try:
                await member.send(
                    f"👋 Добро пожаловать на сервер **{member.guild.name}**!\n"
                    f"Ваш аккаунт слишком новый, поэтому временно выдан мут "
                    f"по причине: **{AUTO_MUTE_REASON}**.\n"
                    f"Свяжитесь с модератором, если это ошибка."
                )
            except discord.HTTPException:
                pass

            # лог в консоль
            print(
                f"[ANTIRAID] {member} ({member.id}) получил мут "
                f"за возраст аккаунта {account_age} (<{MIN_ACCOUNT_AGE_DAYS}d)"
            )


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    ...
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        ...
        # твой код


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
