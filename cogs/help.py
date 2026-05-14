# cogs/help.py
import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Показать список команд бота")
    async def help(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="Список команд",
            description="Список доступных slash-команд с описаниями на русском.",
            color=discord.Color.blurple()
        )

        # 🛡 MODERATION
        embed.add_field(
            name="🛡 Модерация",
            value=(
                "`/clear amount [channel]` — Удалить последние сообщения в канале.\n"
                "`/kick member [reason]` — Кикнуть участника.\n"
                "`/ban member [reason] [delete_messages]` — Забанить участника.\n"
                "`/mban member1 [member2] [reason] [delete_messages]` — Забанить до двух участников.\n"
                "`/randban [count] [reason]` — Рандомно забанить до 10 участников.\n"
                "`/unban user [reason]` — Разбанить пользователя.\n"
                "`/modlog [user]` — Показать журнал модерации сервера или пользователя."
            ),
            inline=False
        )

        # 🚫 ANTIMAT
        embed.add_field(
            name="🚫 Антимат",
            value=(
                "`/addword word` — Добавить запрещённое слово.\n"
                "`/delword word` — Удалить запрещённое слово.\n"
                "`/words` — Показать список запрещённых слов."
            ),
            inline=False
        )

        # 🎮 ИГРЫ
        embed.add_field(
            name="🎮 Игры",
            value=(
                "`/cs info` — Информация о CS-разделе.\n"
                "`/cs rules` — Правила CS.\n"
                "`/cs ranks` — Список CS-рангов.\n"
                "`/valorant nickname` — Пример статистики Valorant.\n"
                "`/fortnite nickname` — Пример статистики Fortnite."
            ),
            inline=False
        )

        # 🎵 МУЗЫКА
        embed.add_field(
            name="🎵 Музыка",
            value=(
                "`/join` — Подключить бота в голосовой канал.\n"
                "`/leave` — Отключить бота из голосового канала.\n"
                "`/play query` — Проиграть трек по ссылке или названию.\n"
                "`/skip` — Пропустить текущий трек.\n"
                "`/stop` — Остановить музыку и очистить очередь.\n"
                "`/pause` — Поставить музыку на паузу.\n"
                "`/resume` — Продолжить музыку.\n"
                "`/queue` — Показать очередь треков."
            ),
            inline=False
        )

        # ⚙️ НАСТРОЙКИ СЕРВЕРА
        embed.add_field(
            name="⚙️ Настройки сервера",
            value=(
                "`/config view` — Показать настройки сервера.\n"
                "`/config set key value` — Установить настройку для сервера.\n"
                "`/config delete key` — Удалить настройку сервера."
            ),
            inline=False
        )

        # 🌐 СЕРВЕРЫ И ИНВАЙТЫ
        embed.add_field(
            name="🌐 Серверы и инвайты",
            value=(
                "`/server` — Показать список серверов, где есть бот (владелец только).\n"
                "`/invites` — Получить инвайты на сервера, где есть бот (владелец только)."
            ),
            inline=False
        )

        # 🛠 ПАНЕЛЬ РАЗРАБОТЧИКА
        embed.add_field(
            name="🛠 Панель разработчика",
            value=(
                "`/dev action` — Панель разработчика / перезагрузка / статистика / выключение бота."
            ),
            inline=False
        )

        # ℹ ОБЩЕЕ
        embed.add_field(
            name="ℹ Общее",
            value=(
                "`/help` — Показать это меню помощи."
            ),
            inline=False
        )

        embed.set_footer(
            text=f"Запросил: {interaction.user}",
            icon_url=interaction.user.display_avatar.url
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
