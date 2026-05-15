import json
from pathlib import Path
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

MODLOG_FILE = Path(__file__).resolve().parents[1] / "data" / "modlog.json"
_lock = asyncio.Lock()


def _load_all() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    MODLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not MODLOG_FILE.exists():
        MODLOG_FILE.write_text("{}", encoding="utf-8")
    try:
        data = json.loads(MODLOG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_all(data: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> None:
    MODLOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def log_mod_action(
    guild_id: int,
    target_id: Optional[int],
    action: str,
    moderator_id: int,
    reason: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    async with _lock:
        data = _load_all()
        guild_key = str(guild_id)
        target_key = str(target_id) if target_id is not None else "0"
        data.setdefault(guild_key, {}).setdefault(target_key, []).append(
            {
                "action": action,
                "moderator_id": moderator_id,
                "reason": reason,
                "extra": extra or {},
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
        )
        _save_all(data)


async def get_guild_actions(guild_id: int) -> Dict[str, List[Dict[str, Any]]]:
    async with _lock:
        return _load_all().get(str(guild_id), {}).copy()


async def get_user_actions(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    return (await get_guild_actions(guild_id)).get(str(user_id), [])

