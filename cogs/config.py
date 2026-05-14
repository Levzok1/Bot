import discord
from discord import app_commands
from discord.ext import commands

from .env_utils import chunk_text
from .guild_settings import get_guild_settings, set_guild_setting, delete_guild_setting


class Config(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    config = app_commands.Group(name="config", description="Настройки сервера", guild_only=True)

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)
            return False
        if interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message("У вас нет прав управлять сервером.", ephemeral=True)
        return False

    @config.command(name="view", description="Показать настройки сервера")
    async def view(self, interaction: discord.Interaction):
        if not await self._check(interaction):
            return
        guild_id = interaction.guild_id
        if guild_id is None:
            return

        settings = await get_guild_settings(guild_id)
        if not settings:
            return await interaction.response.send_message("Настройки для этого сервера не заданы.", ephemeral=True)

        chunks = chunk_text("\n".join(f"**{k}**: {v}" for k, v in settings.items()))
        await interaction.response.send_message(chunks[0], ephemeral=True)
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)

    @config.command(name="set", description="Установить настройку сервера")
    @app_commands.describe(key="Ключ настройки", value="Значение настройки")
    async def set_setting(self, interaction: discord.Interaction, key: str, value: str):
        if not await self._check(interaction):
            return
        guild_id = interaction.guild_id
        key = key.strip()
        if guild_id is None:
            return
        if not key:
            return await interaction.response.send_message("Ключ настройки не может быть пустым.", ephemeral=True)
        value = value.strip()
        await set_guild_setting(guild_id, key, value)
        await interaction.response.send_message(f"Настройка **{key}** установлена в: `{value}`", ephemeral=True)

    @config.command(name="delete", description="Удалить настройку сервера")
    @app_commands.describe(key="Ключ настройки")
    async def delete_setting(self, interaction: discord.Interaction, key: str):
        if not await self._check(interaction):
            return
        guild_id = interaction.guild_id
        key = key.strip()
        if guild_id is None:
            return
        if not key:
            return await interaction.response.send_message("Ключ настройки не может быть пустым.", ephemeral=True)
        await delete_guild_setting(guild_id, key)
        await interaction.response.send_message(f"Настройка **{key}** удалена.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Config(bot))
