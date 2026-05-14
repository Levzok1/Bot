import discord
from discord.ext import commands
from discord import app_commands
from pathlib import Path

from .env_utils import chunk_text
from .guild_settings import get_guild_setting

WORDS_FILE = Path(__file__).resolve().parent / "words.txt"
WORDS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Создаём файл, если его нет
if not WORDS_FILE.exists():
    WORDS_FILE.write_text("", encoding="utf-8")


def load_words():
    return [w.strip().lower() for w in WORDS_FILE.read_text(encoding="utf-8").splitlines() if w.strip()]


def save_words(words):
    WORDS_FILE.write_text("\n".join(words) + ("\n" if words else ""), encoding="utf-8")


def setting_enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "нет"}
    return bool(value)


class AntiMat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ===== ФИЛЬТР СООБЩЕНИЙ =====
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not setting_enabled(await get_guild_setting(message.guild.id, "antimat_enabled", True)):
            return

        words = load_words()
        text = message.content.lower()

        for bad in words:
            if bad in text:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"🚫 {message.author.mention}, запрещённое слово: **{bad}**",
                        delete_after=5
                    )
                except discord.HTTPException:
                    pass
                break

    # ===== /addword =====
    @app_commands.command(name="addword", description="Добавить слово в бан-лист")
    @app_commands.guild_only()
    @app_commands.describe(word="Слово, которое нужно забанить")
    async def addword(self, interaction: discord.Interaction, word: str):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)

        word = word.lower().strip()
        if not word:
            return await interaction.response.send_message("❌ Слово не может быть пустым.", ephemeral=True)

        words = load_words()

        if word in words:
            return await interaction.response.send_message("⚠ Это слово уже есть.", ephemeral=True)

        words.append(word)
        save_words(words)

        await interaction.response.send_message(f"➕ Добавлено слово: **{word}**")

    # ===== /delword =====
    @app_commands.command(name="delword", description="Удалить слово из бан-листа")
    @app_commands.guild_only()
    @app_commands.describe(word="Слово, которое нужно удалить")
    async def delword(self, interaction: discord.Interaction, word: str):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)

        word = word.lower().strip()
        if not word:
            return await interaction.response.send_message("❌ Слово не может быть пустым.", ephemeral=True)

        words = load_words()

        if word not in words:
            return await interaction.response.send_message("❌ Этого слова нет.")

        words.remove(word)
        save_words(words)

        await interaction.response.send_message(f"🗑 Удалено слово: **{word}**")

    # ===== /words =====
    @app_commands.command(name="words", description="Показать список запрещённых слов")
    @app_commands.guild_only()
    async def words(self, interaction: discord.Interaction):
        words = load_words()

        if not words:
            return await interaction.response.send_message("📃 Список пуст.")

        text = "\n".join(f"• {w}" for w in words)
        chunks = chunk_text(f"📃 Запрещённые слова:\n{text}")
        await interaction.response.send_message(chunks[0])
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk)


async def setup(bot):
    await bot.add_cog(AntiMat(bot))
