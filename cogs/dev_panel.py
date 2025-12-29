import os
import discord
from discord.ext import commands
from discord import app_commands

OWNER_ID = int(os.getenv("DISCORD_OWNER_ID", "0"))


def owner_only(interaction: discord.Interaction):
    return interaction.user.id == OWNER_ID


class DevPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========= SLASH =========

    @app_commands.command(name="dev", description="Developer commands")
    @app_commands.describe(action="panel / servers / invites / shutdown / botinfo")
    async def dev(self, interaction: discord.Interaction, action: str):
        if not owner_only(interaction):
            return await interaction.response.send_message(
                "❌ Access denied.", ephemeral=True
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
            await interaction.response.send_message(
                self.get_servers(),
                ephemeral=True
            )

        elif action == "invites":
            await interaction.response.send_message(
                await self.get_invites(),
                ephemeral=True
            )

        elif action == "botinfo":
            await interaction.response.send_message(
                self.bot_info(),
                ephemeral=True
            )

        elif action == "shutdown":
            await interaction.response.send_message("⛔ Bot shutting down...", ephemeral=True)
            await self.bot.close()

        else:
            await interaction.response.send_message(
                "❌ Unknown action.",
                ephemeral=True
            )

    # ========= HELPERS =========

    def panel_embed(self):
        embed = discord.Embed(
            title="🖥 Developer Control Panel",
            description="Управление ботом (DM only)",
            color=0x2F3136
        )
        embed.add_field(name="🌐 Servers", value="Список серверов", inline=True)
        embed.add_field(name="📩 Invites", value="Инвайты", inline=True)
        embed.add_field(name="🔄 Reload", value="Перезагрузка cog", inline=True)
        embed.add_field(name="🚪 Leave", value="Выход с сервера", inline=True)
        embed.add_field(name="⚙️ Bot Info", value="Информация о боте", inline=True)
        embed.add_field(name="⛔ Shutdown", value="Выключить бота", inline=True)
        return embed

    def get_servers(self):
        lines = []
        for g in self.bot.guilds:
            lines.append(f"• {g.name} | ID: `{g.id}` | 👥 {g.member_count}")
        return "\n".join(lines) or "Бот не на серверах."

    async def get_invites(self):
        text = ""
        for g in self.bot.guilds:
            link = "❌ No access"
            for ch in g.text_channels:
                if ch.permissions_for(g.me).create_instant_invite:
                    invite = await ch.create_invite(max_age=3600, max_uses=1)
                    link = invite.url
                    break
            text += f"\n**{g.name}**\n{link}\n"
        return text or "Нет серверов."

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

    @discord.ui.button(label="🌐 Servers", style=discord.ButtonStyle.primary)
    async def servers(self, interaction: discord.Interaction, _):
        await interaction.response.send_message(
            "\n".join(f"{g.name} ({g.id})" for g in self.bot.guilds),
            ephemeral=True
        )

    @discord.ui.button(label="⛔ Shutdown", style=discord.ButtonStyle.danger)
    async def shutdown(self, interaction: discord.Interaction, _):
        await interaction.response.send_message("⛔ Bot shutting down...", ephemeral=True)
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(DevPanel(bot))
