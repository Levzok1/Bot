import asyncio
import queue
import shlex
import threading
import traceback
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .antimat import format_words, load_words, parse_words, save_words
from .guild_settings import delete_guild_setting, get_guild_settings, set_guild_setting
from .modlog import get_guild_actions, get_user_actions, log_mod_action
from .warnings import clear_member_warnings, get_member_warnings, warn_member


def _parse_id(value: str) -> Optional[int]:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 15:
        return None
    return int(digits)


def _split_command(line: str) -> tuple[str, str]:
    line = line.strip()
    if line.startswith("/"):
        line = line[1:]
    command, _, rest = line.partition(" ")
    return command.casefold(), rest.strip()


def _split_args(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _bool_value(value: str) -> bool:
    return value.strip().casefold() not in {"0", "false", "off", "no", "нет", "выкл", "disable", "disabled"}


class Console(commands.Cog):
    """Local terminal control for the bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.task: Optional[asyncio.Task] = None
        self.input_queue: queue.Queue[Optional[str]] = queue.Queue()
        self.stop_event = threading.Event()
        self.input_thread: Optional[threading.Thread] = None

    async def cog_load(self) -> None:
        self.input_thread = threading.Thread(target=self._read_console_input, name="BotConsoleInput", daemon=True)
        self.input_thread.start()
        self.task = asyncio.create_task(self._console_loop())

    def cog_unload(self) -> None:
        self.stop_event.set()
        if self.task and not self.task.done():
            self.task.cancel()

    def _read_console_input(self) -> None:
        while not self.stop_event.is_set():
            try:
                line = input("bot> ")
            except (EOFError, KeyboardInterrupt):
                self.input_queue.put(None)
                return
            self.input_queue.put(line)

    async def _console_loop(self) -> None:
        await self.bot.wait_until_ready()
        print("[Console] Готово. Введи `help`, чтобы увидеть команды консоли.")

        while not self.bot.is_closed():
            try:
                line = self.input_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            except asyncio.CancelledError:
                return

            if line is None:
                print("[Console] Ввод закрыт.")
                return

            line = line.strip()
            if not line:
                continue

            try:
                result = await self.execute(line)
                if result:
                    print(result)
            except Exception as e:
                print(f"[Console] Ошибка: {e}")
                traceback.print_exc()

    async def execute(self, line: str) -> str:
        command, rest = _split_command(line)

        if command in {"help", "?"}:
            return self.help_text()
        if command == "servers":
            return self.servers_text()
        if command == "channels":
            return self.channels_text(rest)
        if command == "roles":
            return self.roles_text(rest)
        if command == "commands":
            return self.commands_text()
        if command == "say":
            return await self.say(rest)
        if command == "embed":
            return await self.send_embed(rest)
        if command == "clear":
            return await self.clear(rest)
        if command == "kick":
            return await self.kick(rest)
        if command == "ban":
            return await self.ban(rest)
        if command == "unban":
            return await self.unban(rest)
        if command == "warn":
            return await self.warn(rest)
        if command in {"warnings", "warns"}:
            return await self.warnings(rest)
        if command in {"clearwarns", "unwarn"}:
            return await self.clearwarns(rest)
        if command == "modlog":
            return await self.modlog(rest)
        if command == "sync":
            synced = await self.bot.tree.sync()
            return f"Slash-команды синхронизированы: {len(synced)}"
        if command == "shutdown":
            await self.bot.close()
            return "Бот выключается."

        if command in {"rr", "reactionrole", "reactionroles"}:
            return await self.reaction_roles(rest)
        if command == "config":
            return await self.config(rest)
        if command in {"addword", "delword", "words"}:
            return self.words(command, rest)

        if command in {"menu", "join", "leave", "play", "skip", "stop", "queue", "shuffle", "jump", "now", "lyrics"}:
            return await self.music(command, rest)

        return f"Неизвестная команда консоли: {command}. Введи `help`."

    def help_text(self) -> str:
        return (
            "Команды консоли:\n"
            "  servers\n"
            "  channels <guild_id>\n"
            "  roles <guild_id>\n"
            "  commands\n"
            "  say <channel_id> <text>\n"
            "  embed <channel_id> | <title> | <description>\n"
            "  clear <channel_id> <amount>\n"
            "  kick <guild_id> <member_id> [reason]\n"
            "  ban <guild_id> <member_id> [reason]\n"
            "  unban <guild_id> <user_id> [reason]\n"
            "  warn <guild_id> <member_id> [reason]\n"
            "  warnings <guild_id> <member_id>\n"
            "  clearwarns|unwarn <guild_id> <member_id> [reason]\n"
            "  modlog <guild_id> [user_id]\n"
            "  menu <text_channel_id>\n"
            "  join <voice_channel_id>\n"
            "  play <voice_channel_id> <query>\n"
            "  skip|stop|leave|queue|shuffle|now <guild_id>\n"
            "  jump <guild_id> <position>\n"
            "  lyrics <guild_id> off | lyrics <guild_id> <text_channel_id>\n"
            "  rr create <channel_id> | <title> | <description> | <emoji>=<role_id>; <emoji>=<role_id>\n"
            "  rr add <channel_id> <message_id> <emoji> <role_id_or_name>\n"
            "  rr remove <guild_id> <message_id> <emoji>\n"
            "  rr list <guild_id>\n"
            "  config view|set|delete ...\n"
            "  addword <word, word>, delword <word, word>, words\n"
            "  sync\n"
            "  shutdown"
        )

    def servers_text(self) -> str:
        if not self.bot.guilds:
            return "Бот не находится на серверах."
        return "\n".join(
            f"{guild.name} | ID: {guild.id} | Участников: {guild.member_count}"
            for guild in self.bot.guilds
        )

    def channels_text(self, rest: str) -> str:
        guild_id = _parse_id(rest)
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if not guild:
            return "Сервер не найден."

        text_channels = "\n".join(f"  #{channel.name}: {channel.id}" for channel in guild.text_channels) or "  нет"
        voice_channels = "\n".join(f"  {channel.name}: {channel.id}" for channel in guild.voice_channels) or "  нет"
        return f"Текстовые каналы:\n{text_channels}\nГолосовые каналы:\n{voice_channels}"

    def roles_text(self, rest: str) -> str:
        guild_id = _parse_id(rest)
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if not guild:
            return "Сервер не найден."

        roles = [role for role in sorted(guild.roles, key=lambda item: item.position, reverse=True) if not role.is_default()]
        return "\n".join(f"{role.name}: {role.id}" for role in roles) or "Ролей нет."

    def commands_text(self) -> str:
        def walk(command: app_commands.Command | app_commands.Group, prefix: str = "") -> list[str]:
            name = f"{prefix}{command.name}"
            if isinstance(command, app_commands.Group):
                lines: list[str] = []
                for child in command.commands:
                    lines.extend(walk(child, f"{name} "))
                return lines
            return [f"/{name}"]

        lines: list[str] = []
        for command in self.bot.tree.get_commands():
            lines.extend(walk(command))
        return "\n".join(sorted(lines)) or "Slash-команды не найдены."

    def _guild_and_id(self, args: list[str], entity: str) -> tuple[Optional[discord.Guild], Optional[int], Optional[str]]:
        if len(args) < 2:
            return None, None, None
        guild_id = _parse_id(args[0])
        entity_id = _parse_id(args[1])
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if not guild or not entity_id:
            return None, None, f"Сервер или {entity} не найден."
        return guild, entity_id, None

    async def _fetch_member(self, guild: discord.Guild, member_id: int) -> Optional[discord.Member]:
        try:
            return guild.get_member(member_id) or await guild.fetch_member(member_id)
        except discord.HTTPException:
            return None

    async def say(self, rest: str) -> str:
        channel_raw, _, text = rest.partition(" ")
        channel_id = _parse_id(channel_raw)
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return "Текстовый канал не найден."
        if not text.strip():
            return "Текст сообщения пустой."

        message = await channel.send(text.strip(), allowed_mentions=discord.AllowedMentions.none())
        return f"Сообщение отправлено: {message.jump_url}"

    async def send_embed(self, rest: str) -> str:
        parts = [part.strip() for part in rest.split("|", 2)]
        if len(parts) != 3:
            return "Формат: embed <channel_id> | <title> | <description>"

        channel_id = _parse_id(parts[0])
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return "Текстовый канал не найден."

        embed = discord.Embed(title=parts[1], description=parts[2], color=discord.Color.blurple())
        message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return f"Embed отправлен: {message.jump_url}"

    async def clear(self, rest: str) -> str:
        args = _split_args(rest)
        if len(args) < 2:
            return "Формат: clear <channel_id> <amount>"

        channel_id = _parse_id(args[0])
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return "Текстовый канал не найден."

        try:
            amount = max(1, min(200, int(args[1])))
        except ValueError:
            return "amount должен быть числом от 1 до 200."

        deleted = await channel.purge(limit=amount)
        await log_mod_action(
            channel.guild.id,
            None,
            "clear",
            self._console_actor_id(),
            reason=f"Консоль: удалено {len(deleted)} сообщений в #{channel.name}",
            extra={"channel_id": channel.id, "deleted": len(deleted)},
        )
        return f"Удалено сообщений: {len(deleted)}"

    async def kick(self, rest: str) -> str:
        args = rest.split(maxsplit=2)
        if len(args) < 2:
            return "Формат: kick <guild_id> <member_id> [reason]"

        guild, member_id, error = self._guild_and_id(args, "участник")
        if error:
            return error
        member = await self._fetch_member(guild, member_id)
        if not member:
            return "Участник не найден."

        reason = args[2] if len(args) > 2 else "Команда из консоли"
        if guild.me is None or member.top_role >= guild.me.top_role:
            return "Роль бота должна быть выше роли участника."
        await member.kick(reason=reason)
        await log_mod_action(guild.id, member.id, "kick", self._console_actor_id(), reason=reason)
        return f"Участник {member} кикнут."

    async def ban(self, rest: str) -> str:
        args = rest.split(maxsplit=2)
        if len(args) < 2:
            return "Формат: ban <guild_id> <member_id> [reason]"

        guild, user_id, error = self._guild_and_id(args, "пользователь")
        if error:
            return error

        reason = args[2] if len(args) > 2 else "Команда из консоли"
        member = guild.get_member(user_id)
        if member and guild.me is not None and member.top_role >= guild.me.top_role:
            return "Роль бота должна быть выше роли участника."

        await guild.ban(discord.Object(id=user_id), reason=reason)
        await log_mod_action(guild.id, user_id, "ban", self._console_actor_id(), reason=reason)
        return f"Пользователь {user_id} забанен."

    async def unban(self, rest: str) -> str:
        args = rest.split(maxsplit=2)
        if len(args) < 2:
            return "Формат: unban <guild_id> <user_id> [reason]"

        guild, user_id, error = self._guild_and_id(args, "пользователь")
        if error:
            return error

        reason = args[2] if len(args) > 2 else "Команда из консоли"
        await guild.unban(discord.Object(id=user_id), reason=reason)
        await log_mod_action(guild.id, user_id, "unban", self._console_actor_id(), reason=reason)
        return f"Пользователь {user_id} разбанен."

    async def warn(self, rest: str) -> str:
        args = rest.split(maxsplit=2)
        if len(args) < 2:
            return "Формат: warn <guild_id> <member_id> [reason]"

        guild, member_id, error = self._guild_and_id(args, "участник")
        if error:
            return error
        member = await self._fetch_member(guild, member_id)
        if not member:
            return "Участник не найден."
        if member == guild.me or member == guild.owner:
            return "Нельзя выдать warn этому участнику."

        reason = args[2] if len(args) > 2 else "Команда из консоли"
        result = await warn_member(guild, member, self._console_actor_id(), reason)
        return (
            f"Warn выдан {member}. Активных варнов: {result['activeCount']}. "
            f"{result['punishment']}"
        )

    async def warnings(self, rest: str) -> str:
        args = _split_args(rest)
        if len(args) < 2:
            return "Формат: warnings <guild_id> <member_id>"

        guild, member_id, error = self._guild_and_id(args, "участник")
        if error:
            return error

        records = await get_member_warnings(guild.id, member_id, active_only=True)
        if not records:
            return f"У <@{member_id}> нет активных варнов."

        lines = [f"Активные варны <@{member_id}>: {len(records)}"]
        for index, record in enumerate(records[-10:], start=1):
            reason = record.get("reason") or "Без причины"
            expires = record.get("expires_at") or "без срока"
            lines.append(f"{index}. {reason} | до {expires}")
        return "\n".join(lines)

    async def clearwarns(self, rest: str) -> str:
        args = rest.split(maxsplit=2)
        if len(args) < 2:
            return "Формат: clearwarns <guild_id> <member_id> [reason]"

        guild, member_id, error = self._guild_and_id(args, "участник")
        if error:
            return error

        reason = args[2] if len(args) > 2 else "Снято через консоль"
        removed = await clear_member_warnings(guild.id, member_id, self._console_actor_id(), reason)
        await log_mod_action(
            guild.id,
            member_id,
            "clearwarns",
            self._console_actor_id(),
            reason=reason,
            extra={"removed": removed},
        )
        return f"Снято активных варнов: {removed}."

    async def modlog(self, rest: str) -> str:
        args = _split_args(rest)
        if not args:
            return "Формат: modlog <guild_id> [user_id]"

        guild_id = _parse_id(args[0])
        user_id = _parse_id(args[1]) if len(args) > 1 else None
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if not guild:
            return "Сервер не найден."

        if user_id:
            entries = await get_user_actions(guild.id, user_id)
            return self._format_modlog_entries(entries, str(user_id))

        actions = await get_guild_actions(guild.id)
        rows = []
        for target_id, entries in actions.items():
            for entry in entries:
                rows.append((target_id, entry))
        rows.sort(key=lambda item: item[1].get("timestamp", ""))
        rows = rows[-20:]
        if not rows:
            return "Журнал модерации пуст."
        return "\n".join(self._format_modlog_entry(entry, target_id) for target_id, entry in rows)

    def _console_actor_id(self) -> int:
        return self.bot.user.id if self.bot.user else 0

    def _format_modlog_entries(self, entries: list[dict], target_id: str) -> str:
        if not entries:
            return "Журнал модерации пуст."
        return "\n".join(self._format_modlog_entry(entry, target_id) for entry in entries[-20:])

    def _format_modlog_entry(self, entry: dict, target_id: str) -> str:
        target = "канал/сервер" if target_id == "0" else f"<@{target_id}>"
        reason = entry.get("reason") or "без причины"
        return f"{entry.get('timestamp')}: {entry.get('action')} | цель: {target} | {reason}"

    async def music(self, command: str, rest: str) -> str:
        music_cog = self.bot.get_cog("Music")
        if music_cog is None:
            return "Music cog не загружен."

        if command == "menu":
            channel_id = _parse_id(rest)
            return await music_cog.console_send_menu(channel_id) if channel_id else "Формат: menu <text_channel_id>"
        if command == "join":
            channel_id = _parse_id(rest)
            return await music_cog.console_join(channel_id) if channel_id else "Формат: join <voice_channel_id>"
        if command == "play":
            channel_raw, _, query = rest.partition(" ")
            channel_id = _parse_id(channel_raw)
            if not channel_id or not query.strip():
                return "Формат: play <voice_channel_id> <query>"
            return await music_cog.console_play(channel_id, query.strip())

        args = _split_args(rest)
        if not args:
            return f"Формат: {command} <guild_id>"
        guild_id = _parse_id(args[0])
        if not guild_id:
            return "guild_id указан неверно."

        if command == "leave":
            return await music_cog.console_leave(guild_id)
        if command == "skip":
            return await music_cog.console_skip(guild_id)
        if command == "stop":
            return await music_cog.console_stop(guild_id)
        if command == "queue":
            return music_cog.console_queue_text(guild_id)
        if command == "shuffle":
            return music_cog.console_shuffle(guild_id)
        if command == "now":
            return music_cog.console_now_text(guild_id)
        if command == "jump":
            if len(args) < 2:
                return "Формат: jump <guild_id> <position>"
            try:
                position = int(args[1])
            except ValueError:
                return "position должен быть числом."
            return await music_cog.console_jump(guild_id, position)
        if command == "lyrics":
            if len(args) < 2:
                return "Формат: lyrics <guild_id> off | lyrics <guild_id> <text_channel_id>"
            if args[1].casefold() in {"off", "false", "0", "выкл"}:
                return await music_cog.console_lyrics(guild_id, 0, False)
            channel_id = _parse_id(args[1])
            return await music_cog.console_lyrics(guild_id, channel_id, True) if channel_id else "text_channel_id указан неверно."

        return "Неизвестная music-команда."

    async def reaction_roles(self, rest: str) -> str:
        rr_cog = self.bot.get_cog("ReactionRoles")
        if rr_cog is None:
            return "ReactionRoles cog не загружен."

        subcommand, args = _split_command(rest)
        if subcommand == "create":
            parts = [part.strip() for part in args.split("|", 3)]
            if len(parts) != 4:
                return "Формат: rr create <channel_id> | <title> | <description> | <emoji>=<role_id>; ..."
            channel_id = _parse_id(parts[0])
            if not channel_id:
                return "channel_id указан неверно."
            return await rr_cog.console_create(channel_id, parts[1], parts[2], parts[3])

        if subcommand == "add":
            parts = args.split(maxsplit=3)
            if len(parts) != 4:
                return "Формат: rr add <channel_id> <message_id> <emoji> <role_id_or_name>"
            channel_id = _parse_id(parts[0])
            message_id = _parse_id(parts[1])
            if not channel_id or not message_id:
                return "channel_id или message_id указан неверно."
            return await rr_cog.console_add(channel_id, message_id, parts[2], parts[3])

        if subcommand == "remove":
            parts = args.split(maxsplit=2)
            if len(parts) != 3:
                return "Формат: rr remove <guild_id> <message_id> <emoji>"
            guild_id = _parse_id(parts[0])
            message_id = _parse_id(parts[1])
            if not guild_id or not message_id:
                return "guild_id или message_id указан неверно."
            return await rr_cog.console_remove(guild_id, message_id, parts[2])

        if subcommand == "list":
            guild_id = _parse_id(args)
            return await rr_cog.console_list(guild_id) if guild_id else "Формат: rr list <guild_id>"

        return "Формат: rr create|add|remove|list ..."

    async def config(self, rest: str) -> str:
        subcommand, args = _split_command(rest)
        parts = args.split(maxsplit=2)
        if subcommand == "view":
            guild_id = _parse_id(args)
            if not guild_id:
                return "Формат: config view <guild_id>"
            settings = await get_guild_settings(guild_id)
            return "\n".join(f"{key}: {value}" for key, value in settings.items()) or "Настройки не заданы."

        if subcommand == "set":
            if len(parts) < 3:
                return "Формат: config set <guild_id> <key> <value>"
            guild_id = _parse_id(parts[0])
            if not guild_id:
                return "guild_id указан неверно."
            value = parts[2]
            if value.casefold() in {"true", "false", "on", "off", "yes", "no", "1", "0", "да", "нет"}:
                value = _bool_value(value)
            await set_guild_setting(guild_id, parts[1], value)
            return f"Настройка {parts[1]} установлена."

        if subcommand == "delete":
            if len(parts) < 2:
                return "Формат: config delete <guild_id> <key>"
            guild_id = _parse_id(parts[0])
            if not guild_id:
                return "guild_id указан неверно."
            await delete_guild_setting(guild_id, parts[1])
            return f"Настройка {parts[1]} удалена."

        return "Формат: config view|set|delete ..."

    def words(self, command: str, rest: str) -> str:
        words = load_words()

        if command == "words":
            return "📃 Запрещённые слова:\n" + format_words(words) if words else "Список пуст."

        parsed = parse_words(rest)
        if not parsed:
            return "Список слов пустой."

        existing = set(words)
        if command == "addword":
            added = [word for word in parsed if word not in existing]
            if added:
                words.extend(added)
                save_words(words)
            return f"Добавлено: {len(added)}"

        removed_set = {word for word in parsed if word in existing}
        if removed_set:
            save_words([word for word in words if word not in removed_set])
        return f"Удалено: {len(removed_set)}"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Console(bot))
