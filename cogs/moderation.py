# cogs/moderation.py
import discord
from discord.ext import commands
from discord import app_commands

import os
import json
from datetime import datetime

ACCESS_ROLE_NAME = "Bot Access"  # та же роль, что в access.py

DATA_DIR = "data"
MODLOG_FILE = os.path.join(DATA_DIR, "modlog.json")
LOGCFG_FILE = os.path.join(DATA_DIR, "modlog_channel.json")


# ===== утилиты для файлов =====
def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def load_json(path: str) -> dict:
    ensure_data_dir()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_json(path: str, data: dict):
    ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ===== история наказаний =====
def add_case(
    guild_id: int,
    user_id: int,
    moderator_id: int,
    action: str,
    reason: str | None = None,
    extra: dict | None = None,
):
    data = load_json(MODLOG_FILE)
    g = str(guild_id)
    u = str(user_id)
    if g not in data:
        data[g] = {}
    if u not in data[g]:
        data[g][u] = []
    data[g][u].append(
        {
            "action": action,
            "moderator_id": moderator_id,
            "reason": reason,
            "extra": extra or {},
            "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M"),
        }
    )
    save_json(MODLOG_FILE, data)


def get_history_for_user(guild_id: int, user_id: int) -> list[dict]:
    data = load_json(MODLOG_FILE)
    return data.get(str(guild_id), {}).get(str(user_id), [])


# ===== права доступа =====
def user_has_access(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.name == ACCESS_ROLE_NAME for r in member.roles)


def has_bot_access_prefix(ctx: commands.Context) -> bool:
    return user_has_access(ctx.author)


