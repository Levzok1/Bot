import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .guild_settings import get_guild_setting, set_guild_setting
from .json_store import load_json, save_json
from .moderation import _send_ephemeral, _valid_target, super_mod
from .modlog import log_mod_action


WARNINGS_FILE = Path(__file__).resolve().parents[1] / "data" / "warnings.json"
MAX_REASON_LENGTH = 512
MAX_WARN_DECAY_DAYS = 365
MAX_TIMEOUT_MINUTES = 28 * 24 * 60
_lock = asyncio.Lock()

DEFAULT_WARN_POLICY: Dict[str, Any] = {
    "decayDays": 30,
    "tiers": [
        {"warns": 1, "action": "none", "durationMinutes": 0, "label": "Предупреждение"},
        {"warns": 2, "action": "timeout", "durationMinutes": 10, "label": "Мут 10 минут"},
        {"warns": 3, "action": "timeout", "durationMinutes": 60, "label": "Мут 1 час"},
    ],
}

ALLOWED_WARN_ACTIONS = {"none", "timeout", "kick", "ban"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _load_all() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    return load_json(WARNINGS_FILE, {})


def _save_all(data: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> None:
    save_json(WARNINGS_FILE, data)


def validate_warn_policy(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Политика варнов должна быть объектом.")

    try:
        decay_days = int(raw.get("decayDays", DEFAULT_WARN_POLICY["decayDays"]))
    except (TypeError, ValueError):
        raise ValueError("Срок спада варна должен быть числом дней.") from None
    if decay_days < 1 or decay_days > MAX_WARN_DECAY_DAYS:
        raise ValueError(f"Срок спада варна должен быть от 1 до {MAX_WARN_DECAY_DAYS} дней.")

    raw_tiers = raw.get("tiers")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        raise ValueError("Нужен хотя бы один порог наказания.")

    tiers: List[Dict[str, Any]] = []
    seen_warns: set[int] = set()
    for item in raw_tiers[:10]:
        if not isinstance(item, dict):
            raise ValueError("Каждый порог должен быть объектом.")
        try:
            warns = int(item.get("warns"))
        except (TypeError, ValueError):
            raise ValueError("Количество варнов в пороге должно быть числом.") from None
        if warns < 1 or warns > 100:
            raise ValueError("Количество варнов должно быть от 1 до 100.")
        if warns in seen_warns:
            raise ValueError(f"Порог {warns} указан дважды.")
        seen_warns.add(warns)

        action = str(item.get("action", "none")).strip().casefold()
        if action not in ALLOWED_WARN_ACTIONS:
            raise ValueError("Действие порога должно быть none, timeout, kick или ban.")

        try:
            duration = int(item.get("durationMinutes", 0) or 0)
        except (TypeError, ValueError):
            raise ValueError("Длительность мута должна быть числом минут.") from None
        if duration < 0 or duration > MAX_TIMEOUT_MINUTES:
            raise ValueError(f"Длительность мута должна быть от 0 до {MAX_TIMEOUT_MINUTES} минут.")
        if action == "timeout" and duration < 1:
            raise ValueError("Для timeout нужна длительность больше 0 минут.")

        label = str(item.get("label", "") or "").strip()[:80]
        tiers.append(
            {
                "warns": warns,
                "action": action,
                "durationMinutes": duration,
                "label": label or _default_tier_label(action, duration),
            }
        )

    tiers.sort(key=lambda tier: tier["warns"])
    return {"decayDays": decay_days, "tiers": tiers}


def _default_tier_label(action: str, duration: int) -> str:
    if action == "timeout":
        return f"Мут {duration} мин."
    if action == "kick":
        return "Kick"
    if action == "ban":
        return "Ban"
    return "Предупреждение"


async def get_warn_policy(guild_id: int) -> Dict[str, Any]:
    raw = await get_guild_setting(guild_id, "warn_policy", None)
    if raw is None:
        return deepcopy(DEFAULT_WARN_POLICY)
    try:
        return validate_warn_policy(raw)
    except ValueError:
        return deepcopy(DEFAULT_WARN_POLICY)


async def save_warn_policy(guild_id: int, raw: Any) -> Dict[str, Any]:
    policy = validate_warn_policy(raw)
    await set_guild_setting(guild_id, "warn_policy", policy)
    return policy


def _is_warning_active(record: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    if record.get("removed"):
        return False
    expires_at = record.get("expires_at")
    if not expires_at:
        return True
    try:
        return _parse_iso(str(expires_at)) > (now or _utc_now())
    except ValueError:
        return False


async def get_member_warnings(guild_id: int, member_id: int, *, active_only: bool = True) -> List[Dict[str, Any]]:
    async with _lock:
        data = _load_all()
        records = data.get(str(guild_id), {}).get(str(member_id), [])
        if not isinstance(records, list):
            return []
        warnings = [record.copy() for record in records if isinstance(record, dict)]
    if active_only:
        now = _utc_now()
        warnings = [record for record in warnings if _is_warning_active(record, now)]
    return warnings


async def add_member_warning(
    guild_id: int,
    member_id: int,
    moderator_id: int,
    reason: str,
    decay_days: int,
) -> Dict[str, Any]:
    now = _utc_now()
    record = {
        "id": f"{int(now.timestamp())}-{moderator_id}",
        "member_id": member_id,
        "moderator_id": moderator_id,
        "reason": reason[:MAX_REASON_LENGTH] or "Без причины",
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(days=decay_days)),
        "removed": False,
    }
    async with _lock:
        data = _load_all()
        guild_records = data.setdefault(str(guild_id), {})
        member_records = guild_records.setdefault(str(member_id), [])
        member_records.append(record)
        _save_all(data)
    return record


async def clear_member_warnings(guild_id: int, member_id: int, moderator_id: int, reason: str) -> int:
    removed = 0
    async with _lock:
        data = _load_all()
        records = data.get(str(guild_id), {}).get(str(member_id), [])
        now = _iso(_utc_now())
        for record in records:
            if isinstance(record, dict) and _is_warning_active(record):
                record["removed"] = True
                record["removed_at"] = now
                record["removed_by"] = moderator_id
                record["remove_reason"] = reason[:MAX_REASON_LENGTH] or "Без причины"
                removed += 1
        if removed:
            _save_all(data)
    return removed


def selected_warn_tier(policy: Dict[str, Any], active_count: int) -> Dict[str, Any]:
    tiers = [tier for tier in policy["tiers"] if tier["warns"] <= active_count]
    return tiers[-1] if tiers else {"warns": active_count, "action": "none", "durationMinutes": 0, "label": "Предупреждение"}


async def apply_warn_punishment(
    guild: discord.Guild,
    member: discord.Member,
    tier: Dict[str, Any],
    reason: str,
) -> str:
    action = tier["action"]
    if action == "none":
        return "Предупреждение записано."

    me = guild.me
    if me is None:
        return "Предупреждение записано, но роль бота не найдена."
    if member.top_role >= me.top_role:
        return "Предупреждение записано, но роль бота ниже роли участника."

    if action == "timeout":
        if not me.guild_permissions.moderate_members:
            return "Предупреждение записано, но у бота нет права Moderate Members для мута."
        until = _utc_now() + timedelta(minutes=int(tier["durationMinutes"]))
        await member.timeout(until, reason=reason)
        return f"Выдан мут на {tier['durationMinutes']} мин."

    if action == "kick":
        if not me.guild_permissions.kick_members:
            return "Предупреждение записано, но у бота нет права Kick Members."
        await member.kick(reason=reason)
        return "Участник кикнут."

    if action == "ban":
        if not me.guild_permissions.ban_members:
            return "Предупреждение записано, но у бота нет права Ban Members."
        await guild.ban(member, reason=reason)
        return "Участник забанен."

    return "Предупреждение записано."


async def warn_member(
    guild: discord.Guild,
    member: discord.Member,
    moderator_id: int,
    reason: str,
) -> Dict[str, Any]:
    policy = await get_warn_policy(guild.id)
    record = await add_member_warning(guild.id, member.id, moderator_id, reason, int(policy["decayDays"]))
    active = await get_member_warnings(guild.id, member.id, active_only=True)
    tier = selected_warn_tier(policy, len(active))
    punishment = await apply_warn_punishment(
        guild,
        member,
        tier,
        f"{reason or 'Без причины'} (warn #{len(active)})",
    )
    await log_mod_action(
        guild.id,
        member.id,
        "warn",
        moderator_id,
        reason=reason or "Без причины",
        extra={"active_warnings": len(active), "tier": tier, "warning_id": record["id"], "punishment": punishment},
    )
    return {"warning": record, "activeCount": len(active), "tier": tier, "punishment": punishment}


def format_warning_list(member: discord.Member, warnings: List[Dict[str, Any]]) -> str:
    if not warnings:
        return f"У {member.mention} нет активных варнов."
    lines = [f"Активные варны {member.mention}: {len(warnings)}"]
    for index, record in enumerate(warnings[-10:], start=1):
        expires = record.get("expires_at", "без срока")
        lines.append(f"{index}. {record.get('reason') or 'Без причины'} | до {expires}")
    return "\n".join(lines)


class Warnings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _clearwarns_response(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str],
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        removed = await clear_member_warnings(interaction.guild.id, member.id, interaction.user.id, reason or "Без причины")
        await log_mod_action(
            interaction.guild.id,
            member.id,
            "clearwarns",
            interaction.user.id,
            reason=reason or "Без причины",
            extra={"removed": removed},
        )
        await interaction.response.send_message(f"Снято активных варнов: {removed}.", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CheckFailure):
            await _send_ephemeral(interaction, "У тебя нет прав использовать эту команду.")
            return
        raise error

    @super_mod
    @app_commands.command(name="warn", description="Выдать предупреждение с авто-наказанием по настройкам сервера.")
    @app_commands.guild_only()
    @app_commands.describe(member="Кому выдать варн", reason="Причина")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)
        if not _valid_target(interaction, member):
            return await interaction.response.send_message("Нельзя выдать варн этому участнику.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            result = await warn_member(interaction.guild, member, interaction.user.id, reason or "Без причины")
        except discord.HTTPException:
            return await interaction.followup.send("Варн записан не был: Discord отклонил действие.", ephemeral=True)

        await interaction.followup.send(
            f"Варн выдан {member.mention}. Активных варнов: {result['activeCount']}. {result['punishment']}",
            ephemeral=True,
        )

    @super_mod
    @app_commands.command(name="warnings", description="Показать активные варны участника.")
    @app_commands.guild_only()
    @app_commands.describe(member="Чьи варны показать")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)
        warnings = await get_member_warnings(interaction.guild.id, member.id, active_only=True)
        await interaction.response.send_message(format_warning_list(member, warnings), ephemeral=True)

    @super_mod
    @app_commands.command(name="clearwarns", description="Снять все активные варны участника.")
    @app_commands.guild_only()
    @app_commands.describe(member="С кого снять варны", reason="Причина")
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await self._clearwarns_response(interaction, member, reason)

    @super_mod
    @app_commands.command(name="unwarn", description="Снять все активные варны участника.")
    @app_commands.guild_only()
    @app_commands.describe(member="С кого снять варны", reason="Причина")
    async def unwarn(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await self._clearwarns_response(interaction, member, reason)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Warnings(bot))
