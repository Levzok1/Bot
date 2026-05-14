import discord
from discord.ext import commands
from discord import app_commands

from .env_utils import chunk_text, get_int_env

OWNER_ID = get_int_env("DISCORD_OWNER_ID")


class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="invites",
        description="Получить инвайты на серверы, где есть бот (только владелец)"
    )
    async def invites(self, interaction: discord.Interaction):
        # 🔒 Только владелец бота
        if not OWNER_ID or interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                "❌ У тебя нет доступа к этой команде.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        lines = []
        for guild in self.bot.guilds:
            invite_link = None

            # Пытаемся создать инвайт
            if guild.me is not None:
                for channel in guild.text_channels:
                    perms = channel.permissions_for(guild.me)
                    if not perms.create_instant_invite:
                        continue
                    try:
                        invite = await channel.create_invite(
                            max_age=0,
                            max_uses=0,
                            reason="Владелец запросил инвайт"
                        )
                        invite_link = invite.url
                        break
                    except discord.HTTPException:
                        continue

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
            for chunk in chunk_text(text):
                await interaction.user.send(chunk)
        except discord.Forbidden:
            return await interaction.followup.send("❌ Не удалось отправить ЛС. Открой личные сообщения от участников сервера.", ephemeral=True)
        except discord.HTTPException:
            return await interaction.followup.send("❌ Не удалось отправить список серверов в ЛС.", ephemeral=True)

        await interaction.followup.send("📨 Я отправил тебе список серверов в личные сообщения.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))