def has_bot_access_slash(interaction: discord.Interaction) -> bool:
    return user_has_access(interaction.user)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ===== лог-канал =====
    def get_log_channel_id(self, guild_id: int) -> int | None:
        cfg = load_json(LOGCFG_FILE)
        return cfg.get(str(guild_id))

    def set_log_channel_id(self, guild_id: int, channel_id: int):
        cfg = load_json(LOGCFG_FILE)
        cfg[str(guild_id)] = channel_id
        save_json(LOGCFG_FILE, cfg)

    def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        ch_id = self.get_log_channel_id(guild.id)
        if not ch_id:
            return None
        return guild.get_channel(ch_id)

    async def send_log(
        self,
        guild: discord.Guild,
        *,
        title: str,
        description: str,
        user: discord.abc.User | None = None,
        moderator: discord.abc.User | None = None,
        color: discord.Color = discord.Color.orange(),
    ):
        channel = self.get_log_channel(guild)
        if channel is None:
            return
        embed = discord.Embed(title=title, description=description, color=color)
        if user is not None:
            embed.add_field(
                name="Пользователь",
                value=f"{user.mention} ({user.id})",
                inline=False,
            )
        if moderator is not None:
            embed.add_field(
                name="Модератор",
                value=f"{moderator.mention} ({moderator.id})",
                inline=False,
            )
        embed.timestamp = datetime.now()
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    # ===== настройка лог-канала =====
    @commands.command(name="setlog")
    @commands.has_permissions(administrator=True)
    async def setlog_cmd(self, ctx: commands.Context, channel: discord.TextChannel):
        """Установить канал для логов (префикс)."""
        self.set_log_channel_id(ctx.guild.id, channel.id)
        await ctx.send(f"✅ Лог-канал установлен: {channel.mention}")

    @setlog_cmd.error
    async def setlog_cmd_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Команду `setlog` может использовать только администратор.")
        else:
            raise error

    @app_commands.command(
        name="setlog",
        description="Установить канал для логов наказаний (только админ).",
    )
    @app_commands.describe(channel="Канал, куда отправлять логи модерации")
    async def setlog_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Только администратор может настраивать лог-канал.",
                ephemeral=True,
            )
            return
        self.set_log_channel_id(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✅ Лог-канал установлен: {channel.mention}",
            ephemeral=True,
        )

    # ========= ! clear =========
    @commands.command(name="clear")
    @commands.check(has_bot_access_prefix)
    async def clear_cmd(self, ctx: commands.Context, amount: int = 5):
        if amount < 1 or amount > 200:
            await ctx.send("Количество должно быть от 1 до 200.")
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"🧹 Удалено сообщений: **{len(deleted) - 1}**")
        await msg.delete(delay=3)

        add_case(
            ctx.guild.id,
            ctx.author.id,
            ctx.author.id,
            "clear",
            f"Удалено {len(deleted) - 1} сообщений в #{ctx.channel.name}",
        )
        await self.send_log(
            ctx.guild,
            title="🧹 Очистка сообщений",
            description=f"Удалено {len(deleted) - 1} сообщений в #{ctx.channel.name}",
            user=ctx.author,
            moderator=ctx.author,
            color=discord.Color.blurple(),
        )

    # ========= /clear =========
    @app_commands.command(name="clear", description="Удалить сообщения (1–200).")
    @app_commands.describe(amount="Сколько сообщений удалить (1–200)")
    @app_commands.check(has_bot_access_slash)
    async def clear_slash(self, interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > 200:
            await interaction.response.send_message(
                "Количество должно быть от 1 до 200.",
                ephemeral=True,
            )
            return
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(
            f"🧹 Удалено сообщений: **{len(deleted)}**", ephemeral=True
        )

        add_case(
            interaction.guild.id,
            interaction.user.id,
            interaction.user.id,
            "clear",
            f"Удалено {len(deleted)} сообщений в #{interaction.channel.name}",
        )
        await self.send_log(
            interaction.guild,
            title="🧹 Очистка сообщений",
            description=f"Удалено {len(deleted)} сообщений в #{interaction.channel.name}",
            user=interaction.user,
            moderator=interaction.user,
            color=discord.Color.blurple(),
        )

    # ========= ! warn =========
    @commands.command(name="warn")
    @commands.check(has_bot_access_prefix)
    async def warn_cmd(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Причина не указана",
    ):
        await ctx.send(f"⚠ {member.mention} получил предупреждение: **{reason}**")

        add_case(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "warn",
            reason,
        )
        await self.send_log(
            ctx.guild,
            title="⚠ Предупреждение",
            description=f"Причина: {reason}",
            user=member,
            moderator=ctx.author,
            color=discord.Color.orange(),
        )

    # ========= /warn =========
    @app_commands.command(name="warn", description="Выдать предупреждение участнику.")
    @app_commands.describe(member="Кому выдать предупреждение", reason="Причина")
    @app_commands.check(has_bot_access_slash)
    async def warn_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Причина не указана",
    ):
        await interaction.response.send_message(
            f"⚠ {member.mention} получил предупреждение: **{reason}**"
        )

        add_case(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "warn",
            reason,
        )
        await self.send_log(
            interaction.guild,
            title="⚠ Предупреждение",
            description=f"Причина: {reason}",
            user=member,
            moderator=interaction.user,
            color=discord.Color.orange(),
        )

    # ========= ! warns =========
    @commands.command(name="warns")
    @commands.check(has_bot_access_prefix)
    async def warns_cmd(self, ctx: commands.Context, member: discord.Member):
        history = [
            c for c in get_history_for_user(ctx.guild.id, member.id)
            if c["action"] == "warn"
        ]
        if not history:
            await ctx.send(f"📋 У {member.mention} нет предупреждений.")
            return
        lines = []
        for i, case in enumerate(history[-10:], start=1):
            mod = ctx.guild.get_member(case["moderator_id"])
            mod_name = mod.mention if mod else f"ID {case['moderator_id']}"
            lines.append(
                f"`{i}.` [{case['timestamp']}] {mod_name} — **{case['reason']}**"
            )
        await ctx.send(
            f"📋 История предупреждений {member.mention}:\n" + "\n".join(lines)
        )

    # ========= /warns =========
    @app_commands.command(name="warns", description="Показать предупреждения участника.")
    @app_commands.describe(member="Чьи предупреждения показать")
    @app_commands.check(has_bot_access_slash)
    async def warns_slash(self, interaction: discord.Interaction, member: discord.Member):
        history = [
            c for c in get_history_for_user(interaction.guild.id, member.id)
            if c["action"] == "warn"
        ]
        if not history:
            await interaction.response.send_message(
                f"📋 У {member.mention} нет предупреждений.",
                ephemeral=True,
            )
            return
        lines = []
        for i, case in enumerate(history[-10:], start=1):
            mod = interaction.guild.get_member(case["moderator_id"])
            мод = mod.mention if mod else f"ID {case['moderator_id']}"
            lines.append(
                f"`{i}.` [{case['timestamp']}] {мод} — **{case['reason']}**"
            )
        await interaction.response.send_message(
            f"📋 История предупреждений {member.mention}:\n" + "\n".join(lines),
            ephemeral=True,
        )

    # ========= ! mute =========
    @commands.command(name="mute")
    @commands.check(has_bot_access_prefix)
    async def mute_cmd(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Не указана",
    ):
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if muted_role is None:
            muted_role = await ctx.guild.create_role(name="Muted")
        await member.add_roles(muted_role, reason=reason)
        await ctx.send(f"🔇 {member.mention} замьючен. Причина: **{reason}**")

        add_case(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "mute",
            reason,
        )
        await self.send_log(
            ctx.guild,
            title="🔇 Мут",
            description=f"Причина: {reason}",
            user=member,
            moderator=ctx.author,
            color=discord.Color.dark_gray(),
        )

    # ========= /mute =========
    @app_commands.command(name="mute", description="Выдать мут (роль Muted) участнику.")
    @app_commands.describe(member="Кого замьютить", reason="Причина")
    @app_commands.check(has_bot_access_slash)
    async def mute_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Не указана",
    ):
        guild = interaction.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if muted_role is None:
            muted_role = await guild.create_role(name="Muted")
        await member.add_roles(muted_role, reason=reason)
        await interaction.response.send_message(
            f"🔇 {member.mention} замьючен. Причина: **{reason}**"
        )

        add_case(
            guild.id,
            member.id,
            interaction.user.id,
            "mute",
            reason,
        )
        await self.send_log(
            guild,
            title="🔇 Мут",
            description=f"Причина: {reason}",
            user=member,
            moderator=interaction.user,
            color=discord.Color.dark_gray(),
        )

    # ========= ! unmute =========
    @commands.command(name="unmute")
    @commands.check(has_bot_access_prefix)
    async def unmute_cmd(self, ctx: commands.Context, member: discord.Member):
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if muted_role and muted_role in member.roles:
            await member.remove_roles(muted_role)
            await ctx.send(f"🔊 {member.mention} размьючен.")

            add_case(
                ctx.guild.id,
                member.id,
                ctx.author.id,
                "unmute",
            )
            await self.send_log(
                ctx.guild,
                title="🔊 Снятие мута",
                description="Мут снят.",
                user=member,
                moderator=ctx.author,
                color=discord.Color.green(),
            )
        else:
            await ctx.send("У участника нет мута.")

    # ========= /unmute =========
    @app_commands.command(name="unmute", description="Снять мут с участника.")
    @app_commands.describe(member="С кого снять мут")
    @app_commands.check(has_bot_access_slash)
    async def unmute_slash(self, interaction: discord.Interaction, member: discord.Member):
        guild = interaction.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if muted_role and muted_role in member.roles:
            await member.remove_roles(muted_role)
            await interaction.response.send_message(
                f"🔊 {member.mention} размьючен."
            )

            add_case(
                guild.id,
                member.id,
                interaction.user.id,
                "unmute",
            )
            await self.send_log(
                guild,
                title="🔊 Снятие мута",
                description="Мут снят.",
                user=member,
                moderator=interaction.user,
                color=discord.Color.green(),
            )
        else:
            await interaction.response.send_message(
                "У участника нет мута.", ephemeral=True
            )

