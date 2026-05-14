from __future__ import annotations

import asyncio
from typing import Optional, Dict, List

import discord
from discord import app_commands
from discord.ext import commands

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: Dict[int, List[dict]] = {}
        self.stop_requested: set[int] = set()

    def get_queue(self, guild_id: int) -> List[dict]:
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def _extract_info(self, query: str) -> Optional[dict]:
        loop = self.bot.loop

        def run_ydl():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                return ydl.extract_info(query, download=False)

        try:
            data = await loop.run_in_executor(None, run_ydl)
        except Exception as e:
            print(f"[Music] yt-dlp error: {e}")
            return None

        if data is None:
            return None

        if "entries" in data:
            entries = data.get("entries") or []
            if not entries:
                return None
            data = entries[0]

        return data

    async def _create_source(self, info: dict) -> Optional[discord.AudioSource]:
        url = info.get("url")
        if not url:
            return None
        try:
            return await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
        except Exception as e:
            print(f"[Music] ffmpeg error: {e}")
            return None

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
            await voice.disconnect()
            return

        track = queue.pop(0)
        source = track.get("source")

        if source is None:
            await self._play_next(guild_id)
            return

        def after_play(err: Optional[Exception]):
            if err:
                print(f"[Music] Player error: {err}")
            if guild_id in self.stop_requested:
                self.stop_requested.discard(guild_id)
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
        await voice.disconnect()
        await interaction.response.send_message("Отключился от голосового канала.", ephemeral=False)

    @app_commands.command(
        name="play",
        description="Проиграть музыку по ссылке или названию.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        query="Ссылка или название трека (YouTube, VK и др.)"
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

        info = await self._extract_info(query)
        if not info:
            await interaction.followup.send("Не удалось получить информацию о треке.", ephemeral=True)
            return

        source = await self._create_source(info)
        if not source:
            await interaction.followup.send("Не удалось подготовить аудио-поток.", ephemeral=True)
            return

        title = info.get("title", "Неизвестно")
        webpage_url = info.get("webpage_url", query)

        track = {
            "title": title,
            "url": webpage_url,
            "requester": interaction.user,
            "source": source,
        }

        queue = self.get_queue(interaction.guild_id)

        if voice.is_playing() or voice.is_paused():
            queue.append(track)
            await interaction.followup.send(
                f"Добавлено в очередь: **{title}**",
                ephemeral=False,
            )
        else:
            def after_play(err: Optional[Exception]):
                if err:
                    print(f"[Music] Player error: {err}")
                if interaction.guild_id in self.stop_requested:
                    self.stop_requested.discard(interaction.guild_id)
                    return
                self._schedule_play_next(interaction.guild_id)

            voice.play(source, after=after_play)
            await interaction.followup.send(
                f"Сейчас играет: **{title}**",
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
        if not voice or not voice.is_playing():
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
        if not queue:
            await interaction.response.send_message(
                "Очередь пуста.",
                ephemeral=True,
            )
            return

        lines = []
        for i, track in enumerate(queue, start=1):
            title = track.get("title", "Неизвестно")
            requester = track.get("requester")
            if requester:
                lines.append(f"{i}. {title} — запросил {requester.mention}")
            else:
                lines.append(f"{i}. {title}")

        text = "\n".join(lines)
        if len(text) > 1900:
            text = text[:1900] + "\n..."

        await interaction.response.send_message(
            f"Очередь:\n{text}",
            ephemeral=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
