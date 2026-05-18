import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional
from urllib.parse import urlencode, urlparse

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands

from .antimat import format_words, load_words, parse_words, save_words
from .guild_settings import delete_guild_setting, get_guild_settings, set_guild_setting
from .modlog import get_guild_actions, log_mod_action
from .warnings import (
    clear_member_warnings,
    get_member_warnings,
    get_warn_policy,
    save_warn_policy,
    warn_member,
)


SNOWFLAKE_RE = re.compile(r"^\d{15,25}$")
SETTING_KEY_RE = re.compile(r"^[a-zA-Z0-9_]{1,64}$")
DISCORD_API_BASE = "https://discord.com/api/v10"
ADMINISTRATOR = 0x8
MANAGE_GUILD = 0x20
MANAGE_ROLES = 0x10000000
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)
STATIC_SITE_DIR = Path(__file__).resolve().parents[1] / "bot_site"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on", "enable", "enabled"}


def _json(data: Dict[str, Any], status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _parse_snowflake(value: Any, field: str) -> int:
    text = str(value or "").strip()
    if not SNOWFLAKE_RE.fullmatch(text):
        raise ApiError(400, f"{field} должен быть Discord ID.")
    return int(text)


def _optional_snowflake(value: Any, field: str) -> Optional[int]:
    if value in (None, ""):
        return None
    return _parse_snowflake(value, field)


def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{field} должен быть числом.") from None
    if parsed < minimum or parsed > maximum:
        raise ApiError(400, f"{field} должен быть от {minimum} до {maximum}.")
    return parsed


def _text(value: Any, field: str, *, max_length: int, required: bool = True) -> str:
    parsed = str(value or "").strip()
    if required and not parsed:
        raise ApiError(400, f"{field} не может быть пустым.")
    if len(parsed) > max_length:
        raise ApiError(400, f"{field} слишком длинный.")
    return parsed


def _safe_emoji(value: Any) -> str:
    emoji = _text(value, "emoji", max_length=64)
    if any(char in emoji for char in ";\n\r=|"):
        raise ApiError(400, "emoji содержит запрещенный разделитель.")
    return emoji


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on", "да", "вкл", "enable", "enabled"}


def _parse_color(value: Any) -> discord.Color:
    text = str(value or "").strip().lstrip("#")
    if not text:
        return discord.Color.blurple()
    if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        raise ApiError(400, "color должен быть HEX-цветом вида #6257ff.")
    return discord.Color(int(text, 16))


class DashboardAPI(commands.Cog):
    """Token/OAuth protected HTTP API for the static dashboard."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.host = os.getenv("DASHBOARD_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
        self.port = int(os.getenv("DASHBOARD_API_PORT", "8080"))
        self.public_url = os.getenv("DASHBOARD_PUBLIC_URL", f"http://{self.host}:{self.port}").rstrip("/")
        self.token = os.getenv("DASHBOARD_TOKEN", "").strip()
        self.allowed_origins = self._load_allowed_origins()
        self.discord_client_id = os.getenv("DISCORD_CLIENT_ID", os.getenv("DASHBOARD_DISCORD_CLIENT_ID", "")).strip()
        self.discord_client_secret = os.getenv("DISCORD_CLIENT_SECRET", os.getenv("DASHBOARD_DISCORD_CLIENT_SECRET", "")).strip()
        self.discord_redirect_uri = os.getenv(
            "DASHBOARD_DISCORD_REDIRECT_URI",
            f"{self.public_url}/api/auth/callback",
        ).strip()
        local_no_auth = self.host in {"127.0.0.1", "localhost", "::1"} and not self.token and not self.oauth_enabled
        self.allow_unsafe_no_auth = _env_bool("DASHBOARD_ALLOW_UNSAFE_NO_AUTH", local_no_auth)
        self.oauth_states: Dict[str, Dict[str, Any]] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

    async def cog_load(self) -> None:
        app = self._build_app()
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        try:
            await self.site.start()
        except OSError as error:
            print(f"[DashboardAPI] Не удалось запустить API на {self.host}:{self.port}: {error}")
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            return

        auth_modes = []
        if self.token:
            auth_modes.append("token")
        if self.oauth_enabled:
            auth_modes.append("discord-oauth")
        if self.allow_unsafe_no_auth:
            auth_modes.append("unsafe-no-auth")
        print(f"[DashboardAPI] API запущен: http://{self.host}:{self.port} ({', '.join(auth_modes) or 'read-only'})")

    async def cog_unload(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.discord_client_id and self.discord_client_secret and self.discord_redirect_uri)

    def _load_allowed_origins(self) -> set[str]:
        raw = os.getenv("DASHBOARD_ALLOWED_ORIGINS", "")
        origins = {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}
        return origins or set(DEFAULT_ALLOWED_ORIGINS)

    def _build_app(self) -> web.Application:
        @web.middleware
        async def cors_middleware(request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]):
            if request.method == "OPTIONS":
                response: web.StreamResponse = web.Response(status=204)
            else:
                try:
                    response = await handler(request)
                except web.HTTPException:
                    raise
                except ApiError as error:
                    response = _json({"ok": False, "error": error.message}, status=error.status)
                except Exception as error:
                    print(f"[DashboardAPI] Unhandled API error: {error}")
                    response = _json({"ok": False, "error": "Внутренняя ошибка API."}, status=500)

            origin = request.headers.get("Origin")
            if origin and self._origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Dashboard-Token"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            return response

        app = web.Application(middlewares=[cors_middleware])
        app.router.add_route("OPTIONS", "/{tail:.*}", self.options)
        app.router.add_get("/", self.index)
        app.router.add_get("/{filename:app\\.js|api\\.js|styles\\.css|vercel\\.json}", self.static_file)
        app.router.add_get("/assets/{filename}", self.asset_file)
        app.router.add_get("/api/health", self.health)
        app.router.add_get("/api/auth/login", self.auth_login)
        app.router.add_get("/api/auth/callback", self.auth_callback)
        app.router.add_post("/api/auth/logout", self.auth_logout)
        app.router.add_get("/api/me", self.me)
        app.router.add_get("/api/guilds", self.guilds)
        app.router.add_get("/api/guilds/{guild_id}/channels", self.channels)
        app.router.add_get("/api/guilds/{guild_id}/roles", self.roles)
        app.router.add_get("/api/guilds/{guild_id}/settings", self.settings)
        app.router.add_get("/api/guilds/{guild_id}/modlog", self.modlog)
        app.router.add_post("/api/actions", self.actions)
        return app

    def _origin_allowed(self, origin: str) -> bool:
        normalized = origin.rstrip("/")
        return "*" in self.allowed_origins or normalized in self.allowed_origins

    async def options(self, request: web.Request) -> web.Response:
        return web.Response(status=204)

    async def index(self, request: web.Request) -> web.StreamResponse:
        path = STATIC_SITE_DIR / "index.html"
        if not path.is_file():
            return await self.health(request)
        return web.FileResponse(path)

    async def static_file(self, request: web.Request) -> web.FileResponse:
        filename = request.match_info["filename"]
        path = STATIC_SITE_DIR / filename
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def asset_file(self, request: web.Request) -> web.FileResponse:
        filename = request.match_info["filename"]
        path = (STATIC_SITE_DIR / "assets" / filename).resolve()
        assets_dir = (STATIC_SITE_DIR / "assets").resolve()
        if assets_dir not in path.parents or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def health(self, request: web.Request) -> web.Response:
        return _json(
            {
                "ok": True,
                "bot": str(self.bot.user) if self.bot.user else None,
                "guildCount": len(self.bot.guilds),
                "auth": {
                    "token": bool(self.token),
                    "discordOAuth": self.oauth_enabled,
                    "unsafeNoAuth": self.allow_unsafe_no_auth,
                },
            }
        )

    async def auth_login(self, request: web.Request) -> web.Response:
        if not self.oauth_enabled:
            raise ApiError(400, "Discord OAuth2 не настроен на backend.")

        return_to = request.query.get("return_to", "")
        if not self._return_to_allowed(return_to):
            return_to = self._default_return_to()

        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = {"return_to": return_to, "expires_at": time.time() + 600}
        params = urlencode(
            {
                "client_id": self.discord_client_id,
                "redirect_uri": self.discord_redirect_uri,
                "response_type": "code",
                "scope": "identify guilds",
                "state": state,
            }
        )
        raise web.HTTPFound(f"https://discord.com/oauth2/authorize?{params}")

    async def auth_callback(self, request: web.Request) -> web.Response:
        if not self.oauth_enabled:
            raise ApiError(400, "Discord OAuth2 не настроен на backend.")

        state = request.query.get("state", "")
        code = request.query.get("code", "")
        record = self.oauth_states.pop(state, None)
        if not record or record["expires_at"] < time.time() or not code:
            raise ApiError(400, "OAuth2 state устарел или неверен.")

        token_data = await self._exchange_oauth_code(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise ApiError(400, "Discord не вернул access_token.")

        user, guilds = await self._fetch_oauth_identity(access_token)
        session_id = secrets.token_urlsafe(40)
        self.sessions[session_id] = {
            "user": user,
            "guilds": self._guild_permission_map(guilds),
            "access_token": access_token,
            "expires_at": time.time() + int(token_data.get("expires_in") or 604800),
        }

        response = web.HTTPFound(record["return_to"])
        secure_cookie = self.public_url.startswith("https://")
        response.set_cookie(
            "dashboard_session",
            session_id,
            httponly=True,
            secure=secure_cookie,
            samesite="None" if secure_cookie else "Lax",
            max_age=604800,
            path="/",
        )
        raise response

    async def auth_logout(self, request: web.Request) -> web.Response:
        session_id = request.cookies.get("dashboard_session", "")
        self.sessions.pop(session_id, None)
        response = _json({"ok": True})
        response.del_cookie("dashboard_session", path="/")
        return response

    async def me(self, request: web.Request) -> web.Response:
        context = await self._auth_context(request)
        return _json({"ok": True, "mode": context["mode"], "user": context.get("user")})

    async def guilds(self, request: web.Request) -> web.Response:
        context = await self._auth_context(request)
        guilds = []
        for guild in self.bot.guilds:
            if context["mode"] == "oauth" and not self._session_can_manage(context["session"], guild.id):
                continue
            guilds.append(self._guild_payload(guild))
        return _json({"ok": True, "guilds": guilds})

    async def channels(self, request: web.Request) -> web.Response:
        guild = self._guild(_parse_snowflake(request.match_info["guild_id"], "guild_id"))
        await self._require_manage(request, guild.id)
        return _json(
            {
                "ok": True,
                "textChannels": [self._text_channel_payload(channel) for channel in guild.text_channels],
                "voiceChannels": [self._voice_channel_payload(channel) for channel in guild.voice_channels],
            }
        )

    async def roles(self, request: web.Request) -> web.Response:
        guild = self._guild(_parse_snowflake(request.match_info["guild_id"], "guild_id"))
        await self._require_manage(request, guild.id)
        roles = [role for role in sorted(guild.roles, key=lambda item: item.position, reverse=True) if not role.is_default()]
        return _json({"ok": True, "roles": [self._role_payload(role) for role in roles]})

    async def settings(self, request: web.Request) -> web.Response:
        guild = self._guild(_parse_snowflake(request.match_info["guild_id"], "guild_id"))
        await self._require_manage(request, guild.id)
        return _json({"ok": True, "settings": await get_guild_settings(guild.id)})

    async def modlog(self, request: web.Request) -> web.Response:
        guild = self._guild(_parse_snowflake(request.match_info["guild_id"], "guild_id"))
        await self._require_manage(request, guild.id)
        return _json({"ok": True, "actions": await get_guild_actions(guild.id)})

    async def actions(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            raise ApiError(400, "Нужен JSON body.") from None
        if not isinstance(data, dict):
            raise ApiError(400, "JSON body должен быть объектом.")

        action_type = _text(data.get("type"), "type", max_length=80)
        guild_id = _optional_snowflake(data.get("guildId"), "guildId")
        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            raise ApiError(400, "payload должен быть объектом.")
        payload = {**payload, "_actionType": action_type}

        handlers: Dict[str, Callable[[web.Request, Optional[int], Dict[str, Any]], Awaitable[Dict[str, Any]]]] = {
            "message.say": self._action_message_say,
            "message.embed": self._action_message_embed,
            "moderation.clear": self._action_moderation_clear,
            "moderation.kick": self._action_moderation_kick,
            "moderation.ban": self._action_moderation_ban,
            "moderation.unban": self._action_moderation_unban,
            "warnings.warn": self._action_warning_warn,
            "warnings.list": self._action_warning_list,
            "warnings.clear": self._action_warning_clear,
            "warnings.config.get": self._action_warning_config_get,
            "warnings.config.set": self._action_warning_config_set,
            "music.menu": self._action_music_menu,
            "music.join": self._action_music_join,
            "music.play": self._action_music_play,
            "music.leave": self._action_music_guild,
            "music.skip": self._action_music_guild,
            "music.shuffle": self._action_music_guild,
            "music.stop": self._action_music_guild,
            "music.queue": self._action_music_guild,
            "music.now": self._action_music_guild,
            "music.jump": self._action_music_jump,
            "music.lyrics": self._action_music_lyrics,
            "reaction_roles.create": self._action_rr_create,
            "reaction_roles.add": self._action_rr_add,
            "reaction_roles.remove": self._action_rr_remove,
            "reaction_roles.list": self._action_rr_list,
            "config.view": self._action_config_view,
            "config.set": self._action_config_set,
            "config.delete": self._action_config_delete,
            "automod.words": self._action_words,
            "automod.add_words": self._action_add_words,
            "automod.del_words": self._action_del_words,
        }
        handler = handlers.get(action_type)
        if handler is None:
            raise ApiError(400, f"Действие {action_type} не разрешено API.")

        result = await handler(request, guild_id, payload)
        return _json({"ok": True, **result})

    async def _exchange_oauth_code(self, code: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{DISCORD_API_BASE}/oauth2/token",
                data={
                    "client_id": self.discord_client_id,
                    "client_secret": self.discord_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.discord_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status >= 400:
                    raise ApiError(400, "Discord OAuth2 token exchange не прошел.")
                return await response.json()

    async def _fetch_oauth_identity(self, access_token: str) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f"{DISCORD_API_BASE}/users/@me") as response:
                if response.status >= 400:
                    raise ApiError(400, "Не удалось получить пользователя Discord.")
                user = await response.json()
            async with session.get(f"{DISCORD_API_BASE}/users/@me/guilds") as response:
                if response.status >= 400:
                    raise ApiError(400, "Не удалось получить серверы Discord.")
                guilds = await response.json()
        return user, guilds if isinstance(guilds, list) else []

    def _guild_permission_map(self, guilds: list[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for guild in guilds:
            guild_id = str(guild.get("id") or "")
            if not SNOWFLAKE_RE.fullmatch(guild_id):
                continue
            result[guild_id] = {
                "owner": bool(guild.get("owner")),
                "permissions": int(guild.get("permissions") or 0),
            }
        return result

    def _return_to_allowed(self, return_to: str) -> bool:
        if not return_to:
            return False
        parsed = urlparse(return_to)
        if not parsed.scheme or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return self._origin_allowed(origin)

    def _default_return_to(self) -> str:
        origin = next(iter(self.allowed_origins)) if self.allowed_origins else "http://localhost:4173"
        return f"{origin}/#/settings"

    async def _auth_context(self, request: web.Request) -> Dict[str, Any]:
        if self.allow_unsafe_no_auth:
            return {"mode": "unsafe"}

        token = request.headers.get("X-Dashboard-Token", "")
        auth = request.headers.get("Authorization", "")
        if auth.casefold().startswith("bearer "):
            token = auth[7:].strip()
        if self.token and token and secrets.compare_digest(token, self.token):
            return {"mode": "token"}

        session_id = request.cookies.get("dashboard_session", "")
        session = self.sessions.get(session_id)
        if session and session.get("expires_at", 0) > time.time():
            return {"mode": "oauth", "session": session, "user": session.get("user")}

        raise ApiError(401, "Нет доступа к dashboard API. Укажи DASHBOARD_TOKEN или войди через Discord OAuth2.")

    async def _require_manage(self, request: web.Request, guild_id: int) -> Dict[str, Any]:
        context = await self._auth_context(request)
        if context["mode"] in {"token", "unsafe"}:
            return context
        if self._session_can_manage(context["session"], guild_id):
            return context
        raise ApiError(403, "Твой Discord-аккаунт не управляет этим сервером или бот не находится на нем.")

    def _session_can_manage(self, session: Dict[str, Any], guild_id: int) -> bool:
        record = session.get("guilds", {}).get(str(guild_id))
        if not record:
            return False
        permissions = int(record.get("permissions") or 0)
        return bool(record.get("owner") or permissions & (ADMINISTRATOR | MANAGE_GUILD | MANAGE_ROLES))

    def _actor_id(self, context: Dict[str, Any]) -> int:
        user = context.get("user") or {}
        user_id = str(user.get("id") or "")
        if SNOWFLAKE_RE.fullmatch(user_id):
            return int(user_id)
        return self.bot.user.id if self.bot.user else 0

    def _guild(self, guild_id: int) -> discord.Guild:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise ApiError(404, "Сервер не найден у бота.")
        return guild

    def _text_channel(self, channel_id: int) -> discord.TextChannel:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise ApiError(404, "Текстовый канал не найден у бота.")
        return channel

    def _voice_channel(self, channel_id: int) -> discord.VoiceChannel | discord.StageChannel:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            raise ApiError(404, "Голосовой канал не найден у бота.")
        return channel

    def _guild_payload(self, guild: discord.Guild) -> Dict[str, Any]:
        return {
            "id": str(guild.id),
            "name": guild.name,
            "memberCount": guild.member_count,
            "ownerId": str(guild.owner_id),
            "iconUrl": guild.icon.url if guild.icon else None,
        }

    def _text_channel_payload(self, channel: discord.TextChannel) -> Dict[str, Any]:
        me = channel.guild.me
        permissions = channel.permissions_for(me) if me else None
        return {
            "id": str(channel.id),
            "name": channel.name,
            "position": channel.position,
            "canSend": bool(permissions and permissions.send_messages),
            "canEmbed": bool(permissions and permissions.embed_links),
        }

    def _voice_channel_payload(self, channel: discord.VoiceChannel) -> Dict[str, Any]:
        me = channel.guild.me
        permissions = channel.permissions_for(me) if me else None
        return {
            "id": str(channel.id),
            "name": channel.name,
            "position": channel.position,
            "canConnect": bool(permissions and permissions.connect),
            "canSpeak": bool(permissions and permissions.speak),
        }

    def _role_payload(self, role: discord.Role) -> Dict[str, Any]:
        return {
            "id": str(role.id),
            "name": role.name,
            "position": role.position,
            "managed": role.managed,
            "color": str(role.color),
        }

    async def _check_actor_hierarchy(self, guild: discord.Guild, context: Dict[str, Any], target: discord.Member) -> None:
        if context["mode"] != "oauth":
            return
        actor_id = self._actor_id(context)
        actor = guild.get_member(actor_id)
        if actor is None:
            try:
                actor = await guild.fetch_member(actor_id)
            except discord.HTTPException:
                raise ApiError(403, "Не удалось проверить твою роль на сервере.") from None
        if actor != guild.owner and target.top_role >= actor.top_role:
            raise ApiError(403, "Нельзя модерировать участника с ролью не ниже твоей.")

    async def _managed_guild(
        self,
        request: web.Request,
        guild_id: Optional[int],
        payload: Dict[str, Any],
    ) -> tuple[discord.Guild, Dict[str, Any]]:
        guild = self._guild(guild_id or _parse_snowflake(payload.get("guildId"), "guildId"))
        return guild, await self._require_manage(request, guild.id)

    async def _fetch_member(self, guild: discord.Guild, member_id: int) -> discord.Member:
        try:
            return guild.get_member(member_id) or await guild.fetch_member(member_id)
        except discord.HTTPException:
            raise ApiError(404, "Участник не найден.") from None

    async def _action_message_say(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._text_channel(_parse_snowflake(payload.get("textChannelId"), "textChannelId"))
        await self._require_manage(request, channel.guild.id)
        text = _text(payload.get("text"), "text", max_length=1900)
        message = await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        return {"result": f"Сообщение отправлено в #{channel.name}.", "jumpUrl": message.jump_url}

    async def _action_message_embed(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._text_channel(_parse_snowflake(payload.get("textChannelId"), "textChannelId"))
        await self._require_manage(request, channel.guild.id)
        title = _text(payload.get("title"), "title", max_length=256)
        description = _text(payload.get("description"), "description", max_length=4000)
        embed = discord.Embed(title=title, description=description, color=_parse_color(payload.get("color")))
        message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return {"result": f"Embed отправлен в #{channel.name}.", "jumpUrl": message.jump_url}

    async def _action_moderation_clear(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._text_channel(_parse_snowflake(payload.get("textChannelId"), "textChannelId"))
        context = await self._require_manage(request, channel.guild.id)
        amount = _bounded_int(payload.get("amount"), "amount", 1, 200)
        me = channel.guild.me
        permissions = channel.permissions_for(me) if me else None
        if not permissions or not permissions.manage_messages or not permissions.read_message_history:
            raise ApiError(403, "У бота нет прав Manage Messages и Read Message History в этом канале.")
        deleted = await channel.purge(limit=amount)
        await log_mod_action(
            channel.guild.id,
            None,
            "clear",
            self._actor_id(context),
            reason=f"Dashboard API: удалено {len(deleted)} сообщений в #{channel.name}",
            extra={"channel_id": channel.id, "deleted": len(deleted)},
        )
        return {"result": f"Удалено сообщений: {len(deleted)}."}

    async def _action_moderation_kick(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, context = await self._managed_guild(request, guild_id, payload)
        member_id = _parse_snowflake(payload.get("memberId"), "memberId")
        reason = _text(payload.get("reason"), "reason", max_length=512, required=False) or "Dashboard API"
        if guild.me is None or not guild.me.guild_permissions.kick_members:
            raise ApiError(403, "У бота нет права Kick Members.")
        member = await self._fetch_member(guild, member_id)
        if member == guild.me or member == guild.owner:
            raise ApiError(403, "Нельзя кикнуть этого участника.")
        await self._check_actor_hierarchy(guild, context, member)
        if member.top_role >= guild.me.top_role:
            raise ApiError(403, "Роль бота должна быть выше роли участника.")
        await member.kick(reason=reason)
        await log_mod_action(guild.id, member.id, "kick", self._actor_id(context), reason=reason)
        return {"result": f"Участник {member} кикнут."}

    async def _action_moderation_ban(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, context = await self._managed_guild(request, guild_id, payload)
        user_id = _parse_snowflake(payload.get("userId") or payload.get("memberId"), "userId")
        reason = _text(payload.get("reason"), "reason", max_length=512, required=False) or "Dashboard API"
        delete_days = _bounded_int(payload.get("deleteMessageDays", 0), "deleteMessageDays", 0, 7)
        if guild.me is None or not guild.me.guild_permissions.ban_members:
            raise ApiError(403, "У бота нет права Ban Members.")
        member = guild.get_member(user_id)
        if member:
            if member == guild.me or member == guild.owner:
                raise ApiError(403, "Нельзя забанить этого участника.")
            await self._check_actor_hierarchy(guild, context, member)
            if member.top_role >= guild.me.top_role:
                raise ApiError(403, "Роль бота должна быть выше роли участника.")
        await guild.ban(discord.Object(id=user_id), reason=reason, delete_message_seconds=delete_days * 86400)
        await log_mod_action(guild.id, user_id, "ban", self._actor_id(context), reason=reason, extra={"delete_days": delete_days})
        return {"result": f"Пользователь {user_id} забанен."}

    async def _action_moderation_unban(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, context = await self._managed_guild(request, guild_id, payload)
        user_id = _parse_snowflake(payload.get("userId"), "userId")
        reason = _text(payload.get("reason"), "reason", max_length=512, required=False) or "Dashboard API"
        if guild.me is None or not guild.me.guild_permissions.ban_members:
            raise ApiError(403, "У бота нет права Ban Members.")
        await guild.unban(discord.Object(id=user_id), reason=reason)
        await log_mod_action(guild.id, user_id, "unban", self._actor_id(context), reason=reason)
        return {"result": f"Пользователь {user_id} разбанен."}

    async def _action_warning_warn(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, context = await self._managed_guild(request, guild_id, payload)
        member_id = _parse_snowflake(payload.get("memberId"), "memberId")
        reason = _text(payload.get("reason"), "reason", max_length=512, required=False) or "Без причины"
        member = await self._fetch_member(guild, member_id)
        if member == guild.me or member == guild.owner:
            raise ApiError(403, "Нельзя выдать варн этому участнику.")
        await self._check_actor_hierarchy(guild, context, member)
        result = await warn_member(guild, member, self._actor_id(context), reason)
        return {
            "result": f"Варн выдан {member}. Активных варнов: {result['activeCount']}. {result['punishment']}",
            "warning": result["warning"],
            "activeCount": result["activeCount"],
            "tier": result["tier"],
        }

    async def _action_warning_list(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        member_id = _parse_snowflake(payload.get("memberId"), "memberId")
        warnings = await get_member_warnings(guild.id, member_id, active_only=True)
        return {"result": warnings, "activeCount": len(warnings)}

    async def _action_warning_clear(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, context = await self._managed_guild(request, guild_id, payload)
        member_id = _parse_snowflake(payload.get("memberId"), "memberId")
        reason = _text(payload.get("reason"), "reason", max_length=512, required=False) or "Dashboard API"
        removed = await clear_member_warnings(guild.id, member_id, self._actor_id(context), reason)
        await log_mod_action(
            guild.id,
            member_id,
            "clearwarns",
            self._actor_id(context),
            reason=reason,
            extra={"removed": removed},
        )
        return {"result": f"Снято активных варнов: {removed}.", "removed": removed}

    async def _action_warning_config_get(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        return {"result": await get_warn_policy(guild.id)}

    async def _action_warning_config_set(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        try:
            policy = await save_warn_policy(guild.id, payload.get("policy"))
        except ValueError as error:
            raise ApiError(400, str(error)) from None
        return {"result": "Настройки варнов сохранены.", "policy": policy}

    def _music_cog(self) -> Any:
        cog = self.bot.get_cog("Music")
        if cog is None:
            raise ApiError(503, "Music cog не загружен.")
        return cog

    async def _action_music_menu(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._text_channel(_parse_snowflake(payload.get("textChannelId"), "textChannelId"))
        await self._require_manage(request, channel.guild.id)
        return {"result": await self._music_cog().console_send_menu(channel.id)}

    async def _action_music_join(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._voice_channel(_parse_snowflake(payload.get("voiceChannelId"), "voiceChannelId"))
        await self._require_manage(request, channel.guild.id)
        return {"result": await self._music_cog().console_join(channel.id)}

    async def _action_music_play(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._voice_channel(_parse_snowflake(payload.get("voiceChannelId"), "voiceChannelId"))
        await self._require_manage(request, channel.guild.id)
        query = _text(payload.get("query"), "query", max_length=500)
        return {"result": await self._music_cog().console_play(channel.id, query)}

    async def _action_music_guild(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        action_type = _text(payload.get("_actionType"), "type", max_length=80)
        command = action_type.split(".", 1)[1]
        music = self._music_cog()
        if command == "leave":
            return {"result": await music.console_leave(guild.id)}
        if command == "skip":
            return {"result": await music.console_skip(guild.id)}
        if command == "shuffle":
            return {"result": music.console_shuffle(guild.id)}
        if command == "stop":
            return {"result": await music.console_stop(guild.id)}
        if command == "queue":
            return {"result": music.console_queue_text(guild.id)}
        if command == "now":
            return {"result": music.console_now_text(guild.id)}
        raise ApiError(400, "Неизвестное music-действие.")

    async def _action_music_jump(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        position = _bounded_int(payload.get("position"), "position", 1, 10000)
        return {"result": await self._music_cog().console_jump(guild.id, position)}

    async def _action_music_lyrics(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        enabled = _bool_value(payload.get("enabled", True))
        channel_id = _optional_snowflake(payload.get("textChannelId"), "textChannelId") or 0
        return {"result": await self._music_cog().console_lyrics(guild.id, channel_id, enabled)}

    def _rr_cog(self) -> Any:
        cog = self.bot.get_cog("ReactionRoles")
        if cog is None:
            raise ApiError(503, "ReactionRoles cog не загружен.")
        return cog

    async def _action_rr_create(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._text_channel(_parse_snowflake(payload.get("textChannelId"), "textChannelId"))
        await self._require_manage(request, channel.guild.id)
        title = _text(payload.get("title"), "title", max_length=256)
        description = _text(payload.get("description"), "description", max_length=2000)
        raw_mappings = payload.get("mappings") or []
        if not isinstance(raw_mappings, list) or not raw_mappings:
            raise ApiError(400, "mappings должен быть непустым массивом.")
        mappings = []
        for item in raw_mappings[:25]:
            if not isinstance(item, dict):
                raise ApiError(400, "Каждый mapping должен быть объектом.")
            emoji = _safe_emoji(item.get("emoji"))
            role_id = _parse_snowflake(item.get("roleId"), "roleId")
            mappings.append(f"{emoji}={role_id}")
        result = await self._rr_cog().console_create(channel.id, title, description, "; ".join(mappings))
        return {"result": result}

    async def _action_rr_add(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        channel = self._text_channel(_parse_snowflake(payload.get("textChannelId"), "textChannelId"))
        await self._require_manage(request, channel.guild.id)
        message_id = _parse_snowflake(payload.get("messageId"), "messageId")
        emoji = _safe_emoji(payload.get("emoji"))
        role_id = _parse_snowflake(payload.get("roleId"), "roleId")
        return {"result": await self._rr_cog().console_add(channel.id, message_id, emoji, str(role_id))}

    async def _action_rr_remove(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        message_id = _parse_snowflake(payload.get("messageId"), "messageId")
        emoji = _safe_emoji(payload.get("emoji"))
        return {"result": await self._rr_cog().console_remove(guild.id, message_id, emoji)}

    async def _action_rr_list(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        return {"result": await self._rr_cog().console_list(guild.id)}

    async def _action_config_view(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        return {"result": await get_guild_settings(guild.id)}

    async def _action_config_set(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        key = _text(payload.get("key"), "key", max_length=64)
        if not SETTING_KEY_RE.fullmatch(key):
            raise ApiError(400, "key может содержать только a-z, A-Z, 0-9 и _.")
        value = payload.get("value")
        if isinstance(value, str) and value.casefold() in {"true", "false", "on", "off", "yes", "no", "1", "0", "да", "нет"}:
            value = _bool_value(value)
        await set_guild_setting(guild.id, key, value)
        return {"result": f"Настройка {key} сохранена."}

    async def _action_config_delete(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        guild, _ = await self._managed_guild(request, guild_id, payload)
        key = _text(payload.get("key"), "key", max_length=64)
        if not SETTING_KEY_RE.fullmatch(key):
            raise ApiError(400, "key может содержать только a-z, A-Z, 0-9 и _.")
        await delete_guild_setting(guild.id, key)
        return {"result": f"Настройка {key} удалена."}

    async def _action_words(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        await self._managed_guild(request, guild_id, payload)
        words = load_words()
        return {"result": format_words(words) if words else "Список пуст."}

    async def _action_add_words(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        await self._managed_guild(request, guild_id, payload)
        parsed = parse_words(_text(payload.get("words"), "words", max_length=1000))
        if not parsed:
            raise ApiError(400, "Список слов пустой.")
        words = load_words()
        existing = set(words)
        added = [word for word in parsed if word not in existing]
        if added:
            words.extend(added)
            save_words(words)
        return {"result": f"Добавлено: {len(added)}"}

    async def _action_del_words(self, request: web.Request, guild_id: Optional[int], payload: Dict[str, Any]) -> Dict[str, Any]:
        await self._managed_guild(request, guild_id, payload)
        parsed = parse_words(_text(payload.get("words"), "words", max_length=1000))
        if not parsed:
            raise ApiError(400, "Список слов пустой.")
        words = load_words()
        removed = {word for word in parsed if word in set(words)}
        if removed:
            save_words([word for word in words if word not in removed])
        return {"result": f"Удалено: {len(removed)}"}


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DashboardAPI(bot))
