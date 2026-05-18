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


def parse_words(raw_words: str) -> list[str]:
    parsed_words = []
    seen = set()

    for raw_word in raw_words.replace("\n", ",").split(","):
        word = raw_word.strip().lower()
        if word and word not in seen:
            parsed_words.append(word)
            seen.add(word)

    return parsed_words


def format_words(words: list[str]) -> str:
    return "\n".join(f"• {word}" for word in words)


async def send_chunked(interaction: discord.Interaction, message: str, *, ephemeral: bool = False):
    chunks = chunk_text(message)
    await interaction.response.send_message(chunks[0], ephemeral=ephemeral)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=ephemeral)


def setting_enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "нет"}
    return bool(value)


class AntiMat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _require_word_manager(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)
            return False

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)
            return False

        return True

    async def _add_words(self, interaction: discord.Interaction, raw_words: str):
        if not await self._require_word_manager(interaction):
            return

        requested_words = parse_words(raw_words)
        if not requested_words:
            return await interaction.response.send_message("❌ Список слов не может быть пустым.", ephemeral=True)

        words = load_words()
        existing_words = set(words)
        added_words = [item for item in requested_words if item not in existing_words]
        skipped_words = [item for item in requested_words if item in existing_words]

        if not added_words:
            message = "⚠ Все эти слова уже есть в списке:\n" + format_words(skipped_words)
            return await send_chunked(interaction, message, ephemeral=True)

        words.extend(added_words)
        save_words(words)

        message_parts = [f"➕ Добавлено слов: **{len(added_words)}**", format_words(added_words)]
        if skipped_words:
            message_parts.extend(["", f"⚠ Уже были в списке: **{len(skipped_words)}**", format_words(skipped_words)])
        await send_chunked(interaction, "\n".join(message_parts))

    async def _delete_words(self, interaction: discord.Interaction, raw_words: str):
        if not await self._require_word_manager(interaction):
            return

        requested_words = parse_words(raw_words)
        if not requested_words:
            return await interaction.response.send_message("❌ Список слов не может быть пустым.", ephemeral=True)

        words = load_words()
        existing_words = set(words)
        removed_words = [item for item in requested_words if item in existing_words]
        missing_words = [item for item in requested_words if item not in existing_words]

        if not removed_words:
            message = "❌ Этих слов нет в списке:\n" + format_words(missing_words)
            return await send_chunked(interaction, message, ephemeral=True)

        removed_set = set(removed_words)
        save_words([item for item in words if item not in removed_set])

        message_parts = [f"🗑 Удалено слов: **{len(removed_words)}**", format_words(removed_words)]
        if missing_words:
            message_parts.extend(["", f"⚠ Не найдены: **{len(missing_words)}**", format_words(missing_words)])
        await send_chunked(interaction, "\n".join(message_parts))

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
    @app_commands.command(name="addword", description="Добавить слово или несколько слов в бан-лист")
    @app_commands.guild_only()
    @app_commands.describe(word="Одно слово или несколько слов через запятую")
    async def addword(self, interaction: discord.Interaction, word: str):
        await self._add_words(interaction, word)

    @app_commands.command(name="addworl", description="Алиас /addword: добавить несколько слов через запятую")
    @app_commands.guild_only()
    @app_commands.describe(word="Одно слово или несколько слов через запятую")
    async def addworl(self, interaction: discord.Interaction, word: str):
        await self._add_words(interaction, word)

    # ===== /delword =====
    @app_commands.command(name="delword", description="Удалить слово или несколько слов из бан-листа")
    @app_commands.guild_only()
    @app_commands.describe(word="Одно слово или несколько слов через запятую")
    async def delword(self, interaction: discord.Interaction, word: str):
        await self._delete_words(interaction, word)

    @app_commands.command(name="delworl", description="Алиас /delword: удалить несколько слов через запятую")
    @app_commands.guild_only()
    @app_commands.describe(word="Одно слово или несколько слов через запятую")
    async def delworl(self, interaction: discord.Interaction, word: str):
        await self._delete_words(interaction, word)

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