import re
import discord
from discord import app_commands
from discord.ext import commands

BULK_BAN_LIMIT = 0 # защита: максимум банов за раз


def extract_ids(text: str) -> list[int]:
    """Достаёт user_id из строки (упоминания <@123>, <@!123> или просто цифры)."""
    ids = set()
    if not text:
        return []
    for m in re.findall(r"<@!?(\d{15,25})>", text):
        ids.add(int(m))
    for m in re.findall(r"\b(\d{15,25})\b",text):
        ids.add(int(m))
    return list(ids)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="ban_all",
        description="Ban one user, a role, or many users (EN) / Забанить (RU)"
    )
    @app_commands.describe(
        member="Один пользователь (опционально)",
        role="Роль (забанить всех с ролью) (опционально)",
        targets="Список: @user1 @user2 или ID через пробел (опционально)",
        reason="Причина (опционально)",
        delete_days="Удалить сообщения за N дней (0-7)",
        confirm="Подтверждение. Поставь True чтобы реально забанить"
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        role: discord.Role | None = None,
        targets: str | None = None,
        reason: str | None = None,
        delete_days: app_commands.Range[int, 0, 7] = 0,
        confirm: bool = False
    ):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Только на сервере.", ephemeral=True)

        me = guild.me
        if not me.guild_permissions.ban_members:
            return await interaction.response.send_message(
                "❌ У бота нет права **Ban Members** на этом сервере.",
                ephemeral=True
            )

        # собрать список целей
        members: list[discord.Member] = []

        if member:
            members.append(member)

        if role:
            members.extend([m for m in role.members if not m.bot])

        if targets:
            ids = extract_ids(targets)
            for uid in ids:
                m = guild.get_member(uid)
                if m and not m.bot:
                    members.append(m)

        # убрать дубликаты
        uniq = []
        seen = set()
        for m in members:
            if m.id not in seen:
                uniq.append(m)
                seen.add(m.id)
        members = uniq

        if not members:
            return await interaction.response.send_message(
                "Укажи `member` или `role` или `targets`.",
                ephemeral=True
            )

        if len(members) > BULK_BAN_LIMIT:
            return await interaction.response.send_message(
                f"Слишком много целей: {len(members)}. Лимит: {BULK_BAN_LIMIT}.",
                ephemeral=True
            )

        # если confirm=False — просто покажем кого забаним
        preview = "\n".join([f"- {m} (`{m.id}`)" for m in members])
        if len(preview) > 1800:
            preview = preview[:1800] + "\n… (обрезано)"

        if not confirm:
            return await interaction.response.send_message(
                "⚠ **Предпросмотр** (бан НЕ выполнен).\n"
                f"Целей: **{len(members)}**\n"
                f"Удаление сообщений: **{delete_days}** дн.\n"
                f"Причина: **{reason or 'не указана'}**\n\n"
                f"{preview}\n\n"
                "Чтобы выполнить бан — запусти команду ещё раз с `confirm=True`.",
                ephemeral=True
            )

        # баним
        ok, fail, skipped = 0, 0, 0
        for m in members:
            try:
                # нельзя банить владельца
                if m.id == guild.owner_id:
                    skipped += 1
                    continue

                # проверка иерархии ролей
                if me.top_role <= m.top_role:
                    skipped += 1
                    continue

                await guild.ban(
                    m,
                    reason=reason or "No reason",
                    delete_message_days=delete_days
                )
                ok += 1
            except Exception:
                fail += 1

        await interaction.response.send_message(
            f"⛔ Бан выполнен.\n"
            f"✅ Забанено: **{ok}**\n"
            f"⏭ Пропущено (роль выше/owner): **{skipped}**\n"
            f"❌ Ошибок: **{fail}**\n"
            f"Причина: **{reason or 'не указана'}**",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))


    # ========= ! ban =========
    @commands.command(name="ban")
    @commands.check(has_bot_access_prefix)
    async def ban_cmd(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "Не указана",
    ):
        await member.ban(reason=reason)
        await ctx.send(f"⛔ {member} забанен. Причина: **{reason}**")

        add_case(
            ctx.guild.id,
            member.id,
            ctx.author.id,
            "ban",
            reason,
        )
        await self.send_log(
            ctx.guild,
            title="⛔ Бан",
            description=f"Причина: {reason}",
            user=member,
            moderator=ctx.author,
            color=discord.Color.red(),
        )

    # ========= /ban =========
    @app_commands.command(name="ban", description="Забанить участника.")
    @app_commands.describe(member="Кого забанить", reason="Причина")
    @app_commands.check(has_bot_access_slash)
    async def ban_slash(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Не указана",
    ):
        await member.ban(reason=reason)
        await interaction.response.send_message(
            f"⛔ {member} забанен. Причина: **{reason}**"
        )

        add_case(
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "ban",
            reason,
        )
        await self.send_log(
            interaction.guild,
            title="⛔ Бан",
            description=f"Причина: {reason}",
            user=member,
            moderator=interaction.user,
            color=discord.Color.red(),
        )

    # ========= ! unban =========
    @commands.command(name="unban")
    @commands.check(has_bot_access_prefix)
    async def unban_cmd(self, ctx: commands.Context, *, name_or_id: str):
        bans = await ctx.guild.bans()
        for entry in bans:
            user = entry.user
            if (
                str(user.id) == name_or_id
                or f"{user.name}#{user.discriminator}" == name_or_id
            ):
                await ctx.guild.unban(user)
                await ctx.send(f"✅ {user} разбанен.")

                add_case(
                    ctx.guild.id,
                    user.id,
                    ctx.author.id,
                    "unban",
                )
                await self.send_log(
                    ctx.guild,
                    title="✅ Разбан",
                    description="Пользователь разбанен.",
                    user=user,
                    moderator=ctx.author,
                    color=discord.Color.green(),
                )
                return
        await ctx.send("Пользователь не найден в банах.")

    # ========= /unban =========
    @app_commands.command(name="unban", description="Разбанить по ID/имени.")
    @app_commands.describe(name_or_id="ID или Имя#0000")
    @app_commands.check(has_bot_access_slash)
    async def unban_slash(self, interaction: discord.Interaction, name_or_id: str):
        bans = await interaction.guild.bans()
        for entry in bans:
            user = entry.user
            if (
                str(user.id) == name_or_id
                or f"{user.name}#{user.discriminator}" == name_or_id
            ):
                await interaction.guild.unban(user)
                await interaction.response.send_message(
                    f"✅ {user} разбанен."
                )

                add_case(
                    interaction.guild.id,
                    user.id,
                    interaction.user.id,
                    "unban",
                )
                await self.send_log(
                    interaction.guild,
                    title="✅ Разбан",
                    description="Пользователь разбанен.",
                    user=user,
                    moderator=interaction.user,
                    color=discord.Color.green(),
                )
                return
        await interaction.response.send_message(
            "Пользователь не найден в списке банов.", ephemeral=True
        )

    # ========= !history / /history =========
    @commands.command(name="history")
    @commands.check(has_bot_access_prefix)
    async def history_cmd(self, ctx: commands.Context, member: discord.Member):
        cases = get_history_for_user(ctx.guild.id, member.id)
        if not cases:
            await ctx.send(f"ℹ У {member.mention} нет записей в истории наказаний.")
            return
        lines = []
        for i, case in enumerate(cases[-15:], start=1):
            mod = ctx.guild.get_member(case["moderator_id"])
            mod_name = mod.mention if mod else f"ID {case['moderator_id']}"
            reason = case.get("reason") or "Не указана"
            lines.append(
                f"`{i}.` [{case['timestamp']}] **{case['action'].upper()}** — {mod_name} — {reason}"
            )
        await ctx.send(
            f"📚 История наказаний {member.mention}:\n" + "\n".join(lines)
        )

    @app_commands.command(
        name="history",
        description="Показать историю наказаний участника.",
    )
    @app_commands.describe(member="Чью историю показать")
    @app_commands.check(has_bot_access_slash)
    async def history_slash(self, interaction: discord.Interaction, member: discord.Member):
        cases = get_history_for_user(interaction.guild.id, member.id)
        if not cases:
            await interaction.response.send_message(
                f"ℹ У {member.mention} нет записей в истории наказаний.",
                ephemeral=True,
            )
            return
        lines = []
        for i, case in enumerate(cases[-15:], start=1):
            mod = interaction.guild.get_member(case["moderator_id"])
            mod_name = mod.mention if mod else f"ID {case['moderator_id']}"
            reason = case.get("reason") or "Не указана"
            lines.append(
                f"`{i}.` [{case['timestamp']}] **{case['action'].upper()}** — {mod_name} — {reason}"
            )
        await interaction.response.send_message(
            f"📚 История наказаний {member.mention}:\n" + "\n".join(lines),
            ephemeral=True,
        )


   