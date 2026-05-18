from pathlib import Path
import asyncio
from typing import Any, Dict, Optional

from .json_store import load_json, save_json

SETTINGS_FILE = Path(__file__).resolve().parents[1] / "data" / "guild_settings.json"
DEFAULT_SETTINGS: Dict[str, Any] = {"moderator_role_names": "", "antimat_enabled": True}
_lock = asyncio.Lock()


def _load_all() -> Dict[str, Dict[str, Any]]:
    return load_json(SETTINGS_FILE, {})


def _save_all(data: Dict[str, Dict[str, Any]]) -> None:
    save_json(SETTINGS_FILE, data)


async def get_guild_settings(guild_id: int) -> Dict[str, Any]:
    async with _lock:
        return _load_all().get(str(guild_id), {}).copy()


async def get_guild_setting(guild_id: int, key: str, default: Optional[Any] = None) -> Any:
    settings = await get_guild_settings(guild_id)
    return settings.get(key, DEFAULT_SETTINGS.get(key, default))


async def set_guild_setting(guild_id: int, key: str, value: Any) -> None:
    async with _lock:
        data = _load_all()
        guild_key = str(guild_id)
        guild = data.get(guild_key, {})
        guild[key] = value
        data[guild_key] = guild
        _save_all(data)


async def delete_guild_setting(guild_id: int, key: str) -> None:
    async with _lock:
        data = _load_all()
        guild_key = str(guild_id)
        if guild_key not in data:
            return
        data[guild_key].pop(key, None)
        if data[guild_key]:
            _save_all(data)
        else:
            data.pop(guild_key, None)
            _save_all(data)
