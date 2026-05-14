from __future__ import annotations

import asyncio
from typing import Dict, List, Optional
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


MAX_PLAYLIST_TRACKS = 25
SUPPORTED_HINT = "YouTube, SoundCloud, Bandcamp, Vimeo, Twitch и другие ссылки, которые поддерживает yt-dlp"
QUERY_DESCRIPTION = "Ссылка или название: YouTube, SoundCloud, Bandcamp, Vimeo, Twitch"

YDL_OPTIONS = {
    "format": "bestaudio[acodec=opus]/bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "extract_flat": "in_playlist",
    "playlistend": MAX_PLAYLIST_TRACKS,
    "source_address": "0.0.0.0",
}

YDL_STREAM_OPTIONS = {
    "format": "bestaudio[acodec=opus]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: Dict[int, List[dict]] = {}
        self.now_playing: Dict[int, dict] = {}
        self.stop_requested: set[int] = set()

    def get_queue(self, guild_id: int) -> List[dict]:
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    @staticmethod
    def _is_url(query: str) -> bool:
        parsed = urlparse(query)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _entry_url(entry: dict) -> Optional[str]:
        url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
        if not url:
            return None

        url = str(url)
        if entry.get("ie_key") == "Youtube" and not url.startswith(("http://", "https://")):
            return f"https://www.youtube.com/watch?v={url}"

        return url

    @staticmethod
    def _format_duration(seconds: Optional[int]) -> str:
        if not isinstance(seconds, int) or seconds <= 0:
            return "неизвестно"

        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{sec:02d}"
        return f"{minutes}:{sec:02d}"

    async def _extract_info(self, query: str, *, stream: bool = False) -> Optional[dict]:
        if yt_dlp is None:
            return None

        options = YDL_STREAM_OPTIONS if stream else YDL_OPTIONS
        lookup = query if self._is_url(query) else f"ytsearch1:{query}"
        loop = self.bot.loop

        def run_ydl():
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(lookup, download=False)

        try:
            return await loop.run_in_executor(None, run_ydl)
        except Exception as e:
            print(f"[Music] yt-dlp error: {e}")
            return None

    async def _build_tracks(self, query: str, requester: discord.Member) -> List[dict]:
        data = await self._extract_info(query)
        if data is None:
            return []

        entries = data.get("entries") if isinstance(data, dict) else None
        if entries:
            tracks = []
            for entry in entries[:MAX_PLAYLIST_TRACKS]:
                if not entry:
                    continue

                url = self._entry_url(entry)
                if not url:
                    continue

                tracks.append(
                    {
                        "title": entry.get("title") or "Неизвестно",
                        "url": url,
                        "requester": requester,
                        "duration": entry.get("duration"),
                    }
                )
            return tracks

        url = self._entry_url(data)
        if not url:
            return []

        return [
            {
                "title": data.get("title") or "Неизвестно",
                "url": url,
                "requester": requester,
                "duration": data.get("duration"),
            }
        ]

    async def _create_source(self, track: dict) -> tuple[Optional[discord.AudioSource], Optional[dict]]:
        info = await self._extract_info(track["url"], stream=True)
        if not info:
            return None, None

        if "entries" in info:
            entries = info.get("entries") or []
            info = next((entry for entry in entries if entry), None)
            if not info:
                return None, None

        stream_url = info.get("url")
        if not stream_url:
            return None, info

        ffmpeg_options = self._ffmpeg_options(info)

        try:
            source = await discord.FFmpegOpusAudio.from_probe(stream_url, **ffmpeg_options)
            return source, info
        except Exception as opus_error:
            print(f"[Music] ffmpeg opus error: {opus_error}")

        try:
            return discord.FFmpegOpusAudio(stream_url, **ffmpeg_options), info
        except Exception as ffmpeg_error:
            print(f"[Music] ffmpeg error: {ffmpeg_error}")
            return None, info

    @staticmethod
    def _ffmpeg_options(info: dict) -> dict:
        before_options = FFMPEG_BEFORE_OPTIONS
        headers = info.get("http_headers") or {}

        if headers:
            header_text = "".join(f"{key}: {value}\r\n" for key, value in headers.items())
            before_options = f'{before_options} -headers "{header_text}"'

        return {
            "before_options": before_options,
            "options": FFMPEG_OPTIONS,
        }

    def _schedule_play_next(self, guild_id: int) -> None:
        future = asyncio.run_coroutine_threadsafe(self._play_next(guild_id), self.bot.loop)

        def log_error(done):
            try:
                done.result()
            except Exception as e:
                print(f"[Music] Queue error: {e}")

        future.add_done_callback(log_error)

    async def _play_next(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        voice = guild.voice_client
        if not voice:
            return

        queue = self.get_queue(guild_id)
        if not queue:
            self.now_playing.pop(guild_id, None)
            await voice.disconnect()
            return

        track = queue.pop(0)
        source, info = await self._create_source(track)

        if source is None:
            await self._play_next(guild_id)
            return

        if info:
            track["title"] = info.get("title") or track["title"]
            track["duration"] = info.get("duration") or track.get("duration")
            track["url"] = info.get("webpage_url") or track["url"]

        self.now_playing[guild_id] = track

        def after_play(err: Optional[Exception]):
            if err:
                print(f"[Music] Player error: {err}")
            if guild_id in self.stop_requested:
                self.stop_requested.discard(guild_id)
                self.now_playing.pop(guild_id, None)
                return
            self._schedule_play_next(guild_id)

        voice.play(source, after=after_play)

    @app_commands.command(
        name="join",
        description="Подключить бота к голосовому каналу.",
    )
    @app_commands.guild_only()
    async def join(self, interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "Ты должен быть в голосовом канале.",
                ephemeral=True,
            )
            return

        channel = interaction.user.voice.channel

        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()

        await interaction.response.send_message(
            f"Подключился к каналу: {channel.mention}",
            ephemeral=False,
        )

    @app_commands.command(
        name="leave",
        description="Отключить бота от голосового канала.",
    )
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild_id is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        voice = interaction.guild.voice_client
        if not voice:
            await interaction.response.send_message(
                "Я не нахожусь в голосовом канале.",
                ephemeral=True,
            )
            return

        self.queues.pop(interaction.guild_id, None)
        self.now_playing.pop(interaction.guild_id, None)
        self.stop_requested.add(interaction.guild_id)
        await voice.disconnect()
        await interaction.response.send_message("Отключился от голосового канала.", ephemeral=False)

    @app_commands.command(
        name="play",
        description="Проиграть музыку по ссылке или названию.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        query=QUERY_DESCRIPTION
    )
    async def play(self, interaction: discord.Interaction, query: str):
        if interaction.guild is None or interaction.guild_id is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "Ты должен быть в голосовом канале.",
                ephemeral=True,
            )
            return

        channel = interaction.user.voice.channel
        voice = interaction.guild.voice_client

        if voice and voice.channel != channel:
            await interaction.response.send_message(
                "Я уже играю в другом голосовом канале.",
                ephemeral=True,
            )
            return

        if yt_dlp is None:
            await interaction.response.send_message(
                "Команды музыки недоступны, потому что зависимость `yt-dlp` не установлена.",
                ephemeral=True,
            )
            return

        if not voice:
            voice = await channel.connect()

        await interaction.response.defer()

        tracks = await self._build_tracks(query, interaction.user)
        if not tracks:
            await interaction.followup.send(
                f"Не удалось найти трек. Поддерживаются: {SUPPORTED_HINT}.",
                ephemeral=True,
            )
            return

        queue = self.get_queue(interaction.guild_id)

        if voice.is_playing() or voice.is_paused():
            queue.extend(tracks)
            first_title = tracks[0]["title"]
            extra = "" if len(tracks) == 1 else f" и ещё {len(tracks) - 1}"
            await interaction.followup.send(
                f"Добавлено в очередь: **{first_title}**{extra}",
                ephemeral=False,
            )
            return

        queue.extend(tracks)
        await self._play_next(interaction.guild_id)
        current = self.now_playing.get(interaction.guild_id)
        if not current:
            await interaction.followup.send("Не удалось подготовить аудио-поток. Проверь, что на хостинге установлен `ffmpeg`.", ephemeral=True)
            return

        extra = "" if len(tracks) == 1 else f"\nДобавлено в очередь ещё треков: {len(tracks) - 1}"
        await interaction.followup.send(
            f"Сейчас играет: **{current['title']}**{extra}",
            ephemeral=False,
        )

    @app_commands.command(
        name="skip",
        description="Пропустить текущий трек.",
    )
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        voice = interaction.guild.voice_client
        if not voice or not (voice.is_playing() or voice.is_paused()):
            await interaction.response.send_message(
                "Сейчас ничего не играет.",
                ephemeral=True,
            )
            return

        voice.stop()
        await interaction.response.send_message("Трек пропущен.", ephemeral=False)

    @app_commands.command(
        name="stop",
        description="Остановить музыку и очистить очередь.",
    )
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild_id is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        voice = interaction.guild.voice_client
        if not voice:
            await interaction.response.send_message(
                "Я не в голосовом канале.",
                ephemeral=True,
            )
            return

        self.get_queue(interaction.guild_id).clear()
        self.now_playing.pop(interaction.guild_id, None)
        if voice.is_playing() or voice.is_paused():
            self.stop_requested.add(interaction.guild_id)
            voice.stop()

        await interaction.response.send_message("Музыка остановлена, очередь очищена.", ephemeral=False)

    @app_commands.command(
        name="pause",
        description="Поставить музыку на паузу.",
    )
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        voice = interaction.guild.voice_client
        if not voice or not voice.is_playing():
            await interaction.response.send_message(
                "Сейчас ничего не играет.",
                ephemeral=True,
            )
            return

        voice.pause()
        await interaction.response.send_message("Музыка на паузе.", ephemeral=False)

    @app_commands.command(
        name="resume",
        description="Продолжить проигрывание музыки.",
    )
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        voice = interaction.guild.voice_client
        if not voice or not voice.is_paused():
            await interaction.response.send_message(
                "Музыка не на паузе.",
                ephemeral=True,
            )
            return

        voice.resume()
        await interaction.response.send_message("Продолжаю проигрывание.", ephemeral=False)

    @app_commands.command(
        name="queue",
        description="Посмотреть очередь треков.",
    )
    @app_commands.guild_only()
    async def queue_cmd(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return await interaction.response.send_message("Эта команда доступна только на сервере.", ephemeral=True)

        queue = self.get_queue(interaction.guild_id)
        current = self.now_playing.get(interaction.guild_id)
        if not current and not queue:
            await interaction.response.send_message(
                "Очередь пуста.",
                ephemeral=True,
            )
            return

        lines = []
        if current:
            duration = self._format_duration(current.get("duration"))
            lines.append(f"Сейчас: {current.get('title', 'Неизвестно')} ({duration})")

        for i, track in enumerate(queue, start=1):
            title = track.get("title", "Неизвестно")
            duration = self._format_duration(track.get("duration"))
            requester = track.get("requester")
            if requester:
                lines.append(f"{i}. {title} ({duration}) — запросил {requester.mention}")
            else:
                lines.append(f"{i}. {title} ({duration})")

        text = "\n".join(lines)
        if len(text) > 1900:
            text = text[:1900] + "\n..."

        await interaction.response.send_message(
            f"Очередь:\n{text}",
            ephemeral=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
