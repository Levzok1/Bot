import discord
from discord.ext import commands
from discord import app_commands
import os


OWNER_ID = int(os.getenv("DISCORD_OWNER_ID", "0"))


class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="invites",
        description="(Owner) Получить инвайты на серверы, где есть бот"
    )
    async def invites(self, interaction: discord.Interaction):
        # 🔒 Только владелец бота
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                "❌ У тебя нет доступа к этой команде.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "📨 Я отправил тебе список серверов в личные сообщения.",
            ephemeral=True
        )

        lines = []
        for guild in self.bot.guilds:
            invite_link = None

            # Пытаемся создать инвайт
            try:
                for channel in guild.text_channels:
                    perms = channel.permissions_for(guild.me)
                    if perms.create_instant_invite:
                        invite = await channel.create_invite(
                            max_age=0,
                            max_uses=0,
                            reason="Owner requested server invite"
                        )
                        invite_link = invite.url
                        break
            except Exception:
                invite_link = None

            if invite_link:
                lines.append(
                    f"**{guild.name}**\n"
                    f"👥 {guild.member_count}\n"
                    f"🔗 {invite_link}\n"
                )
            else:
                lines.append(
                    f"**{guild.name}**\n"
                    f"👥 {guild.member_count}\n"
                    f"❌ Нет прав на создание инвайта\n"
                )

        text = "\n".join(lines)
        if not text:
            text = "Бот не состоит ни на одном сервере."

        # Отправляем в ЛС
        try:
            await interaction.user.send(text)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))
