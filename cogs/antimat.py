import discord
from discord.ext import commands
from discord import app_commands
import os

WORDS_FILE = "cogs/words.txt"

# Создаём файл, если его нет
if not os.path.exists(WORDS_FILE):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        f.write("")


def load_words():
    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        return [w.strip().lower() for w in f.readlines()]


def save_words(words):
    with open(WORDS_FILE, "w", encoding="utf-8") as f:
        for w in words:
            f.write(w + "\n")


class AntiMat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ===== ФИЛЬТР СООБЩЕНИЙ =====
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
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
                except:
                    pass
                break

    # ===== /addword =====
    @app_commands.command(name="addword", description="Добавить слово в бан-лист")
    @app_commands.describe(word="Слово, которое нужно забанить")
    async def addword(self, interaction: discord.Interaction, word: str):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)

        word = word.lower().strip()
        words = load_words()

        if word in words:
            return await interaction.response.send_message("⚠ Это слово уже есть.", ephemeral=True)

        words.append(word)
        save_words(words)

        await interaction.response.send_message(f"➕ Добавлено слово: **{word}**")

    # ===== /delword =====
    @app_commands.command(name="delword", description="Удалить слово из бан-листа")
    @app_commands.describe(word="Слово, которое нужно удалить")
    async def delword(self, interaction: discord.Interaction, word: str):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ У вас нет прав!", ephemeral=True)

        word = word.lower().strip()
        words = load_words()

        if word not in words:
            return await interaction.response.send_message("❌ Этого слова нет.")

        words.remove(word)
        save_words(words)

        await interaction.response.send_message(f"🗑 Удалено слово: **{word}**")

    # ===== /words =====
    @app_commands.command(name="words", description="Показать список запрещённых слов")
    async def words(self, interaction: discord.Interaction):
        words = load_words()

        if not words:
            return await interaction.response.send_message("📃 Список пуст.")

        text = "\n".join(f"• {w}" for w in words)
        await interaction.response.send_message(f"📃 Запрещённые слова:\n{text}")


async def setup(bot):
    await bot.add_cog(AntiMat(bot))
