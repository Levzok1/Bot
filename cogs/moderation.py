import os
import random
from typing import Optional, Set

import discord
from discord import app_commands
from discord.ext import commands

from .guild_settings import get_guild_setting
from .modlog import log_mod_action, get_guild_actions, get_user_actions


def _parse_ids(raw: str) -> Set[int]:
    return {int(item) for item in raw.split(",") if item.strip().isdigit()}


def _parse_names(raw: str) -> Set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


ALLOWED_MOD_IDS = _parse_ids(os.getenv("MODERATOR_IDS", ""))
ALLOWED_MOD_ROLE_NAMES = _parse_names(os.getenv("MODERATOR_ROLE_NAMES", ""))


async def _allowed_roles(interaction: discord.Interaction) -> Set[str]:
    if interaction.guild is None:
        return set()

    guild_roles = await get_guild_setting(interaction.guild.id, "moderator_role_names")
    return ALLOWED_MOD_ROLE_NAMES | (_parse_names(guild_roles) if isinstance(guild_roles, str) else set())


async def _is_mod(interaction: discord.Interaction) -> bool:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.guild_permissions.administrator or interaction.user.id in ALLOWED_MOD_IDS:
        return True

    allowed_roles = await _allowed_roles(interaction)
    return any(role.name in allowed_roles for role in interaction.user.roles)


super_mod = app_commands.check(_is_mod)


def _valid_target(interaction: discord.Interaction, member: discord.Member) -> bool:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False

    return (
        member != interaction.user
        and member.id != interaction.guild.owner_id
        and (interaction.user.id == interaction.guild.owner_id or member.top_role < interaction.user.top_role)
    )


