import asyncio
import contextlib
import html
import random
import re
import traceback
from urllib.parse import urlencode
from typing import Dict, List, Optional
import shutil

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


FFMPEG_OPTIONS = {
    "before_options": (
        "-nostdin -reconnect 1 -reconnect_streamed 1 "
        "-reconnect_on_network_error 1 -reconnect_on_http_error 4xx,5xx "
        "-reconnect_delay_max 15 -rw_timeout 20000000"
    ),
    "options": "-vn -loglevel warning",
}

MAX_PLAYLIST_ITEMS = 1000
QUEUE_PAGE_SIZE = 10
TEMP_MESSAGE_DELETE_AFTER = 120
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
DEFAULT_PLAYBACK_SPEED = 1.0
MIN_PLAYBACK_SPEED = 0.25
MAX_PLAYBACK_SPEED = 4.0
LYRICS_EARLY_OFFSET_SECONDS = 1.0
LYRICS_LANGUAGE_PRIORITY = (
    "ru",
    "ru-RU",
    "ru-orig",
    "en",
    "en-US",
    "en-orig",
)
WEBVTT_TIMING_RE = re.compile(
    r"(?P<start>(?:\d+:)?\d{2}:\d{2}[\.,]\d{3})\s+-->\s+"
    r"(?P<end>(?:\d+:)?\d{2}:\d{2}[\.,]\d{3})"
)
LRC_TIMESTAMP_RE = re.compile(r"\[(?P<minutes>\d{1,3}):(?P<seconds>\d{2}(?:[\.:]\d{1,3})?)\]")
ARTIST_TITLE_RE = re.compile(r"\s+[-–—]\s+")
WEBVTT_TAG_RE = re.compile(r"<[^>]+>")
WEBVTT_INLINE_TIMESTAMP_RE = re.compile(r"<(?:\d+:)?\d{2}:\d{2}[\.,]\d{3}>")

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "extract_flat": False,
    "ignoreerrors": True,
    "socket_timeout": 30,
    "source_address": "0.0.0.0",
    "writesubtitles": True,
    "writeautomaticsub": True,
    "subtitlesformat": "vtt",
}

YDL_PLAYLIST_OPTIONS = {
    **YDL_OPTIONS,
    "noplaylist": False,
    "extract_flat": "in_playlist",
    "playlistend": MAX_PLAYLIST_ITEMS,
}

IDLE_DISCONNECT_SECONDS = 180


def is_url_query(query: str) -> bool:
    normalized = query.strip().lower()
    return normalized.startswith(("http://", "https://"))


async def send_temp_response(interaction: discord.Interaction, *args, **kwargs):
    kwargs.setdefault("delete_after", TEMP_MESSAGE_DELETE_AFTER)
    return await interaction.response.send_message(*args, **kwargs)


async def send_temp_followup(interaction: discord.Interaction, *args, **kwargs):
    message = await interaction.followup.send(*args, wait=True, **kwargs)
    if message:
        await message.delete(delay=TEMP_MESSAGE_DELETE_AFTER)
    return message


