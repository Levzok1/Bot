import discord
from discord.ext import commands
from discord import app_commands

from .env_utils import chunk_text, get_int_env

OWNER_ID = get_int_env("DISCORD_OWNER_ID")


def owner_only(interaction: discord.Interaction):
    return bool(OWNER_ID) and interaction.user.id == OWNER_ID


class DevPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========= SLASH =========

    @app_commands.command(name="dev", description="Команды разработчика")
    @app_commands.describe(action="panel / servers / invites / shutdown / botinfo")
    async def dev(self, interaction: discord.Interaction, action: str):
        if not owner_only(interaction):
            return await interaction.response.send_message(
                "❌ Доступ запрещён.", ephemeral=True
            )

        if interaction.guild is not None:
            return await interaction.response.send_message(
                "❌ Dev panel доступна только в личных сообщениях.",
                ephemeral=True
            )

        action = action.lower()

        if action == "panel":
            await interaction.response.send_message(
                embed=self.panel_embed(),
                view=DevPanelView(self.bot),
                ephemeral=True
            )

        elif action == "servers":
            await self.send_long_response(interaction, self.get_servers())

        elif action == "invites":
            await self.send_long_response(interaction, await self.get_invites())

        elif action == "botinfo":
            await interaction.response.send_message(
                self.bot_info(),
                ephemeral=True
            )

        elif action == "shutdown":
            await interaction.response.send_message("⛔ Бот выключается...", ephemeral=True)
            await self.bot.close()

        else:
            await interaction.response.send_message(
                "❌ Неизвестное действие.",
                ephemeral=True
            )

    # ========= HELPERS =========

    async def send_long_response(self, interaction: discord.Interaction, text: str) -> None:
        chunks = chunk_text(text)
        await interaction.response.send_message(chunks[0], ephemeral=True)
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)

    def panel_embed(self):
        embed = discord.Embed(
            title="🖥 Панель разработчика",
            description="Управление ботом (только в личных сообщениях)",
            color=0x2F3136
        )
        embed.add_field(name="🌐 Серверы", value="Список серверов", inline=True)
        embed.add_field(name="📩 Инвайты", value="Инвайты", inline=True)
        embed.add_field(name="🔄 Перезагрузить", value="Перезагрузка cog", inline=True)
        embed.add_field(name="🚪 Выйти", value="Выход с сервера", inline=True)
        embed.add_field(name="⚙️ Инфо бота", value="Информация о боте", inline=True)
        embed.add_field(name="⛔ Выключить", value="Выключить бота", inline=True)
        return embed

    def get_servers(self):
        lines = []
        for g in self.bot.guilds:
            lines.append(f"• {g.name} | ID: `{g.id}` | 👥 {g.member_count}")
        return "\n".join(lines) or "Бот не на серверах."

    async def get_invites(self):
        lines = []
        for g in self.bot.guilds:
            link = "❌ Нет доступа"
            if g.me is not None:
                for ch in g.text_channels:
                    try:
                        if ch.permissions_for(g.me).create_instant_invite:
                            invite = await ch.create_invite(max_age=3600, max_uses=1)
                            link = invite.url
                            break
                    except discord.HTTPException:
                        continue
            lines.append(f"**{g.name}**\n{link}")
        return "\n\n".join(lines) or "Нет серверов."

    def bot_info(self):
        return (
            f"🤖 **{self.bot.user}**\n"
            f"ID: `{self.bot.user.id}`\n"
            f"Servers: {len(self.bot.guilds)}\n"
            f"Latency: {round(self.bot.latency * 1000)} ms"
        )


# ========= BUTTONS =========

class DevPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🌐 Серверы", style=discord.ButtonStyle.primary)
    async def servers(self, interaction: discord.Interaction, _):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Доступ запрещён.", ephemeral=True)

        text = "\n".join(f"{g.name} ({g.id})" for g in self.bot.guilds) or "Нет серверов."
        await interaction.response.send_message(chunk_text(text)[0], ephemeral=True)

    @discord.ui.button(label="⛔ Выключить", style=discord.ButtonStyle.danger)
    async def shutdown(self, interaction: discord.Interaction, _):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Доступ запрещён.", ephemeral=True)

        await interaction.response.send_message("⛔ Бот выключается...", ephemeral=True)
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(DevPanel(bot))