async def _send_ephemeral(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def _safe_dm(member: discord.Member, text: str) -> None:
    try:
        await member.send(text)
    except discord.HTTPException:
        pass


async def _member_action(
    interaction: discord.Interaction,
    member: discord.Member,
    action: str,
    reason: Optional[str] = None,
    delete_days: int = 0,
) -> str:
    guild = interaction.guild
    if guild is None or guild.me is None:
        return "guild"

    if member == interaction.user:
        return "self"
    if not _valid_target(interaction, member):
        return "hierarchy"
    if member.top_role >= guild.me.top_role:
        return "bot_hierarchy"

    try:
        if action == "kick":
            if not guild.me.guild_permissions.kick_members:
                return "noperm"
            await _safe_dm(member, f"Ты был кикнут с сервера {guild.name}. Причина: {reason or 'не указана'}.")
            await member.kick(reason=f"{reason or 'Без причины'} (модератор: {interaction.user})")
        else:
            if not guild.me.guild_permissions.ban_members:
                return "noperm"
            await _safe_dm(member, f"Ты был забанен на сервере {guild.name}. Причина: {reason or 'не указана'}.")
            await guild.ban(
                member,
                reason=f"{reason or 'Без причины'} (модератор: {interaction.user})",
                delete_message_seconds=delete_days * 86400,
            )
    except discord.Forbidden:
        return "bot_hierarchy"
    except discord.HTTPException:
        return "http_error"

    await log_mod_action(
        guild.id,
        member.id,
        action,
        interaction.user.id,
        reason=reason or "Без причины",
        extra={"delete_messages_days": delete_days} if action != "kick" else {"member_id": member.id},
    )
    return "ok"


ACTION_WORDS = {"kick": ("кикнуть", "кикать", "кикнут"), "ban": ("забанить", "банить", "забанен")}
SKIP_LABELS = {
    "self": "сам себя",
    "hierarchy": "роль не ниже твоей",
    "bot_hierarchy": "моя роль ниже",
    "noperm": "нет прав у бота",
}


def _action_error_message(action: str, result: str) -> str:
    verb, perm_verb, _ = ACTION_WORDS[action]
    return {
        "self": f"Нельзя {verb} самого себя.",
        "hierarchy": f"Нельзя {verb} участника с ролью не ниже твоей.",
        "noperm": f"У меня нет права {perm_verb} участников.",
        "bot_hierarchy": "Моя роль должна быть выше роли этого участника.",
        "http_error": f"Не удалось {verb} участника. Попробуйте позже.",
    }.get(result, "Не удалось выполнить команду на этом сервере.")


async def _send_member_action_result(
    interaction: discord.Interaction,
    member: discord.Member,
    action: str,
    reason: Optional[str],
    delete_days: int = 0,
) -> None:
    result = await _member_action(interaction, member, action, reason, delete_days)
    if result == "ok":
        await interaction.response.send_message(
            f"Участник {member.mention} был {ACTION_WORDS[action][2]}. Причина: {reason or 'не указана'}.",
            ephemeral=False,
        )
        return

    await interaction.response.send_message(_action_error_message(action, result), ephemeral=True)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CheckFailure):
            await _send_ephemeral(interaction, "У тебя нет прав использовать эту команду.")
            return
        raise error

    @super_mod
    @app_commands.command(name="clear", description="Удалить сообщения в канале.")
    @app_commands.guild_only()
    @app_commands.describe(amount="Сколько сообщений удалить (1–200)", channel="Канал для очистки")
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 200],
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        channel = channel or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("Эту команду можно использовать только в текстовом канале.", ephemeral=True)

        if interaction.guild is None or interaction.guild.me is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.manage_messages or not permissions.read_message_history:
            return await interaction.response.send_message("У меня нет прав удалять сообщения в этом канале.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await channel.purge(limit=amount)
        except discord.HTTPException:
            return await interaction.followup.send("Не удалось удалить сообщения. Попробуйте позже.", ephemeral=True)

        await log_mod_action(
            interaction.guild.id,
            None,
            "clear",
            interaction.user.id,
            reason=f"Удалено {len(deleted)} сообщений в #{channel.name}",
            extra={"channel_id": channel.id, "deleted": len(deleted)},
        )
        await interaction.followup.send(f"Удалено сообщений: {len(deleted)}.", ephemeral=True)

    @super_mod
    @app_commands.command(name="kick", description="Выгнать участника с сервера.")
    @app_commands.guild_only()
    @app_commands.describe(member="Кого кикнуть", reason="Причина")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await _send_member_action_result(interaction, member, "kick", reason)

    @super_mod
    @app_commands.command(name="ban", description="Забанить участника.")
    @app_commands.guild_only()
    @app_commands.describe(member="Кого забанить", reason="Причина", delete_messages="Сколько дней сообщений удалить (0–7)")
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
        delete_messages: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        await _send_member_action_result(interaction, member, "ban", reason, delete_messages)

    @super_mod
    @app_commands.command(name="randban", description="Рандомно забанить до 10 участников сервера.")
    @app_commands.guild_only()
    @app_commands.describe(count="Сколько человек забанить (1-10)", reason="Причина для бана")
    async def randban(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 10] = 10,
        reason: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None or interaction.guild.me is None or not isinstance(interaction.user, discord.Member):
            return await interaction.followup.send("Эта команда доступна только на сервере.", ephemeral=True)

        if not interaction.guild.me.guild_permissions.ban_members:
            return await interaction.followup.send("У меня нет права банить участников.", ephemeral=True)

        members = [
            m for m in interaction.guild.members
            if not m.bot
            and m != interaction.user
            and m != interaction.guild.owner
            and (interaction.user == interaction.guild.owner or m.top_role < interaction.user.top_role)
        ]
        if not members:
            return await interaction.followup.send("Нет доступных участников для рандомного бана.", ephemeral=True)

        selected = random.sample(members, min(count, len(members)))
        banned, skipped = [], []
        for member in selected:
            result = await _member_action(interaction, member, "randban", reason, 0)
            if result == "ok":
                banned.append(member.mention)
            else:
                skipped.append(member.mention)

        if not banned:
            return await interaction.followup.send("Не удалось забанить ни одного пользователя. Проверьте права и иерархию ролей.", ephemeral=True)
        text = f"Забанены: {', '.join(banned)}"
        if skipped:
            text += f"\nНе удалось забанить: {', '.join(skipped)}"
        await interaction.followup.send(text, ephemeral=True)

    @super_mod
    @app_commands.command(name="mban", description="Забанить сразу до двух участников.")
    @app_commands.guild_only()
    @app_commands.describe(member1="Первый участник", member2="Второй участник (опционально)", reason="Причина", delete_messages="Сколько дней сообщений удалить (0–7)")
    async def mban(
        self,
        interaction: discord.Interaction,
        member1: discord.Member,
        member2: Optional[discord.Member] = None,
        reason: Optional[str] = None,
        delete_messages: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        if interaction.guild is None or interaction.guild.me is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        if not interaction.guild.me.guild_permissions.ban_members:
            return await interaction.response.send_message("У меня нет права банить участников.", ephemeral=True)

        members = [member1] + ([member2] if member2 is not None and member2 != member1 else [])
        banned, skipped = [], []
        for member in members:
            result = await _member_action(interaction, member, "ban", reason, delete_messages)
            if result == "ok":
                banned.append(member.mention)
            else:
                skipped.append(f"{member.mention} ({SKIP_LABELS.get(result, 'ошибка при бане')})")

        text = []
        if banned:
            text.append("Забанены: " + ", ".join(banned))
        if skipped:
            text.append("Пропущены: " + ", ".join(skipped))
        text.append(f"Причина: {reason or 'не указана'}.")
        await interaction.response.send_message("\n".join(text), ephemeral=False)

    @super_mod
    @app_commands.command(name="unban", description="Разбанить пользователя.")
    @app_commands.guild_only()
    @app_commands.describe(user="Пользователь для разбана", reason="Причина")
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None or interaction.guild.me is None:
            return await interaction.followup.send("Эта команда доступна только на сервере.", ephemeral=True)
        if not interaction.guild.me.guild_permissions.ban_members:
            return await interaction.followup.send("У меня нет права разбанивать пользователей.", ephemeral=True)

        try:
            await interaction.guild.fetch_ban(user)
        except discord.NotFound:
            return await interaction.followup.send("Этот пользователь не найден в списке банов.", ephemeral=True)
        except discord.HTTPException:
            return await interaction.followup.send("Ошибка при проверке списка банов. Попробуйте позже.", ephemeral=True)

        await interaction.guild.unban(user, reason=f"{reason or 'Без причины'} (модератор: {interaction.user})")
        await log_mod_action(interaction.guild.id, user.id, "unban", interaction.user.id, reason=reason or "Без причины")
        await interaction.followup.send(f"Пользователь {user.mention} был разбанен. Причина: {reason or 'не указана'}.", ephemeral=True)

    @super_mod
    @app_commands.command(name="modlog", description="Показать журнал модерации для сервера или участника.")
    @app_commands.guild_only()
    @app_commands.describe(user="Пользователь для просмотра истории (опционально)")
    async def modlog(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        if interaction.guild is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        if user is None:
            actions = await get_guild_actions(interaction.guild.id)
            if not actions:
                return await interaction.response.send_message("Журнал модерации пуст.", ephemeral=True)
            lines = []
            for target_id, entries in actions.items():
                for entry in entries[-5:]:
                    target = "Действие канала" if target_id == "0" else f"Пользователь <@{target_id}>"
                    lines.append(f"{entry['timestamp']}: {target} — {entry['action']} ({entry.get('reason') or 'без причины'})")
            return await interaction.response.send_message("\n".join(lines[-10:]), ephemeral=True)

        entries = await get_user_actions(interaction.guild.id, user.id)
        if not entries:
            return await interaction.response.send_message("У этого пользователя нет записей в журнале.", ephemeral=True)
        await interaction.response.send_message("\n".join(f"{entry['timestamp']}: {entry['action']} — {entry.get('reason') or 'без причины'}" for entry in entries[-10:]), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