class MusicControlView(discord.ui.View):
    def __init__(self, cog: "Music", guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id

    async def _get_voice(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        if not interaction.guild:
            await send_temp_response(interaction, "Эта кнопка работает только на сервере", ephemeral=True)
            return None

        voice = interaction.guild.voice_client
        if not voice or not voice.is_connected():
            await send_temp_response(interaction, "❌ Я не подключен к голосовому каналу", ephemeral=True)
            return None

        return voice

    @discord.ui.button(label="🔌 Войти", style=discord.ButtonStyle.secondary)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button join")
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await send_temp_response(interaction, "Эта кнопка работает только на сервере", ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await send_temp_response(interaction, "❌ Ты должен быть в голосовом канале", ephemeral=True)

        try:
            voice = interaction.guild.voice_client
            if voice and voice.is_connected():
                await voice.move_to(interaction.user.voice.channel)
            else:
                await self.cog._connect_to(interaction.user.voice.channel)
            await send_temp_response(interaction, f"✅ Подключился к каналу: {interaction.user.voice.channel.mention}", ephemeral=True)
        except Exception as e:
            await send_temp_response(interaction, f"❌ Ошибка подключения: {self.cog._format_voice_connect_error(e)}", ephemeral=True)

    @discord.ui.button(label="🚪 Выйти", style=discord.ButtonStyle.secondary)
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button leave")
        voice = await self._get_voice(interaction)
        if not voice:
            return

        self.cog._cancel_idle_disconnect(self.guild_id)
        await self.cog._stop_lyrics(self.guild_id)
        self.cog.queues.pop(self.guild_id, None)
        self.cog.now_playing.pop(self.guild_id, None)
        await voice.disconnect()
        await send_temp_response(interaction, "✅ Отключился от голосового канала", ephemeral=True)

    @discord.ui.button(label="➕ Трек", style=discord.ButtonStyle.success)
    async def add_track_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button play query modal")
        await interaction.response.send_modal(PlayQueryModal(self.cog))

    @discord.ui.button(label="▶️ Включить", style=discord.ButtonStyle.success)
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button play/resume")
        if not interaction.guild:
            await send_temp_response(interaction, "Эта кнопка работает только на сервере", ephemeral=True)
            return

        guild_id = self.guild_id
        voice = interaction.guild.voice_client
        deferred = False

        if voice and voice.is_connected():
            if voice.is_paused():
                self.cog._cancel_idle_disconnect(guild_id)
                voice.resume()
                self.cog._mark_track_resumed(guild_id)
                await send_temp_response(interaction, "▶️ Воспроизведение продолжено", ephemeral=True)
                return

            if voice.is_playing():
                await send_temp_response(interaction, "▶️ Музыка уже играет", ephemeral=True)
                return

            if not self.cog.get_queue(guild_id):
                await send_temp_response(interaction, "❌ Очередь пустая", ephemeral=True)
                return
        else:
            if not self.cog.get_queue(guild_id):
                await send_temp_response(interaction, "❌ Очередь пустая", ephemeral=True)
                return

            if isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel:
                await interaction.response.defer(ephemeral=True)
                deferred = True
                try:
                    voice = await self.cog._connect_to(interaction.user.voice.channel)
                except Exception as e:
                    error_text = self.cog._format_voice_connect_error(e)
                    await send_temp_followup(
                        interaction,
                        f"❌ Не удалось подключиться к каналу: {error_text}",
                        ephemeral=True,
                    )
                    return

        if not deferred:
            await interaction.response.defer(ephemeral=True)
        self.cog._cancel_idle_disconnect(guild_id)
        await self.cog._play_next(guild_id, voice)

        current = self.cog.now_playing.get(guild_id)
        if current:
            await send_temp_followup(interaction, f"▶️ Включил: **{current['title']}**", ephemeral=True)
        else:
            await send_temp_followup(interaction, "❌ Не удалось начать воспроизведение", ephemeral=True)

    @discord.ui.button(label="⏸️ Пауза", style=discord.ButtonStyle.secondary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button pause")
        voice = await self._get_voice(interaction)
        if not voice:
            return

        if voice.is_paused():
            return await send_temp_response(interaction, "⏸️ Музыка уже на паузе", ephemeral=True)

        if not voice.is_playing():
            return await send_temp_response(interaction, "❌ Сейчас ничего не играет", ephemeral=True)

        voice.pause()
        self.cog._mark_track_paused(self.guild_id)
        self.cog._cancel_idle_disconnect(self.guild_id)
        await send_temp_response(interaction, "⏸️ Музыка поставлена на паузу", ephemeral=True)

    @discord.ui.button(label="🗑️ Очистить", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button clear")
        voice = await self._get_voice(interaction)
        if not voice:
            return

        self.cog._cancel_idle_disconnect(self.guild_id)
        await self.cog._stop_lyrics(self.guild_id)
        self.cog.queues.pop(self.guild_id, None)
        self.cog.now_playing.pop(self.guild_id, None)
        voice.stop()
        self.cog._schedule_idle_disconnect(self.guild_id)

        await send_temp_response(interaction, "🗑️ Очередь очищена, музыка остановлена", ephemeral=True)

    @discord.ui.button(label="⏭️ Следующая", style=discord.ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button skip")
        voice = await self._get_voice(interaction)
        if not voice:
            return

        if not (voice.is_playing() or voice.is_paused()):
            return await send_temp_response(interaction, "❌ Сейчас ничего не играет", ephemeral=True)

        voice.stop()
        await send_temp_response(interaction, "⏭️ Трек пропущен", ephemeral=True)

    @discord.ui.button(label="🔉 Тише", style=discord.ButtonStyle.secondary)
    async def volume_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button volume down")
        volume = self.cog.get_volume(self.guild_id)
        volume = max(0.0, volume - 0.1)
        self.cog.set_volume(self.guild_id, volume)
        await send_temp_response(interaction, f"🔉 Громкость: {int(volume * 100)}%", ephemeral=True)

    @discord.ui.button(label="🔊 Громче", style=discord.ButtonStyle.secondary)
    async def volume_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button volume up")
        volume = self.cog.get_volume(self.guild_id)
        volume = min(2.0, volume + 0.1)
        self.cog.set_volume(self.guild_id, volume)
        await send_temp_response(interaction, f"🔊 Громкость: {int(volume * 100)}%", ephemeral=True)

    @discord.ui.button(label="📜 Список песен", style=discord.ButtonStyle.success)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button queue")
        embed = self.cog.create_queue_embed(self.guild_id)
        view = QueuePageView(self.cog, self.guild_id)
        await send_temp_response(interaction, embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔀 Перемешать", style=discord.ButtonStyle.primary)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button shuffle")
        result = self.cog.shuffle_queue(self.guild_id)
        await send_temp_response(interaction, result, ephemeral=True)

    @discord.ui.button(label="📍 Сейчас", style=discord.ButtonStyle.secondary)
    async def now_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button now")
        embed = self.cog.create_now_embed(self.guild_id)
        await send_temp_response(interaction, embed=embed, ephemeral=True)

    @discord.ui.button(label="⏱️ Перемотка", style=discord.ButtonStyle.primary)
    async def seek_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button seek modal")
        await interaction.response.send_modal(SeekModal(self.cog))

    @discord.ui.button(label="⚙️ Скорость", style=discord.ButtonStyle.primary)
    async def speed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button speed modal")
        await interaction.response.send_modal(SpeedModal(self.cog))

    @discord.ui.button(label="🎤 Субтитры", style=discord.ButtonStyle.secondary)
    async def lyrics_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button lyrics toggle")
        enabled = self.guild_id not in self.cog.lyrics_channels
        await self.cog.set_lyrics_enabled(interaction, enabled)


class QueueStartModal(discord.ui.Modal, title="Перейти к номеру"):
    position = discord.ui.TextInput(
        label="Номер песни",
        placeholder="240",
        required=True,
        max_length=5,
    )

    def __init__(self, cog: "Music", guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            position = int(str(self.position.value).strip())
        except ValueError:
            return await send_temp_response(interaction, "❌ Введи номер песни числом.", ephemeral=True)

        self.cog.log_music_action(interaction, "modal queue start", str(position))
        embed = self.cog.create_queue_embed(self.guild_id, start=position)
        view = QueuePageView(self.cog, self.guild_id, start=position)
        await send_temp_response(interaction, embed=embed, view=view, ephemeral=True)


class QueuePlayModal(discord.ui.Modal, title="Включить песню"):
    position = discord.ui.TextInput(
        label="Номер песни",
        placeholder="240",
        required=True,
        max_length=5,
    )

    def __init__(self, cog: "Music", guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            position = int(str(self.position.value).strip())
        except ValueError:
            return await send_temp_response(interaction, "❌ Введи номер песни числом.", ephemeral=True)

        self.cog.log_music_action(interaction, "modal play number", str(position))
        await self.cog.jump_to_position(interaction, position)


class PlayQueryModal(discord.ui.Modal, title="Добавить музыку"):
    query = discord.ui.TextInput(
        label="Ссылка или название",
        placeholder="https://... или название песни",
        required=True,
        max_length=300,
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        query = str(self.query.value).strip()
        if not query:
            return await send_temp_response(interaction, "❌ Запрос не может быть пустым.", ephemeral=True)

        self.cog.log_music_action(interaction, "modal play query", query)
        await self.cog.play_query_from_menu(interaction, query)


class SeekModal(discord.ui.Modal, title="Перемотать песню"):
    seconds = discord.ui.TextInput(
        label="Секунда",
        placeholder="90",
        required=True,
        max_length=8,
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = float(str(self.seconds.value).replace(",", ".").strip())
        except ValueError:
            return await send_temp_response(interaction, "❌ Введи секунды числом.", ephemeral=True)

        self.cog.log_music_action(interaction, "modal seek", f"{seconds:g}s")
        await self.cog.seek_to(interaction, seconds)


class SpeedModal(discord.ui.Modal, title="Скорость воспроизведения"):
    speed = discord.ui.TextInput(
        label="Скорость x",
        placeholder="0.25 или 2",
        required=True,
        max_length=5,
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            speed = float(str(self.speed.value).replace(",", ".").strip())
        except ValueError:
            return await send_temp_response(interaction, "❌ Введи скорость числом.", ephemeral=True)

        self.cog.log_music_action(interaction, "modal speed", f"{speed:g}x")
        await self.cog.set_playback_speed(interaction, speed)


class QueuePageView(discord.ui.View):
    def __init__(self, cog: "Music", guild_id: int, start: int = 1):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.start = self.cog.normalize_queue_start(guild_id, start)
        self._sync_buttons()

    def _sync_buttons(self):
        total = self.cog.get_visible_queue_item_count(self.guild_id)
        max_start = self.cog.get_max_queue_start(self.guild_id)
        self.previous_button.disabled = total <= QUEUE_PAGE_SIZE or self.start <= 1
        self.next_button.disabled = total <= QUEUE_PAGE_SIZE or self.start >= max_start

    async def _edit_page(self, interaction: discord.Interaction):
        self.start = self.cog.normalize_queue_start(self.guild_id, self.start)
        self._sync_buttons()
        embed = self.cog.create_queue_embed(self.guild_id, start=self.start)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button queue previous")
        self.start -= QUEUE_PAGE_SIZE
        await self._edit_page(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button queue next")
        self.start += QUEUE_PAGE_SIZE
        await self._edit_page(interaction)

    @discord.ui.button(label="🔢 К номеру", style=discord.ButtonStyle.primary)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button queue number modal")
        await interaction.response.send_modal(QueueStartModal(self.cog, self.guild_id))

    @discord.ui.button(label="▶️ Играть номер", style=discord.ButtonStyle.success)
    async def play_number_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.log_music_action(interaction, "button queue play number modal")
        await interaction.response.send_modal(QueuePlayModal(self.cog, self.guild_id))


class Music(commands.Cog):
    """Модуль музыки для Discord бота: YouTube, YouTube Music, Twitch, VK."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: Dict[int, List[dict]] = {}
        self.now_playing: Dict[int, dict] = {}
        self.idle_disconnect_tasks: Dict[int, asyncio.Task] = {}
        self.lyrics_channels: Dict[int, int] = {}
        self.lyrics_tasks: Dict[int, asyncio.Task] = {}
        self.lyrics_messages: Dict[int, discord.Message] = {}
        self.volumes: Dict[int, float] = {}
        self.speeds: Dict[int, float] = {}
        self.play_next_locks: Dict[int, asyncio.Lock] = {}
        self.suppressed_after_callbacks: set[int] = set()

    def get_volume(self, guild_id: int) -> float:
        return self.volumes.get(guild_id, 1.0)

    def set_volume(self, guild_id: int, volume: float):
        self.volumes[guild_id] = volume

        guild = self.bot.get_guild(guild_id)
        voice = guild.voice_client if guild else None
        if voice and voice.source and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = volume

    def get_speed(self, guild_id: int) -> float:
        return self.speeds.get(guild_id, DEFAULT_PLAYBACK_SPEED)

    def set_speed_value(self, guild_id: int, speed: float) -> float:
        speed = max(MIN_PLAYBACK_SPEED, min(MAX_PLAYBACK_SPEED, float(speed)))
        self.speeds[guild_id] = speed
        return speed

    def _mark_track_paused(self, guild_id: int):
        track = self.now_playing.get(guild_id)
        if track and not track.get("pause_started_at"):
            track["pause_started_at"] = self.bot.loop.time()

    def _mark_track_resumed(self, guild_id: int):
        track = self.now_playing.get(guild_id)
        if not track:
            return

        pause_started_at = track.pop("pause_started_at", None)
        if pause_started_at:
            track["paused_total"] = track.get("paused_total", 0.0) + max(
                0.0,
                self.bot.loop.time() - pause_started_at,
            )

    def _track_elapsed(self, track: dict) -> float:
        started_at = track.get("started_at")
        if not started_at:
            return 0.0

        paused_total = track.get("paused_total", 0.0)
        pause_started_at = track.get("pause_started_at")
        if pause_started_at:
            paused_total += max(0.0, self.bot.loop.time() - pause_started_at)

        wall_elapsed = max(0.0, self.bot.loop.time() - started_at - paused_total)
        media_start = track.get("media_start", 0.0)
        speed = track.get("speed", DEFAULT_PLAYBACK_SPEED)
        return max(0.0, media_start + wall_elapsed * speed)

    def get_queue(self, guild_id: int) -> List[dict]:
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def shuffle_queue(self, guild_id: int) -> str:
        queue = self.get_queue(guild_id)
        if len(queue) < 2:
            return "❌ Для перемешивания нужно минимум 2 трека в очереди."

        random.shuffle(queue)
        return f"🔀 Очередь перемешана. Треков в очереди: {len(queue)}."

    def get_play_next_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.play_next_locks:
            self.play_next_locks[guild_id] = asyncio.Lock()
        return self.play_next_locks[guild_id]

    def cog_unload(self):
        for task in self.idle_disconnect_tasks.values():
            task.cancel()
        for task in self.lyrics_tasks.values():
            task.cancel()
        self.queues.clear()
        self.now_playing.clear()
        self.idle_disconnect_tasks.clear()
        self.lyrics_channels.clear()
        self.lyrics_tasks.clear()
        self.lyrics_messages.clear()
        self.volumes.clear()
        self.speeds.clear()
        self.play_next_locks.clear()
        self.suppressed_after_callbacks.clear()

    def _cancel_idle_disconnect(self, guild_id: int):
        task = self.idle_disconnect_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    def _schedule_idle_disconnect(self, guild_id: int):
        self._cancel_idle_disconnect(guild_id)

        async def disconnect_when_idle():
            try:
                await asyncio.sleep(IDLE_DISCONNECT_SECONDS)
                guild = self.bot.get_guild(guild_id)
                voice = guild.voice_client if guild else None
                queue = self.get_queue(guild_id)

                if (
                    voice
                    and voice.is_connected()
                    and not queue
                    and not voice.is_playing()
                    and not voice.is_paused()
                ):
                    print(f"[Music] Очередь пустая {IDLE_DISCONNECT_SECONDS} сек, отключаемся")
                    await voice.disconnect()
                    await self._stop_lyrics(guild_id)
                    self.queues.pop(guild_id, None)
                    self.now_playing.pop(guild_id, None)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[Music] Ошибка отложенного отключения: {e}")
            finally:
                current_task = asyncio.current_task()
                if self.idle_disconnect_tasks.get(guild_id) is current_task:
                    self.idle_disconnect_tasks.pop(guild_id, None)

        task = self.bot.loop.create_task(disconnect_when_idle())
        self.idle_disconnect_tasks[guild_id] = task

    async def _connect_to(self, channel: discord.abc.Connectable) -> discord.VoiceClient:
        return await channel.connect(timeout=30.0, reconnect=False, self_deaf=True)

    def _format_voice_connect_error(self, error: Exception) -> str:
        if isinstance(error, discord.ConnectionClosed) and getattr(error, "code", None) == 4017:
            return (
                "Discord отклонил voice-подключение: нужен DAVE/E2EE. "
                "Перезапусти бота и убедись, что установлен discord.py[voice]>=2.7.1."
            )
        return str(error)

    def _normalize_info(self, info: Optional[dict]) -> Optional[dict]:
        if not info:
            return None

        entries = info.get("entries")
        if entries is not None:
            for entry in entries:
                if entry:
                    return entry
            return None

        return info

    @staticmethod
    def _is_youtube_entry(info: dict) -> bool:
        source = " ".join(
            str(info.get(key, ""))
            for key in ("extractor", "extractor_key", "ie_key")
        ).lower()
        return "youtube" in source

    def _entry_url(self, info: dict, fallback_query: str) -> str:
        webpage_url = info.get("webpage_url") or info.get("original_url")
        if webpage_url:
            return webpage_url

        url = info.get("url")
        if url:
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
            if self._is_youtube_entry(info) and info.get("id"):
                return f"https://www.youtube.com/watch?v={info['id']}"
            return str(url)

        if self._is_youtube_entry(info) and info.get("id"):
            return f"https://www.youtube.com/watch?v={info['id']}"

        return fallback_query

    def _track_from_info(
        self,
        info: Optional[dict],
        requester: discord.Member,
        fallback_query: str,
        voice_channel_id: Optional[int] = None,
    ) -> Optional[dict]:
        if not info:
            return None

        track = {
            "title": info.get("title") or info.get("fulltitle") or "Неизвестный трек",
            "url": self._entry_url(info, fallback_query),
            "duration": info.get("duration"),
            "requester": requester,
        }
        if voice_channel_id is not None:
            track["voice_channel_id"] = voice_channel_id
        return track

    def _tracks_from_info(
        self,
        info: Optional[dict],
        requester: discord.Member,
        fallback_query: str,
        voice_channel_id: Optional[int] = None,
    ) -> List[dict]:
        if not info:
            return []

        entries = info.get("entries")
        if entries is None:
            track = self._track_from_info(info, requester, fallback_query, voice_channel_id)
            return [track] if track else []

        tracks = []
        for entry in entries:
            track = self._track_from_info(entry, requester, fallback_query, voice_channel_id)
            if track:
                tracks.append(track)

        return tracks

    @staticmethod
    def _format_added_tracks_message(tracks: List[dict], source_title: Optional[str] = None) -> str:
        if len(tracks) == 1:
            return f"✅ Добавлено в очередь: **{tracks[0]['title']}**"

        source = f" из **{source_title}**" if source_title else ""
        preview = "\n".join(f"{index}. **{track['title']}**" for index, track in enumerate(tracks[:5], 1))
        if len(tracks) > 5:
            preview += f"\n... и ещё {len(tracks) - 5} треков"
        if len(tracks) >= MAX_PLAYLIST_ITEMS:
            preview += f"\nДобавлены первые {MAX_PLAYLIST_ITEMS} треков."

        return f"✅ Добавлено треков{source}: **{len(tracks)}**\n{preview}"

    def _get_stream_url(self, info: dict) -> Optional[str]:
        if info.get("url"):
            return info["url"]

        formats = info.get("formats") or []
        for item in formats:
            if item.get("url") and item.get("acodec") != "none":
                return item["url"]

        return None

    async def _extract_info(self, query: str, options: dict, timeout: float = 30.0) -> Optional[dict]:
        if yt_dlp is None:
            print("[Music] yt-dlp не установлен")
            return None

        loop = asyncio.get_running_loop()

        def extract():
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(query, download=False)
            except Exception as e:
                print(f"[Music] Ошибка yt-dlp: {e}")
                return None

        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, extract),
                timeout=timeout,
            )
            return info
        except asyncio.TimeoutError:
            print(f"[Music] Timeout при поиске: {query}")
            return None

    async def _extract_track_info(self, query: str) -> Optional[dict]:
        """Извлечь информацию о треке/видео через yt-dlp."""
        info = await self._extract_info(query, YDL_OPTIONS)
        return self._normalize_info(info)

    async def _extract_queue_info(self, query: str) -> Optional[dict]:
        """Извлечь одиночный трек или список треков для очереди."""
        return await self._extract_info(query, YDL_PLAYLIST_OPTIONS, timeout=120.0)

    @staticmethod
    def _parse_webvtt_timestamp(value: str) -> float:
        value = value.replace(",", ".")
        parts = value.split(":")
        seconds = float(parts[-1])
        minutes = int(parts[-2])
        hours = int(parts[-3]) if len(parts) == 3 else 0
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _clean_caption_text(text: str) -> str:
        text = WEBVTT_INLINE_TIMESTAMP_RE.sub("", text)
        text = WEBVTT_TAG_RE.sub("", text)
        text = html.unescape(text)
        return " ".join(text.split())

    def _parse_webvtt(self, content: str) -> List[tuple[float, str]]:
        entries = []
        previous_text = ""

        for block in re.split(r"\n\s*\n", content.replace("\r\n", "\n")):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines or lines[0] in {"WEBVTT", "STYLE", "REGION"} or lines[0].startswith("NOTE"):
                continue

            timing_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
            if timing_index is None:
                continue

            match = WEBVTT_TIMING_RE.search(lines[timing_index])
            if not match:
                continue

            caption_text = self._clean_caption_text(" ".join(lines[timing_index + 1:]))
            if not caption_text or caption_text == previous_text:
                continue

            entries.append((self._parse_webvtt_timestamp(match.group("start")), caption_text))
            previous_text = caption_text

        return sorted(entries, key=lambda item: item[0])

    @staticmethod
    def _ordered_caption_languages(captions: dict) -> List[str]:
        languages = list(captions)
        ordered = []

        for preferred in LYRICS_LANGUAGE_PRIORITY:
            for language in languages:
                if language in ordered:
                    continue
                normalized = language.lower()
                preferred_normalized = preferred.lower()
                if normalized == preferred_normalized or normalized.startswith(f"{preferred_normalized}-"):
                    ordered.append(language)

        ordered.extend(language for language in languages if language not in ordered)
        return ordered

    def _find_webvtt_subtitle_url(self, info: dict) -> Optional[str]:
        for captions in (info.get("subtitles") or {}, info.get("automatic_captions") or {}):
            for language in self._ordered_caption_languages(captions):
                formats = captions.get(language) or []
                for item in formats:
                    url = item.get("url")
                    extension = (item.get("ext") or "").lower()
                    if url and extension in {"vtt", "webvtt"}:
                        return url
        return None

    async def _fetch_subtitle_text(self, url: str) -> Optional[str]:
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status >= 400:
                        print(f"[Music] Не удалось загрузить субтитры: HTTP {response.status}")
                        return None
                    return await response.text()
        except Exception as e:
            print(f"[Music] Ошибка загрузки субтитров: {e}")
            return None

    @staticmethod
    def _parse_lrc_timestamp(minutes: str, seconds: str) -> float:
        return int(minutes) * 60 + float(seconds.replace(",", "."))

    def _parse_lrc(self, content: str) -> List[tuple[float, str]]:
        entries = []
        previous_text = ""

        for line in content.splitlines():
            matches = list(LRC_TIMESTAMP_RE.finditer(line))
            if not matches:
                continue

            text = LRC_TIMESTAMP_RE.sub("", line).strip()
            text = html.unescape(" ".join(text.split()))
            if not text or text == previous_text:
                continue

            for match in matches:
                entries.append((
                    self._parse_lrc_timestamp(match.group("minutes"), match.group("seconds")),
                    text,
                ))
            previous_text = text

        return sorted(entries, key=lambda item: item[0])

    @staticmethod
    def _lyrics_query_parts(info: dict) -> tuple[str, Optional[str]]:
        title = (
            info.get("track")
            or info.get("alt_title")
            or info.get("title")
            or ""
        ).strip()
        artist = (
            info.get("artist")
            or info.get("creator")
            or info.get("uploader")
            or ""
        ).strip() or None

        if title and not artist:
            parts = ARTIST_TITLE_RE.split(title, maxsplit=1)
            if len(parts) == 2 and all(parts):
                artist, title = parts[0].strip(), parts[1].strip()

        title = re.sub(r"\s+\(.*?(official|video|audio|lyrics|music).*?\)\s*$", "", title, flags=re.I).strip()
        title = re.sub(r"\s+\[.*?(official|video|audio|lyrics|music).*?\]\s*$", "", title, flags=re.I).strip()

        return title, artist

    async def _fetch_lrclib_lyrics(self, info: dict) -> List[tuple[float, str]]:
        title, artist = self._lyrics_query_parts(info)
        if not title:
            return []

        search_queries = []
        if artist:
            search_queries.append({"track_name": title, "artist_name": artist})
            search_queries.append({"q": f"{artist} {title}"})
        search_queries.append({"q": title})

        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "discord-music-bot/1.0"}

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                for params in search_queries:
                    url = f"{LRCLIB_SEARCH_URL}?{urlencode(params)}"
                    async with session.get(url) as response:
                        if response.status >= 400:
                            continue

                        results = await response.json(content_type=None)
                        if not isinstance(results, list):
                            continue

                        for item in results:
                            synced = item.get("syncedLyrics")
                            if synced:
                                parsed = self._parse_lrc(synced)
                                if parsed:
                                    print(f"[Music] Субтитры найдены через LRCLIB: {item.get('trackName', title)}")
                                    return parsed
        except Exception as e:
            print(f"[Music] Ошибка LRCLIB: {e}")

        return []

    async def _extract_timed_lyrics(self, info: dict) -> List[tuple[float, str]]:
        subtitle_url = self._find_webvtt_subtitle_url(info)
        if subtitle_url:
            content = await self._fetch_subtitle_text(subtitle_url)
            if content:
                parsed = self._parse_webvtt(content)
                if parsed:
                    return parsed

        return await self._fetch_lrclib_lyrics(info)

    async def _stop_lyrics(self, guild_id: int):
        task = self.lyrics_tasks.pop(guild_id, None)
        current_task = asyncio.current_task()
        if task and task is not current_task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        message = self.lyrics_messages.pop(guild_id, None)
        if message:
            with contextlib.suppress(discord.HTTPException, discord.NotFound):
                await message.delete()

    def _get_lyrics_channel(self, guild_id: int) -> Optional[discord.abc.Messageable]:
        channel_id = self.lyrics_channels.get(guild_id)
        if not channel_id:
            return None

        channel = self.bot.get_channel(channel_id)
        if channel:
            return channel

        guild = self.bot.get_guild(guild_id)
        if guild and hasattr(guild, "get_channel_or_thread"):
            return guild.get_channel_or_thread(channel_id)

        return None

    def _format_lyrics_message(self, track: dict, line: str) -> str:
        title = self._shorten(track.get("title", "Трек"), 80)
        line = self._shorten(line, 1800)
        return f"🎤 **{title}**\n{line}"

    def _start_lyrics_task(self, guild_id: int, track: dict, info: dict):
        channel = self._get_lyrics_channel(guild_id)
        if not channel:
            return

        task = self.bot.loop.create_task(self._lyrics_worker(guild_id, channel, track, info))
        self.lyrics_tasks[guild_id] = task

    async def _lyrics_worker(
        self,
        guild_id: int,
        channel: discord.abc.Messageable,
        track: dict,
        info: dict,
    ):
        message = None
        try:
            message = await channel.send(f"🎤 Ищу субтитры: **{self._shorten(track['title'])}**")
            self.lyrics_messages[guild_id] = message

            entries = await self._extract_timed_lyrics(info)
            if self.now_playing.get(guild_id) is not track:
                return

            if not entries:
                await message.edit(content=f"🎤 Субтитры для **{self._shorten(track['title'])}** не найдены.")
                self.lyrics_messages.pop(guild_id, None)
                await message.delete(delay=TEMP_MESSAGE_DELETE_AFTER)
                return

            start_index = 0
            current_text = None
            elapsed = self._track_elapsed(track)
            for index, (timestamp, text) in enumerate(entries):
                display_at = max(0.0, timestamp - LYRICS_EARLY_OFFSET_SECONDS)
                if display_at <= elapsed:
                    start_index = index + 1
                    current_text = text
                else:
                    break

            if current_text:
                await message.edit(content=self._format_lyrics_message(track, current_text))

            for index in range(start_index, len(entries)):
                timestamp, text = entries[index]

                while self.now_playing.get(guild_id) is track:
                    voice = self.bot.get_guild(guild_id).voice_client if self.bot.get_guild(guild_id) else None
                    if not voice or not voice.is_connected():
                        return

                    display_at = max(0.0, timestamp - LYRICS_EARLY_OFFSET_SECONDS)
                    wait_time = display_at - self._track_elapsed(track)
                    if wait_time <= 0:
                        break

                    await asyncio.sleep(min(wait_time, 0.5))

                if self.now_playing.get(guild_id) is not track:
                    return

                await message.edit(content=self._format_lyrics_message(track, text))

            while self.now_playing.get(guild_id) is track:
                voice = self.bot.get_guild(guild_id).voice_client if self.bot.get_guild(guild_id) else None
                if not voice or not voice.is_connected() or (not voice.is_playing() and not voice.is_paused()):
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        except discord.HTTPException as e:
            print(f"[Music] Ошибка сообщения субтитров: {e}")
        except Exception as e:
            print(f"[Music] Ошибка субтитров: {e}")
            traceback.print_exc()
        finally:
            current_task = asyncio.current_task()
            if self.lyrics_tasks.get(guild_id) is current_task:
                self.lyrics_tasks.pop(guild_id, None)

            if message and self.lyrics_messages.get(guild_id) is message:
                self.lyrics_messages.pop(guild_id, None)
                with contextlib.suppress(discord.HTTPException, discord.NotFound):
                    await message.delete()

    @staticmethod
    def _atempo_filter(speed: float) -> Optional[str]:
        speed = max(MIN_PLAYBACK_SPEED, min(MAX_PLAYBACK_SPEED, speed))
        if abs(speed - DEFAULT_PLAYBACK_SPEED) < 0.001:
            return None

        filters = []
        remaining = speed
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        filters.append(f"atempo={remaining:.3f}".rstrip("0").rstrip("."))
        return ",".join(filters)

    def _ffmpeg_options(self, seek_seconds: float = 0.0, speed: float = DEFAULT_PLAYBACK_SPEED) -> dict:
        before_options = FFMPEG_OPTIONS["before_options"]
        if seek_seconds > 0:
            before_options = f"{before_options} -ss {seek_seconds:.3f}"

        options = FFMPEG_OPTIONS["options"]
        speed_filter = self._atempo_filter(speed)
        if speed_filter:
            options = f"-vn -filter:a {speed_filter} -loglevel warning"

        return {
            "before_options": before_options,
            "options": options,
        }

    async def _create_audio_source(
        self,
        url: str,
        guild_id: int,
        *,
        seek_seconds: float = 0.0,
        speed: Optional[float] = None,
    ) -> Optional[discord.AudioSource]:
        try:
            playback_speed = self.get_speed(guild_id) if speed is None else speed
            source = discord.FFmpegPCMAudio(
                url,
                **self._ffmpeg_options(seek_seconds=seek_seconds, speed=playback_speed),
            )
            return discord.PCMVolumeTransformer(source, volume=self.get_volume(guild_id))
        except Exception as e:
            print(f"[Music] Ошибка создания аудио: {e}")
            traceback.print_exc()
            return None

    def _make_after_callback(self, guild_id: int, voice: discord.VoiceClient):
        def after_callback(error):
            if guild_id in self.suppressed_after_callbacks:
                self.suppressed_after_callbacks.discard(guild_id)
                return

            if error:
                print(f"[Music] Ошибка при воспроизведении: {error}")

            future = asyncio.run_coroutine_threadsafe(
                self._play_next(guild_id, voice),
                self.bot.loop,
            )

            def log_play_next_result(task):
                try:
                    exc = task.exception()
                except Exception:
                    return
                if exc:
                    print(f"[Music] Ошибка перехода к следующему треку: {exc}")

            future.add_done_callback(log_play_next_result)

        return after_callback

    async def _restart_current_track(
        self,
        guild_id: int,
        voice: discord.VoiceClient,
        *,
        seek_seconds: Optional[float] = None,
        speed: Optional[float] = None,
    ) -> Optional[dict]:
        track = self.now_playing.get(guild_id)
        if not track:
            return None

        info = await self._extract_track_info(track["url"])
        if not info:
            return None

        stream_url = self._get_stream_url(info)
        if not stream_url:
            return None

        duration = info.get("duration") or track.get("duration")
        playback_speed = self.get_speed(guild_id) if speed is None else self.set_speed_value(guild_id, speed)
        position = self._track_elapsed(track) if seek_seconds is None else float(seek_seconds)
        if duration:
            position = max(0.0, min(position, max(0.0, float(duration) - 1.0)))
        else:
            position = max(0.0, position)

        source = await self._create_audio_source(
            stream_url,
            guild_id,
            seek_seconds=position,
            speed=playback_speed,
        )
        if not source:
            return None

        if voice.is_playing() or voice.is_paused():
            self.suppressed_after_callbacks.add(guild_id)
            voice.stop()
            await asyncio.sleep(0.15)

        track["title"] = info.get("title", track["title"])
        track["duration"] = duration
        track["stream_url"] = stream_url
        track["media_start"] = position
        track["speed"] = playback_speed
        track["started_at"] = self.bot.loop.time()
        track["paused_total"] = 0.0
        track.pop("pause_started_at", None)

        try:
            voice.play(source, after=self._make_after_callback(guild_id, voice))
        except Exception as e:
            self.suppressed_after_callbacks.discard(guild_id)
            print(f"[Music] Ошибка перезапуска трека: {e}")
            return None

        await self._stop_lyrics(guild_id)
        self._start_lyrics_task(guild_id, track, info)
        return track

    async def _play_next(self, guild_id: int, voice: Optional[discord.VoiceClient] = None):
        lock = self.get_play_next_lock(guild_id)
        if lock.locked():
            print(f"[Music] Переход к следующему треку уже выполняется для guild={guild_id}, повторный запуск пропущен")
            return

        async with lock:
            await self._play_next_locked(guild_id, voice)

    async def _play_next_locked(self, guild_id: int, voice: Optional[discord.VoiceClient] = None):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        if voice is not None:
            await asyncio.sleep(0.25)

        actual_voice = guild.voice_client
        if actual_voice and actual_voice.is_connected():
            voice = actual_voice
        elif voice and voice.is_connected():
            pass
        else:
            voice = None

        if not voice or not voice.is_connected():
            print("[Music] Голосовой клиент не найден, пытаемся переподключиться")
            queue = self.get_queue(guild_id)
            if not queue:
                return

            track = queue[0]
            target_channel = None
            voice_channel_id = track.get("voice_channel_id")
            if voice_channel_id:
                channel = guild.get_channel(int(voice_channel_id))
                if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                    target_channel = channel

            requester = track.get("requester")
            if target_channel is None and requester and requester.voice and requester.voice.channel:
                target_channel = requester.voice.channel

            if target_channel is not None:
                try:
                    voice = await self._connect_to(target_channel)
                    print(f"[Music] Переподключились к каналу: {target_channel.name}")
                except Exception as e:
                    error_text = self._format_voice_connect_error(e)
                    print(f"[Music] Не удалось переподключиться: {error_text}")
                    self.queues.pop(guild_id, None)
                    self.now_playing.pop(guild_id, None)
                    return
            else:
                print("[Music] Не удалось найти голосовой канал для переподключения")
                self.queues.pop(guild_id, None)
                self.now_playing.pop(guild_id, None)
                return

        if voice.is_playing() or voice.is_paused():
            print(f"[Music] Голосовой клиент уже играет, повторный _play_next пропущен для guild={guild_id}")
            return

        await self._stop_lyrics(guild_id)
        queue = self.get_queue(guild_id)

        if not queue:
            print(f"[Music] Очередь пуста, отключение через {IDLE_DISCONNECT_SECONDS} сек")
            self.now_playing.pop(guild_id, None)
            self._schedule_idle_disconnect(guild_id)
            return

        self._cancel_idle_disconnect(guild_id)
        track = queue.pop(0)
        print(f"[Music] Проигрываю: {track['title']}")

        info = await self._extract_track_info(track["url"])
        if not info:
            print("[Music] Не удалось получить информацию о треке, пропускаю")
            await self._play_next_locked(guild_id, voice)
            return

        stream_url = self._get_stream_url(info)
        if not stream_url:
            print("[Music] Не удалось найти URL потока, пропускаю")
            await self._play_next_locked(guild_id, voice)
            return

        source = await self._create_audio_source(stream_url, guild_id)
        if not source:
            print("[Music] Не удалось создать аудио-источник, пропускаю")
            await self._play_next_locked(guild_id, voice)
            return

        track["title"] = info.get("title", track["title"])
        track["duration"] = info.get("duration")
        track["stream_url"] = stream_url
        track["speed"] = self.get_speed(guild_id)
        track["media_start"] = 0.0
        track["started_at"] = self.bot.loop.time()
        track["paused_total"] = 0.0
        track.pop("pause_started_at", None)
        self.now_playing[guild_id] = track

        try:
            voice.play(source, after=self._make_after_callback(guild_id, voice))
            self._start_lyrics_task(guild_id, track, info)
            print(f"[Music] Начал проигрывать: {track['title']}")
        except Exception as e:
            print(f"[Music] Ошибка voice.play(): {e}")
            if isinstance(e, discord.ClientException) and "Already playing audio" in str(e):
                queue.insert(0, track)
                if self.now_playing.get(guild_id) is track:
                    self.now_playing.pop(guild_id, None)
                print("[Music] Трек возвращён в очередь, потому что voice уже воспроизводит аудио")
                return

            traceback.print_exc()
            await self._play_next_locked(guild_id, voice)

    @staticmethod
    def _format_duration(seconds: Optional[int]) -> str:
        if not seconds:
            return "неизвестно"
        minutes, sec = divmod(int(max(0, seconds)), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{sec:02d}"
        return f"{minutes}:{sec:02d}"

    def _progress_text(self, guild_id: int, track: dict) -> str:
        elapsed = self._track_elapsed(track)
        duration = track.get("duration")
        speed = track.get("speed", self.get_speed(guild_id))
        if duration:
            ratio = max(0.0, min(1.0, elapsed / max(1.0, float(duration))))
            filled = int(ratio * 18)
            bar = "█" * filled + "░" * (18 - filled)
            return (
                f"`{self._format_duration(elapsed)} / {self._format_duration(duration)}`\n"
                f"`{bar}`\n"
                f"Скорость: `{speed:g}x`"
            )

        return f"`{self._format_duration(elapsed)} / неизвестно`\nСкорость: `{speed:g}x`"

    @staticmethod
    def _shorten(text: str, limit: int = 78) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def get_visible_queue_item_count(self, guild_id: int) -> int:
        return len(self.get_queue(guild_id)) + (1 if self.now_playing.get(guild_id) else 0)

    def get_max_queue_start(self, guild_id: int) -> int:
        total = self.get_visible_queue_item_count(guild_id)
        if total <= QUEUE_PAGE_SIZE:
            return 1
        return max(1, total - QUEUE_PAGE_SIZE + 1)

    def normalize_queue_start(self, guild_id: int, start: int = 1) -> int:
        try:
            start = int(start)
        except (TypeError, ValueError):
            start = 1

        if start < 1:
            return 1
        return min(start, self.get_max_queue_start(guild_id))

    def get_visible_track(self, guild_id: int, position: int) -> Optional[tuple[dict, bool]]:
        if position < 1:
            return None

        current = self.now_playing.get(guild_id)
        if current:
            if position == 1:
                return current, True
            queue_index = position - 2
        else:
            queue_index = position - 1

        queue = self.get_queue(guild_id)
        if 0 <= queue_index < len(queue):
            return queue[queue_index], False
        return None

    def create_queue_embed(self, guild_id: int, start: int = 1) -> discord.Embed:
        current = self.now_playing.get(guild_id)
        queue = self.get_queue(guild_id)
        total = self.get_visible_queue_item_count(guild_id)
        start = self.normalize_queue_start(guild_id, start)

        embed = discord.Embed(
            title="🎵 Музыкальное меню",
            color=discord.Color.purple(),
        )

        if current:
            embed.add_field(
                name="Сейчас играет",
                value=f"**{current['title']}**\n{self._progress_text(guild_id, current)}",
                inline=False,
            )
        else:
            embed.add_field(name="Сейчас играет", value="Ничего", inline=False)

        embed.add_field(
            name="Громкость",
            value=f"{int(self.get_volume(guild_id) * 100)}%",
            inline=False,
        )

        if total:
            end = min(total, start + QUEUE_PAGE_SIZE - 1)
            queue_lines = []
            for position in range(start, end + 1):
                visible_track = self.get_visible_track(guild_id, position)
                if not visible_track:
                    continue

                track, is_current = visible_track
                marker = "▶️ " if is_current else ""
                title = self._shorten(track["title"])
                duration = self._format_duration(track.get("duration"))
                queue_lines.append(f"{position}. {marker}**{title}** `{duration}`")

            queue_text = "\n".join(queue_lines) if queue_lines else "Пусто"
            embed.set_footer(text=f"Показаны {start}-{end} из {total}")
        else:
            queue_text = "Пусто"

        embed.add_field(
            name=f"Список песен ({total})",
            value=queue_text,
            inline=False,
        )

        return embed

    def create_now_embed(self, guild_id: int) -> discord.Embed:
        current = self.now_playing.get(guild_id)
        if not current:
            return discord.Embed(
                title="🎵 Сейчас играет",
                description="❌ Сейчас ничего не играет",
                color=discord.Color.purple(),
            )

        embed = discord.Embed(
            title="🎵 Сейчас играет",
            description=f"**{current['title']}**",
            color=discord.Color.purple(),
        )
        embed.add_field(name="Время", value=self._progress_text(guild_id, current), inline=False)
        embed.add_field(name="Громкость", value=f"{int(self.get_volume(guild_id) * 100)}%", inline=True)
        embed.add_field(name="Скорость", value=f"{self.get_speed(guild_id):g}x", inline=True)

        requester = current.get("requester")
        if requester:
            embed.add_field(name="Запрошено", value=requester.mention, inline=False)

        return embed

    def log_music_action(self, interaction: discord.Interaction, action: str, details: str = ""):
        user = getattr(interaction, "user", None)
        guild = getattr(interaction, "guild", None)
        channel = getattr(interaction, "channel", None)
        user_text = f"{user} ({getattr(user, 'id', 'unknown')})"
        guild_text = f"{getattr(guild, 'name', 'DM')} ({getattr(guild, 'id', 'no-guild')})"
        channel_text = f"{getattr(channel, 'name', 'unknown')} ({getattr(channel, 'id', 'no-channel')})"
        details_text = f" | {details}" if details else ""
        print(f"[MusicAction] {user_text} | {guild_text} | {channel_text} | {action}{details_text}")

    async def set_lyrics_enabled(self, interaction: discord.Interaction, enabled: bool):
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        if not enabled:
            self.lyrics_channels.pop(guild_id, None)
            await self._stop_lyrics(guild_id)
            return await send_temp_response(interaction, "🎤 Субтитры выключены.", ephemeral=True)

        if interaction.channel_id is None:
            return await send_temp_response(
                interaction,
                "❌ Не удалось определить канал для субтитров.",
                ephemeral=True,
            )

        self.lyrics_channels[guild_id] = interaction.channel_id
        channel_name = getattr(interaction.channel, "mention", "этом канале")
        current = self.now_playing.get(guild_id)

        await interaction.response.defer(ephemeral=True)

        if current:
            await self._stop_lyrics(guild_id)
            info = await self._extract_track_info(current["url"])
            if info and self.now_playing.get(guild_id) is current:
                self._start_lyrics_task(guild_id, current, info)
                return await send_temp_followup(
                    interaction,
                    f"🎤 Субтитры включены в {channel_name}. Пробую найти строки для текущей песни.",
                    ephemeral=True,
                )

            return await send_temp_followup(
                interaction,
                f"🎤 Субтитры включены в {channel_name}. Начну со следующей песни.",
                ephemeral=True,
            )

        await send_temp_followup(
            interaction,
            f"🎤 Субтитры включены в {channel_name}. Начну, когда заиграет песня.",
            ephemeral=True,
        )

    async def seek_to(self, interaction: discord.Interaction, seconds: float):
        if not interaction.guild:
            return await send_temp_response(interaction, "Эта команда работает только на сервере", ephemeral=True)

        guild_id = interaction.guild.id
        voice = interaction.guild.voice_client
        current = self.now_playing.get(guild_id)
        if not current or not voice or not voice.is_connected():
            return await send_temp_response(interaction, "❌ Сейчас ничего не играет.", ephemeral=True)

        self.log_music_action(interaction, "seek", f"{seconds:g}s")
        await interaction.response.defer()
        restarted = await self._restart_current_track(guild_id, voice, seek_seconds=seconds)
        if not restarted:
            return await send_temp_followup(interaction, "❌ Не удалось перемотать трек.", ephemeral=True)

        await send_temp_followup(
            interaction,
            f"⏱️ Перемотал на `{self._format_duration(seconds)}`\n{self._progress_text(guild_id, restarted)}",
            ephemeral=True,
        )

    async def set_playback_speed(self, interaction: discord.Interaction, speed: float):
        if not interaction.guild:
            return await send_temp_response(interaction, "Эта команда работает только на сервере", ephemeral=True)

        guild_id = interaction.guild.id
        speed = self.set_speed_value(guild_id, speed)
        voice = interaction.guild.voice_client
        current = self.now_playing.get(guild_id)

        self.log_music_action(interaction, "speed", f"{speed:g}x")

        if not current or not voice or not voice.is_connected():
            return await send_temp_response(
                interaction,
                f"⚙️ Скорость установлена: `{speed:g}x`. Применится к следующему треку.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)
        restarted = await self._restart_current_track(guild_id, voice, speed=speed)
        if not restarted:
            return await send_temp_followup(
                interaction,
                f"⚙️ Скорость сохранена: `{speed:g}x`, но текущий трек не удалось перезапустить.",
                ephemeral=True,
            )

        await send_temp_followup(
            interaction,
            f"⚙️ Скорость: `{speed:g}x`\n{self._progress_text(guild_id, restarted)}",
            ephemeral=True,
        )

    async def play_query_from_menu(self, interaction: discord.Interaction, query: str):
        if not isinstance(interaction.user, discord.Member):
            return await send_temp_response(interaction, "Ошибка: пользователь не является членом сервера", ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await send_temp_response(interaction, "❌ Ты должен быть в голосовом канале", ephemeral=True)

        if yt_dlp is None:
            return await send_temp_response(interaction, "❌ yt-dlp не установлен. Установи: `pip install -U yt-dlp`", ephemeral=True)

        if shutil.which("ffmpeg") is None:
            return await send_temp_response(interaction, "❌ ffmpeg не найден в PATH. Установи ffmpeg и добавь его в PATH", ephemeral=True)

        if not interaction.guild:
            return await send_temp_response(interaction, "Эта команда работает только на сервере", ephemeral=True)

        channel = interaction.user.voice.channel
        voice = interaction.guild.voice_client
        if voice and voice.is_connected() and voice.channel != channel:
            return await send_temp_response(interaction, "❌ Я уже подключен к другому голосовому каналу", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        if is_url_query(query):
            await interaction.followup.send(
                f"🔗 Ссылка: {query}",
                allowed_mentions=discord.AllowedMentions.none(),
                suppress_embeds=True,
            )

        info = await self._extract_queue_info(query)
        tracks = self._tracks_from_info(info, interaction.user, query, voice_channel_id=channel.id)
        if not tracks:
            return await send_temp_followup(interaction, "❌ Не удалось найти треки.", ephemeral=True)

        if not voice or not voice.is_connected():
            try:
                voice = await self._connect_to(channel)
            except Exception as e:
                return await send_temp_followup(
                    interaction,
                    f"❌ Не удалось подключиться к каналу: {self._format_voice_connect_error(e)}",
                    ephemeral=True,
                )

        guild_id = interaction.guild.id
        self._cancel_idle_disconnect(guild_id)
        queue = self.get_queue(guild_id)
        queue.extend(tracks)

        if voice.is_playing() or voice.is_paused():
            return await send_temp_followup(
                interaction,
                self._format_added_tracks_message(tracks, info.get("title") if len(tracks) > 1 else None),
                ephemeral=True,
            )

        await asyncio.sleep(0.2)
        await self._play_next(guild_id, voice)
        current = self.now_playing.get(guild_id)
        if current:
            return await send_temp_followup(interaction, f"🎵 Проигрываю: **{current['title']}**", ephemeral=True)

        await send_temp_followup(interaction, "❌ Не удалось начать воспроизведение", ephemeral=True)

    async def console_send_menu(self, channel_id: int) -> str:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return "Текстовый канал не найден."

        embed = self.create_queue_embed(channel.guild.id)
        view = MusicControlView(self, channel.guild.id)
        await channel.send(embed=embed, view=view)
        return f"Музыкальное меню отправлено в #{channel.name}."

    async def console_join(self, voice_channel_id: int) -> str:
        channel = self.bot.get_channel(voice_channel_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return "Голосовой канал не найден."

        voice = channel.guild.voice_client
        try:
            if voice and voice.is_connected():
                await voice.move_to(channel)
            else:
                await self._connect_to(channel)
        except Exception as e:
            return f"Не удалось подключиться: {self._format_voice_connect_error(e)}"

        self._cancel_idle_disconnect(channel.guild.id)
        return f"Подключился к голосовому каналу: {channel.name}."

    async def console_leave(self, guild_id: int) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return "Сервер не найден."

        voice = guild.voice_client
        if not voice or not voice.is_connected():
            return "Бот не подключен к голосовому каналу."

        self._cancel_idle_disconnect(guild_id)
        await self._stop_lyrics(guild_id)
        self.queues.pop(guild_id, None)
        self.now_playing.pop(guild_id, None)
        await voice.disconnect()
        return "Отключился от голосового канала."

    async def console_play(self, voice_channel_id: int, query: str) -> str:
        channel = self.bot.get_channel(voice_channel_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return "Голосовой канал не найден."

        if yt_dlp is None:
            return "yt-dlp не установлен."

        if shutil.which("ffmpeg") is None:
            return "ffmpeg не найден в PATH."

        guild = channel.guild
        requester = guild.me
        if requester is None:
            return "Не удалось получить участника бота на сервере."

        voice = guild.voice_client
        try:
            if voice and voice.is_connected():
                if voice.channel != channel:
                    await voice.move_to(channel)
            else:
                voice = await self._connect_to(channel)
        except Exception as e:
            return f"Не удалось подключиться: {self._format_voice_connect_error(e)}"

        print(f"[MusicConsole] Ищу: {query}")
        info = await self._extract_queue_info(query)
        tracks = self._tracks_from_info(info, requester, query, voice_channel_id=channel.id)
        if not tracks:
            return "Не удалось найти треки."

        guild_id = guild.id
        self._cancel_idle_disconnect(guild_id)
        queue = self.get_queue(guild_id)
        queue.extend(tracks)

        if voice.is_playing() or voice.is_paused():
            return self._format_added_tracks_message(tracks, info.get("title") if len(tracks) > 1 else None)

        await asyncio.sleep(0.2)
        await self._play_next(guild_id, voice)
        current = self.now_playing.get(guild_id)
        if current:
            return f"Проигрываю: {current['title']}"
        return "Треки добавлены, но воспроизведение не началось."

    async def console_skip(self, guild_id: int) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return "Сервер не найден."

        voice = guild.voice_client
        if not voice or not voice.is_connected():
            return "Бот не подключен к голосовому каналу."
        if not (voice.is_playing() or voice.is_paused()):
            return "Сейчас ничего не играет."

        voice.stop()
        return "Трек пропущен."

    async def console_stop(self, guild_id: int) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return "Сервер не найден."

        voice = guild.voice_client
        if not voice or not voice.is_connected():
            return "Бот не подключен к голосовому каналу."

        self._cancel_idle_disconnect(guild_id)
        await self._stop_lyrics(guild_id)
        self.queues.pop(guild_id, None)
        self.now_playing.pop(guild_id, None)
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        self._schedule_idle_disconnect(guild_id)
        return "Музыка остановлена, очередь очищена."

    def console_shuffle(self, guild_id: int) -> str:
        if not self.bot.get_guild(guild_id):
            return "Сервер не найден."
        return self.shuffle_queue(guild_id)

    async def console_jump(self, guild_id: int, position: int) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return "Сервер не найден."

        total = self.get_visible_queue_item_count(guild_id)
        if total == 0:
            return "Список песен пустой."
        if position < 1 or position > total:
            return f"Номер должен быть от 1 до {total}."

        voice = guild.voice_client
        if not voice or not voice.is_connected():
            return "Бот не подключен к голосовому каналу."

        current = self.now_playing.get(guild_id)
        if current and position == 1:
            if voice.is_paused():
                voice.resume()
                self._mark_track_resumed(guild_id)
                return "Воспроизведение продолжено."
            return "Этот трек уже играет."

        queue = self.get_queue(guild_id)
        target_index = position - (2 if current else 1)
        if target_index < 0 or target_index >= len(queue):
            return "Не удалось найти этот номер в очереди."

        target = queue[target_index]
        if target_index:
            del queue[:target_index]

        self._cancel_idle_disconnect(guild_id)
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        else:
            await self._play_next(guild_id, voice)

        return f"Переключаюсь на #{position}: {target['title']}"

    def console_queue_text(self, guild_id: int) -> str:
        total = self.get_visible_queue_item_count(guild_id)
        if total == 0:
            return "Очередь пустая."

        lines = []
        for position in range(1, total + 1):
            visible = self.get_visible_track(guild_id, position)
            if not visible:
                continue
            track, is_current = visible
            marker = "▶ " if is_current else ""
            duration = self._format_duration(track.get("duration"))
            lines.append(f"{position}. {marker}{track['title']} ({duration})")
        return "\n".join(lines)

    def console_now_text(self, guild_id: int) -> str:
        current = self.now_playing.get(guild_id)
        if not current:
            return "Сейчас ничего не играет."
        return f"{current['title']}\n{self._progress_text(guild_id, current)}"

    async def console_lyrics(self, guild_id: int, channel_id: int, enabled: bool) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return "Сервер не найден."

        if not enabled:
            self.lyrics_channels.pop(guild_id, None)
            await self._stop_lyrics(guild_id)
            return "Субтитры выключены."

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return "Текстовый канал не найден."

        self.lyrics_channels[guild_id] = channel.id
        current = self.now_playing.get(guild_id)
        if current:
            await self._stop_lyrics(guild_id)
            info = await self._extract_track_info(current["url"])
            if info and self.now_playing.get(guild_id) is current:
                self._start_lyrics_task(guild_id, current, info)
                return f"Субтитры включены в #{channel.name} для текущей песни."
        return f"Субтитры включены в #{channel.name}; начну со следующей песни."

    async def jump_to_position(self, interaction: discord.Interaction, position: int):
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        total = self.get_visible_queue_item_count(guild_id)

        if total == 0:
            return await send_temp_response(interaction, "❌ Список песен пустой.", ephemeral=True)

        if position < 1 or position > total:
            return await send_temp_response(
                interaction,
                f"❌ Номер должен быть от 1 до {total}.",
                ephemeral=True,
            )

        voice = interaction.guild.voice_client
        current = self.now_playing.get(guild_id)

        if current and position == 1:
            if voice and voice.is_connected() and voice.is_paused():
                self._cancel_idle_disconnect(guild_id)
                voice.resume()
                self._mark_track_resumed(guild_id)
                return await send_temp_response(
                    interaction,
                    "▶️ Воспроизведение продолжено.",
                    ephemeral=True,
                )

            return await send_temp_response(
                interaction,
                "▶️ Этот трек уже играет.",
                ephemeral=True,
            )

        if yt_dlp is None:
            return await send_temp_response(
                interaction,
                "❌ yt-dlp не установлен. Установи: `pip install -U yt-dlp`",
                ephemeral=True,
            )

        if shutil.which("ffmpeg") is None:
            return await send_temp_response(
                interaction,
                "❌ ffmpeg не найден в PATH. Установи ffmpeg и добавь его в PATH",
                ephemeral=True,
            )

        queue = self.get_queue(guild_id)
        target_index = position - (2 if current else 1)
        if target_index < 0 or target_index >= len(queue):
            return await send_temp_response(
                interaction,
                "❌ Не удалось найти этот номер в очереди.",
                ephemeral=True,
            )

        target = queue[target_index]

        if not voice or not voice.is_connected():
            if not isinstance(interaction.user, discord.Member):
                return await send_temp_response(
                    interaction,
                    "Ошибка: пользователь не является членом сервера",
                    ephemeral=True,
                )

            if not interaction.user.voice or not interaction.user.voice.channel:
                return await send_temp_response(
                    interaction,
                    "❌ Ты должен быть в голосовом канале",
                    ephemeral=True,
                )

            await interaction.response.defer(ephemeral=True)
            try:
                voice = await self._connect_to(interaction.user.voice.channel)
            except Exception as e:
                error_text = self._format_voice_connect_error(e)
                return await send_temp_followup(
                    interaction,
                    f"❌ Не удалось подключиться к каналу: {error_text}",
                    ephemeral=True,
                )
        else:
            await interaction.response.defer(ephemeral=True)

        if target_index:
            del queue[:target_index]

        self._cancel_idle_disconnect(guild_id)
        if voice.is_playing() or voice.is_paused():
            voice.stop()
        else:
            await self._play_next(guild_id, voice)

        await send_temp_followup(
            interaction,
            f"▶️ Переключаюсь на #{position}: **{target['title']}**",
            ephemeral=True,
        )

    @app_commands.command(name="join", description="Подключить бота к голосовому каналу")
    @app_commands.guild_only()
    async def join(self, interaction: discord.Interaction):
        self.log_music_action(interaction, "command /join")
        if not isinstance(interaction.user, discord.Member):
            return await send_temp_response(
                interaction,
                "Ошибка: пользователь не является членом сервера",
                ephemeral=True,
            )

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await send_temp_response(
                interaction,
                "❌ Ты должен быть в голосовом канале",
                ephemeral=True,
            )

        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        channel = interaction.user.voice.channel
        self._cancel_idle_disconnect(interaction.guild.id)

        try:
            voice = interaction.guild.voice_client
            if voice and voice.is_connected():
                await voice.move_to(channel)
            else:
                await self._connect_to(channel)

            await send_temp_response(interaction, f"✅ Подключился к каналу: {channel.mention}")
        except Exception as e:
            error_text = self._format_voice_connect_error(e)
            print(f"[Music] Ошибка подключения: {error_text}")
            await send_temp_response(
                interaction,
                f"❌ Ошибка подключения: {error_text}",
                ephemeral=True,
            )

    @app_commands.command(name="leave", description="Отключить бота от голосового канала")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        self.log_music_action(interaction, "command /leave")
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        voice = interaction.guild.voice_client
        if not voice or not voice.is_connected():
            return await send_temp_response(
                interaction,
                "❌ Я не нахожусь в голосовом канале",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        self._cancel_idle_disconnect(guild_id)
        await self._stop_lyrics(guild_id)
        self.queues.pop(guild_id, None)
        self.now_playing.pop(guild_id, None)

        try:
            await voice.disconnect()
            await send_temp_response(interaction, "✅ Отключился от голосового канала")
        except Exception as e:
            print(f"[Music] Ошибка отключения: {e}")
            await send_temp_response(
                interaction,
                f"❌ Ошибка отключения: {e}",
                ephemeral=True,
            )

    @app_commands.command(name="play", description="Проиграть музыку по ссылке, названию или плейлисту")
    @app_commands.guild_only()
    @app_commands.describe(query="YouTube / YouTube Music / Twitch / VK ссылка, название песни или ссылка на плейлист")
    async def play(self, interaction: discord.Interaction, query: str):
        self.log_music_action(interaction, "command /play", query)
        if not isinstance(interaction.user, discord.Member):
            return await send_temp_response(
                interaction,
                "Ошибка: пользователь не является членом сервера",
                ephemeral=True,
            )

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await send_temp_response(
                interaction,
                "❌ Ты должен быть в голосовом канале",
                ephemeral=True,
            )

        if yt_dlp is None:
            return await send_temp_response(
                interaction,
                "❌ yt-dlp не установлен. Установи: `pip install -U yt-dlp`",
                ephemeral=True,
            )

        if shutil.which("ffmpeg") is None:
            return await send_temp_response(
                interaction,
                "❌ ffmpeg не найден в PATH. Установи ffmpeg и добавь его в PATH",
                ephemeral=True,
            )

        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        channel = interaction.user.voice.channel
        voice = interaction.guild.voice_client

        if voice and voice.is_connected() and voice.channel != channel:
            return await send_temp_response(
                interaction,
                "❌ Я уже подключен к другому голосовому каналу",
                ephemeral=True,
            )

        await interaction.response.defer()

        if is_url_query(query):
            await interaction.followup.send(
                f"🔗 Ссылка: {query}",
                allowed_mentions=discord.AllowedMentions.none(),
                suppress_embeds=True,
            )

        print(f"[Music] Ищу: {query}")
        info = await self._extract_queue_info(query)
        tracks = self._tracks_from_info(info, interaction.user, query, voice_channel_id=channel.id)

        if not tracks:
            return await send_temp_followup(
                interaction,
                "❌ Не удалось найти треки. Попробуй YouTube/YouTube Music/Twitch/VK ссылку, плейлист или другое название",
                ephemeral=True,
            )

        if not voice or not voice.is_connected():
            try:
                voice = await self._connect_to(channel)
                print(f"[Music] Подключился к каналу: {channel.name}")
            except Exception as e:
                error_text = self._format_voice_connect_error(e)
                print(f"[Music] Ошибка подключения: {error_text}")
                return await send_temp_followup(
                    interaction,
                    f"❌ Не удалось подключиться к каналу: {error_text}",
                    ephemeral=True,
                )

        guild_id = interaction.guild.id
        self._cancel_idle_disconnect(guild_id)
        queue = self.get_queue(guild_id)

        queue.extend(tracks)
        print(f"[Music] Добавлено треков в очередь: {len(tracks)}")

        if voice.is_playing() or voice.is_paused():
            await send_temp_followup(
                interaction,
                self._format_added_tracks_message(tracks, info.get("title") if len(tracks) > 1 else None)
            )
            return

        await asyncio.sleep(0.2)
        await self._play_next(guild_id, voice)

        current = self.now_playing.get(guild_id)
        if current:
            if len(tracks) == 1:
                await send_temp_followup(interaction, f"🎵 Проигрываю: **{current['title']}**")
            else:
                limit_note = (
                    f"\nДобавлены первые {MAX_PLAYLIST_ITEMS} треков."
                    if len(tracks) >= MAX_PLAYLIST_ITEMS
                    else ""
                )
                await send_temp_followup(
                    interaction,
                    f"🎵 Проигрываю: **{current['title']}**\n"
                    f"✅ Добавлено треков из плейлиста: **{len(tracks)}**"
                    f"{limit_note}"
                )
        else:
            await send_temp_followup(
                interaction,
                "❌ Не удалось начать воспроизведение",
                ephemeral=True,
            )

    @app_commands.command(name="menu", description="Открыть музыкальное меню с кнопками")
    @app_commands.guild_only()
    async def menu(self, interaction: discord.Interaction):
        self.log_music_action(interaction, "command /menu")
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        embed = self.create_queue_embed(guild_id)
        view = MusicControlView(self, guild_id)
        await send_temp_response(interaction, embed=embed, view=view)

    @app_commands.command(name="skip", description="Пропустить текущий трек")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        self.log_music_action(interaction, "command /skip")
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        voice = interaction.guild.voice_client
        if not voice or not voice.is_connected():
            return await send_temp_response(
                interaction,
                "❌ Я не подключен к голосовому каналу",
                ephemeral=True,
            )

        if not (voice.is_playing() or voice.is_paused()):
            return await send_temp_response(
                interaction,
                "❌ Сейчас ничего не играет",
                ephemeral=True,
            )

        voice.stop()
        await send_temp_response(interaction, "⏭️ Трек пропущен")

    @app_commands.command(name="stop", description="Остановить музыку")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        self.log_music_action(interaction, "command /stop")
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        voice = interaction.guild.voice_client
        if not voice or not voice.is_connected():
            return await send_temp_response(
                interaction,
                "❌ Я не подключен к голосовому каналу",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        self._cancel_idle_disconnect(guild_id)
        await self._stop_lyrics(guild_id)
        self.queues.pop(guild_id, None)
        self.now_playing.pop(guild_id, None)

        voice.stop()
        self._schedule_idle_disconnect(guild_id)
        await send_temp_response(interaction, "⏹️ Музыка остановлена. Очередь очищена")

    @app_commands.command(name="queue", description="Показать список песен в очереди")
    @app_commands.guild_only()
    @app_commands.describe(start="Номер песни, с которого показать список")
    async def queue(self, interaction: discord.Interaction, start: int = 1):
        self.log_music_action(interaction, "command /queue", f"start={start}")
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        embed = self.create_queue_embed(guild_id, start=start)
        view = QueuePageView(self, guild_id, start=start)
        await send_temp_response(interaction, embed=embed, view=view)

    @app_commands.command(name="shuffle", description="Перемешать очередь музыки")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction):
        self.log_music_action(interaction, "command /shuffle")
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        await send_temp_response(interaction, self.shuffle_queue(interaction.guild.id), ephemeral=True)

    @app_commands.command(name="jump", description="Переключиться на песню по номеру из списка")
    @app_commands.guild_only()
    @app_commands.describe(position="Номер песни из /queue")
    async def jump(self, interaction: discord.Interaction, position: int):
        self.log_music_action(interaction, "command /jump", str(position))
        await self.jump_to_position(interaction, position)

    @app_commands.command(name="seek", description="Перемотать текущую песню на указанную секунду")
    @app_commands.guild_only()
    @app_commands.describe(seconds="Секунда трека, например 90")
    async def seek(self, interaction: discord.Interaction, seconds: float):
        await self.seek_to(interaction, seconds)

    @app_commands.command(name="speed", description="Изменить скорость воспроизведения")
    @app_commands.guild_only()
    @app_commands.describe(value="Скорость x, например 0.25, 1 или 2")
    async def speed(self, interaction: discord.Interaction, value: float):
        await self.set_playback_speed(interaction, value)

    @app_commands.command(name="lyrics", description="Включить или выключить субтитры музыки")
    @app_commands.guild_only()
    @app_commands.describe(enabled="true - включить в этом канале, false - выключить")
    async def lyrics(self, interaction: discord.Interaction, enabled: bool = True):
        self.log_music_action(interaction, "command /lyrics", str(enabled))
        await self.set_lyrics_enabled(interaction, enabled)

    @app_commands.command(name="now", description="Показать текущий трек")
    @app_commands.guild_only()
    async def now(self, interaction: discord.Interaction):
        self.log_music_action(interaction, "command /now")
        if not interaction.guild:
            return await send_temp_response(
                interaction,
                "Эта команда работает только на сервере",
                ephemeral=True,
            )

        await send_temp_response(interaction, embed=self.create_now_embed(interaction.guild.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
