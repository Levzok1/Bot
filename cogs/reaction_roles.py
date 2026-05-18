import asyncio
import contextlib
import re
from pathlib import Path
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .json_store import load_json, save_json


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "reaction_roles.json"
ROLE_MENTION_RE = re.compile(r"<@&(?P<id>\d+)>")
SNOWFLAKE_RE = re.compile(r"\d{15,25}")
MAPPING_SPLIT_RE = re.compile(r"[;\n]+")


def _load_all() -> Dict[str, Dict[str, Any]]:
    return load_json(DATA_FILE, {})


def _save_all(data: Dict[str, Dict[str, Any]]) -> None:
    save_json(DATA_FILE, data)


def _parse_id(value: str) -> Optional[int]:
    match = SNOWFLAKE_RE.search(value)
    return int(match.group(0)) if match else None


def _emoji_key(emoji: object) -> str:
    value = str(emoji).strip()
    if value.startswith("<") and value.endswith(">"):
        return value
    return value.replace("\ufe0f", "")


def _mapping_display(mapping: Any, fallback: str) -> str:
    if isinstance(mapping, dict):
        return str(mapping.get("emoji") or fallback)
    return fallback


class ReactionRoles(commands.Cog):
    """Carl-bot style roles by reactions."""

    reactionroles = app_commands.Group(
        name="reactionroles",
        description="Роли по реакциям",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()

    async def _require_manager(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await self._reply(interaction, "Эта команда доступна только на сервере.", ephemeral=True)
            return False

        perms = interaction.user.guild_permissions
        if perms.administrator or perms.manage_roles or perms.manage_guild:
            return True

        await self._reply(interaction, "У тебя нет прав управлять ролями.", ephemeral=True)
        return False

    async def _reply(self, interaction: discord.Interaction, message: str, *, ephemeral: bool = True) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(message, ephemeral=ephemeral)

    def _resolve_role(self, guild: discord.Guild, value: str) -> Optional[discord.Role]:
        value = value.strip()
        if not value:
            return None

        match = ROLE_MENTION_RE.fullmatch(value)
        role_id = int(match.group("id")) if match else _parse_id(value)
        if role_id:
            return guild.get_role(role_id)

        role_name = value[1:].strip() if value.startswith("@") else value
        lowered = role_name.casefold()
        return next((role for role in guild.roles if role.name.casefold() == lowered), None)

    def _role_problem(self, guild: discord.Guild, role: discord.Role) -> Optional[str]:
        me = guild.me
        if me is None:
            return "Не удалось определить роль бота на сервере."
        if not me.guild_permissions.manage_roles:
            return "У бота нет права Manage Roles."
        if role.is_default():
            return "Нельзя выдавать роль @everyone."
        if role.managed:
            return f"Роль {role.mention} управляется интеграцией, её нельзя выдавать."
        if role >= me.top_role:
            return f"Роль {role.mention} должна быть ниже самой высокой роли бота."
        return None

    def _parse_mappings(self, guild: discord.Guild, raw: Optional[str]) -> tuple[Dict[str, Dict[str, Any]], list[str]]:
        if not raw or not raw.strip():
            return {}, []

        mappings: Dict[str, Dict[str, Any]] = {}
        errors: list[str] = []

        for item in MAPPING_SPLIT_RE.split(raw):
            item = item.strip()
            if not item:
                continue

            if "=" in item:
                emoji, role_ref = item.split("=", 1)
            else:
                parts = item.split(maxsplit=1)
                if len(parts) != 2:
                    errors.append(f"`{item}`: используй формат `emoji=роль`.")
                    continue
                emoji, role_ref = parts

            emoji = emoji.strip()
            role_ref = role_ref.strip()
            key = _emoji_key(emoji)
            if not key:
                errors.append(f"`{item}`: emoji не найден.")
                continue
            if key in mappings:
                errors.append(f"`{emoji}`: этот emoji указан дважды.")
                continue

            role = self._resolve_role(guild, role_ref)
            if role is None:
                errors.append(f"`{emoji}`: роль `{role_ref}` не найдена.")
                continue

            problem = self._role_problem(guild, role)
            if problem:
                errors.append(f"`{emoji}`: {problem}")
                continue

            mappings[key] = {"emoji": emoji, "role_id": role.id}

        return mappings, errors

    def _build_embed(self, guild: discord.Guild, record: Dict[str, Any]) -> discord.Embed:
        title = str(record.get("title") or "Выбери роль")
        description = str(record.get("description") or "Нажми на реакцию ниже, чтобы получить роль.")
        mappings = record.get("mappings") if isinstance(record.get("mappings"), dict) else {}

        lines = []
        for key, mapping in mappings.items():
            role_id = int(mapping.get("role_id") if isinstance(mapping, dict) else mapping)
            role = guild.get_role(role_id)
            role_text = role.mention if role else f"`{role_id}`"
            lines.append(f"{_mapping_display(mapping, key)} {role_text}")

        full_description = description.strip()
        if lines:
            full_description = f"{full_description}\n\n" + "\n".join(lines)

        embed = discord.Embed(
            title=title,
            description=full_description,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Нажми реакцию, чтобы получить или снять роль.")
        return embed

    async def _get_record(self, guild_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        async with self.lock:
            data = _load_all()
            records = data.get(str(guild_id), {})
            if not isinstance(records, dict):
                return None
            record = records.get(str(message_id))
            return record.copy() if isinstance(record, dict) else None

    async def _get_guild_records(self, guild_id: int) -> Dict[str, Dict[str, Any]]:
        async with self.lock:
            data = _load_all()
            records = data.get(str(guild_id), {})
            return records.copy() if isinstance(records, dict) else {}

    async def _set_record(self, guild_id: int, message_id: int, record: Dict[str, Any]) -> None:
        async with self.lock:
            data = _load_all()
            guild_records = data.setdefault(str(guild_id), {})
            guild_records[str(message_id)] = record
            _save_all(data)

    async def _delete_record(self, guild_id: int, message_id: int) -> None:
        async with self.lock:
            data = _load_all()
            guild_records = data.get(str(guild_id), {})
            guild_records.pop(str(message_id), None)
            if guild_records:
                data[str(guild_id)] = guild_records
            else:
                data.pop(str(guild_id), None)
            _save_all(data)

    async def _fetch_bot_message(self, channel: discord.TextChannel, message_id: int) -> discord.Message:
        message = await channel.fetch_message(message_id)
        if self.bot.user is None or message.author.id != self.bot.user.id:
            raise ValueError("Сообщение должно быть отправлено этим ботом.")
        return message

    def _record_from_message(self, channel: discord.TextChannel, message: discord.Message) -> Dict[str, Any]:
        embed = message.embeds[0] if message.embeds else None
        return {
            "channel_id": channel.id,
            "message_id": message.id,
            "title": embed.title if embed and embed.title else "Выбери роль",
            "description": embed.description.split("\n\n", 1)[0] if embed and embed.description else "",
            "mappings": {},
        }

    async def _add_reaction_safely(self, message: discord.Message, emoji: str) -> Optional[str]:
        try:
            await message.add_reaction(emoji)
            return None
        except discord.HTTPException as e:
            return f"`{emoji}`: не удалось поставить реакцию ({e})."

    @reactionroles.command(name="create", description="Создать сообщение с ролями по реакциям")
    @app_commands.describe(
        channel="Канал, куда отправить сообщение",
        title="Заголовок сообщения",
        description="Текст сообщения",
        mappings="Формат: emoji=@role; emoji=role_id",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        mappings: Optional[str] = None,
    ) -> None:
        if not await self._require_manager(interaction):
            return
        if interaction.guild is None:
            return
        if channel.guild.id != interaction.guild.id:
            return await self._reply(interaction, "Канал должен быть на этом сервере.")

        me = interaction.guild.me
        if me is None:
            return await self._reply(interaction, "Не удалось определить участника бота на сервере.")
        perms = channel.permissions_for(me)
        if not perms.send_messages or not perms.embed_links or not perms.add_reactions:
            return await self._reply(interaction, "Боту нужны права Send Messages, Embed Links и Add Reactions в этом канале.")

        parsed, errors = self._parse_mappings(interaction.guild, mappings)
        if errors:
            return await self._reply(interaction, "Исправь настройки ролей:\n" + "\n".join(errors[:10]))

        record = {
            "channel_id": channel.id,
            "title": title.strip() or "Выбери роль",
            "description": description.strip(),
            "mappings": parsed,
        }

        await interaction.response.defer(ephemeral=True)
        message = await channel.send(
            embed=self._build_embed(interaction.guild, record),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        record["message_id"] = message.id
        await self._set_record(interaction.guild.id, message.id, record)

        reaction_errors = []
        for mapping in parsed.values():
            error = await self._add_reaction_safely(message, str(mapping["emoji"]))
            if error:
                reaction_errors.append(error)

        suffix = "\n" + "\n".join(reaction_errors) if reaction_errors else ""
        await interaction.followup.send(f"✅ Reaction roles созданы: {message.jump_url}{suffix}", ephemeral=True)

    @reactionroles.command(name="add", description="Добавить emoji -> роль к сообщению reaction roles")
    @app_commands.describe(
        channel="Канал, где находится сообщение",
        message_id="ID сообщения от бота",
        emoji="Emoji для реакции",
        role="Роль, которую выдавать",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        emoji: str,
        role: discord.Role,
    ) -> None:
        if not await self._require_manager(interaction):
            return
        if interaction.guild is None:
            return
        if channel.guild.id != interaction.guild.id:
            return await self._reply(interaction, "Канал должен быть на этом сервере.")

        parsed_message_id = _parse_id(message_id)
        if parsed_message_id is None:
            return await self._reply(interaction, "ID сообщения указан неверно.")

        problem = self._role_problem(interaction.guild, role)
        if problem:
            return await self._reply(interaction, problem)

        await interaction.response.defer(ephemeral=True)
        try:
            message = await self._fetch_bot_message(channel, parsed_message_id)
        except (discord.HTTPException, ValueError) as e:
            return await interaction.followup.send(f"❌ {e}", ephemeral=True)

        record = await self._get_record(interaction.guild.id, message.id)
        if record is None:
            record = self._record_from_message(channel, message)

        key = _emoji_key(emoji)
        mappings = record.setdefault("mappings", {})
        mappings[key] = {"emoji": emoji, "role_id": role.id}
        record["channel_id"] = channel.id
        record["message_id"] = message.id

        error = await self._add_reaction_safely(message, emoji)
        if error:
            return await interaction.followup.send(f"❌ {error}", ephemeral=True)

        await self._set_record(interaction.guild.id, message.id, record)
        await message.edit(embed=self._build_embed(interaction.guild, record), allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(f"✅ Добавлено: {emoji} -> {role.mention}", ephemeral=True)

    @reactionroles.command(name="remove", description="Удалить emoji -> роль из сообщения reaction roles")
    @app_commands.describe(channel="Канал, где находится сообщение", message_id="ID сообщения", emoji="Emoji для удаления")
    async def remove(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        emoji: str,
    ) -> None:
        if not await self._require_manager(interaction):
            return
        if interaction.guild is None:
            return

        parsed_message_id = _parse_id(message_id)
        if parsed_message_id is None:
            return await self._reply(interaction, "ID сообщения указан неверно.")
        if channel.guild.id != interaction.guild.id:
            return await self._reply(interaction, "Канал должен быть на этом сервере.")

        record = await self._get_record(interaction.guild.id, parsed_message_id)
        if record is None:
            return await self._reply(interaction, "Это сообщение не настроено как reaction roles.")

        key = _emoji_key(emoji)
        mappings = record.setdefault("mappings", {})
        if key not in mappings:
            return await self._reply(interaction, "Такого emoji нет в настройках сообщения.")

        await interaction.response.defer(ephemeral=True)
        try:
            message = await self._fetch_bot_message(channel, parsed_message_id)
        except (discord.HTTPException, ValueError) as e:
            return await interaction.followup.send(f"❌ {e}", ephemeral=True)

        display = _mapping_display(mappings[key], key)
        mappings.pop(key, None)
        await self._set_record(interaction.guild.id, parsed_message_id, record)
        await message.edit(embed=self._build_embed(interaction.guild, record), allowed_mentions=discord.AllowedMentions.none())

        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await message.clear_reaction(display)

        await interaction.followup.send(f"✅ Удалено: {display}", ephemeral=True)

    @reactionroles.command(name="list", description="Показать настроенные reaction-role сообщения")
    async def list_messages(self, interaction: discord.Interaction) -> None:
        if not await self._require_manager(interaction):
            return
        if interaction.guild is None:
            return

        records = await self._get_guild_records(interaction.guild.id)
        if not records:
            return await self._reply(interaction, "Reaction roles ещё не настроены.")

        lines = []
        for message_id, record in records.items():
            channel = interaction.guild.get_channel(int(record.get("channel_id", 0)))
            channel_text = channel.mention if channel else f"`{record.get('channel_id')}`"
            mappings = record.get("mappings") if isinstance(record.get("mappings"), dict) else {}
            lines.append(f"`{message_id}` в {channel_text}: {len(mappings)} emoji")

        await self._reply(interaction, "\n".join(lines), ephemeral=True)

    async def console_create(self, channel_id: int, title: str, description: str, mappings: str = "") -> str:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return "Текстовый канал не найден."
        guild = channel.guild
        parsed, errors = self._parse_mappings(guild, mappings)
        if errors:
            return "Ошибки в mappings:\n" + "\n".join(errors[:10])

        record = {
            "channel_id": channel.id,
            "title": title.strip() or "Выбери роль",
            "description": description.strip(),
            "mappings": parsed,
        }
        message = await channel.send(embed=self._build_embed(guild, record), allowed_mentions=discord.AllowedMentions.none())
        record["message_id"] = message.id
        await self._set_record(guild.id, message.id, record)

        errors = []
        for mapping in parsed.values():
            error = await self._add_reaction_safely(message, str(mapping["emoji"]))
            if error:
                errors.append(error)
        return f"Reaction roles созданы: {message.jump_url}" + (("\n" + "\n".join(errors)) if errors else "")

    async def console_add(self, channel_id: int, message_id: int, emoji: str, role_ref: str) -> str:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return "Текстовый канал не найден."
        guild = channel.guild
        role = self._resolve_role(guild, role_ref)
        if role is None:
            return f"Роль `{role_ref}` не найдена."
        problem = self._role_problem(guild, role)
        if problem:
            return problem

        try:
            message = await self._fetch_bot_message(channel, message_id)
        except (discord.HTTPException, ValueError) as e:
            return str(e)

        record = await self._get_record(guild.id, message.id) or self._record_from_message(channel, message)
        key = _emoji_key(emoji)
        record.setdefault("mappings", {})[key] = {"emoji": emoji, "role_id": role.id}
        error = await self._add_reaction_safely(message, emoji)
        if error:
            return error

        await self._set_record(guild.id, message.id, record)
        await message.edit(embed=self._build_embed(guild, record), allowed_mentions=discord.AllowedMentions.none())
        return f"Добавлено: {emoji} -> {role.name}"

    async def console_remove(self, guild_id: int, message_id: int, emoji: str) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return "Сервер не найден."

        record = await self._get_record(guild_id, message_id)
        if record is None:
            return "Это сообщение не настроено как reaction roles."

        key = _emoji_key(emoji)
        mappings = record.setdefault("mappings", {})
        if key not in mappings:
            return "Такого emoji нет в настройках сообщения."

        channel = guild.get_channel(int(record.get("channel_id", 0)))
        if not isinstance(channel, discord.TextChannel):
            return "Канал сообщения не найден."

        try:
            message = await self._fetch_bot_message(channel, message_id)
        except (discord.HTTPException, ValueError) as e:
            return str(e)

        display = _mapping_display(mappings[key], key)
        mappings.pop(key, None)
        await self._set_record(guild_id, message_id, record)
        await message.edit(embed=self._build_embed(guild, record), allowed_mentions=discord.AllowedMentions.none())
        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await message.clear_reaction(display)
        return f"Удалено: {display}"

    async def console_list(self, guild_id: int) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return "Сервер не найден."

        records = await self._get_guild_records(guild_id)
        if not records:
            return "Reaction roles ещё не настроены."

        lines = []
        for message_id, record in records.items():
            channel = guild.get_channel(int(record.get("channel_id", 0)))
            channel_text = f"#{channel.name}" if channel else str(record.get("channel_id"))
            mappings = record.get("mappings") if isinstance(record.get("mappings"), dict) else {}
            lines.append(f"{message_id} в {channel_text}: {len(mappings)} emoji")
        return "\n".join(lines)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == getattr(self.bot.user, "id", None):
            return

        record = await self._get_record(payload.guild_id, payload.message_id)
        if record is None:
            return

        mapping = record.get("mappings", {}).get(_emoji_key(payload.emoji))
        if not mapping:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(int(mapping["role_id"]))
        if role is None:
            return

        member = payload.member
        if member is None:
            with contextlib.suppress(discord.HTTPException):
                member = await guild.fetch_member(payload.user_id)
        if member is None or member.bot or role in member.roles:
            return

        problem = self._role_problem(guild, role)
        if problem:
            print(f"[ReactionRoles] {problem}")
            return

        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await member.add_roles(role, reason=f"Reaction role: {payload.message_id}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == getattr(self.bot.user, "id", None):
            return

        record = await self._get_record(payload.guild_id, payload.message_id)
        if record is None:
            return

        mapping = record.get("mappings", {}).get(_emoji_key(payload.emoji))
        if not mapping:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(int(mapping["role_id"]))
        if role is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            with contextlib.suppress(discord.HTTPException):
                member = await guild.fetch_member(payload.user_id)
        if member is None or member.bot or role not in member.roles:
            return

        with contextlib.suppress(discord.HTTPException, discord.Forbidden):
            await member.remove_roles(role, reason=f"Reaction role removed: {payload.message_id}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReactionRoles(bot))
