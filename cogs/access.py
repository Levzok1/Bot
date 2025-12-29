# cogs/access.py
import json
import os
import discord
from discord import app_commands
from discord.ext import commands

# <<< СЮДА ВСТАВЬ ID роли разработчика >>>
DEV_ROLE_ID = "<@914221453258420265>, <@&1373259776548671589>"  # <- замени на реальный ID роли

DATA_PATH = "data/access.json"


def load_data() -> dict:
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_data(data: dict):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_dev():
    """Проверка: есть ли у пользователя Dev-роль или админка."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True

        role = interaction.guild.get_role(DEV_ROLE_ID)
        return role is not None and role in interaction.user.roles

    return app_commands.check(predicate)


class Access(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = load_data()

    # --- Вспомогательное ---
    def get_guild_cfg(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.data:
            self.data[gid] = {"allowed_users": []}
        return self.data[gid]

    def user_has_access(self, guild_id: int, user_id: int) -> bool:
        cfg = self.get_guild_cfg(guild_id)
        return user_id in cfg["allowed_users"]

    # --- Команды Dev panel ---

    @app_commands.command(
        name="givebot",
        description="Give access to use bot commands. / Выдать доступ к боту."
    )
    @app_commands.describe(user="Кому выдать доступ")
    @is_dev()
    async def givebot(self, interaction: discord.Interaction, user: discord.Member):
        cfg = self.get_guild_cfg(interaction.guild_id)

        if user.id in cfg["allowed_users"]:
            await interaction.response.send_message(
                f"⚠ {user.mention} уже имеет доступ к боту.",
                ephemeral=True
            )
            return

        cfg["allowed_users"].append(user.id)
        save_data(self.data)

        await interaction.response.send_message(
            f"✅ {user.mention} теперь имеет доступ к командам бота.",
            ephemeral=True
        )

    @app_commands.command(
        name="takebot",
        description="Remove access to use bot commands. / Забрать доступ к боту."
    )
    @app_commands.describe(user="У кого забрать доступ")
    @is_dev()
    async def takebot(self, interaction: discord.Interaction, user: discord.Member):
        cfg = self.get_guild_cfg(interaction.guild_id)

        if user.id not in cfg["allowed_users"]:
            await interaction.response.send_message(
                f"⚠ У {user.mention} и так нет доступа к боту.",
                ephemeral=True
            )
            return

        cfg["allowed_users"].remove(user.id)
        save_data(self.data)

        await interaction.response.send_message(
            f"✅ У {user.mention} забран доступ к командам бота.",
            ephemeral=True
        )

    # --- Хелпер для других cog'ов ---

    def has_access(self, interaction: discord.Interaction) -> bool:
        """Проверка доступа к ‘важным’ командам в других cog'ах."""
        if interaction.user.guild_permissions.administrator:
            return True
        return self.user_has_access(interaction.guild_id, interaction.user.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Access(bot))
