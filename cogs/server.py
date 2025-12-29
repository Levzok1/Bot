import os
import discord
from discord import app_commands
from discord.ext import commands


class ServerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.owner_id = int(os.getenv("DISCORD_OWNER_ID", "0"))

    @app_commands.command(
        name="server",
        description="(Owner) Показать список серверов, где есть бот."
    )
    async def server(self, interaction: discord.Interaction):
        # ✅ Защита: только владелец бота
        if self.owner_id and interaction.user.id != self.owner_id:
            return await interaction.response.send_message(
                "❌ У тебя нет доступа к этой команде.",
                ephemeral=True
            )

        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
        total = len(guilds)

        # Discord лимит на embed field value ~1024, поэтому режем и делаем аккуратно
        lines = []
        for i, g in enumerate(guilds, start=1):
            lines.append(f"{i}) **{g.name}** — `ID: {g.id}` — 👥 {g.member_count}")

        text = "\n".join(lines)
        if len(text) > 3800:
            text = text[:3800] + "\n… (слишком много серверов, обрезано)"

        embed = discord.Embed(
            title="🌐 Servers list",
            description=f"Бот находится на **{total}** сервер(ах):\n\n{text}",
            color=0x2F3136
        )
        embed.set_footer(text=f"Requested by {interaction.user}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerCog(bot))
