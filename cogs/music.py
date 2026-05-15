import asyncio
import traceback
from typing import Dict, List, Optional
import shutil

import discord
from discord import app_commands
from discord.ext import commands

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


FFMPEG_OPTIONS = {
    "before_options": "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -loglevel warning",
}

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "extract_flat": False,
    "ignoreerrors": True,
    "socket_timeout": 30,
}

IDLE_DISCONNECT_SECONDS = 180


class Music(commands.Cog):
    """Модуль музыки для Discord бота"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: Dict[int, List[dict]] = {}
        self.now_playing: Dict[int, dict] = {}
        self.idle_disconnect_tasks: Dict[int, asyncio.Task] = {}

    def get_queue(self, guild_id: int) -> List[dict]:
        """Получить очередь для гильдии"""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def cog_unload(self):
        """Очистить ресурсы при выгрузке модуля"""
        for task in self.idle_disconnect_tasks.values():
            task.cancel()
        self.queues.clear()
        self.now_playing.clear()
        self.idle_disconnect_tasks.clear()

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
                "Перезапусти бота и убедись, что он запущен из этого .venv с discord.py[voice]>=2.7.1."
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

    def _get_stream_url(self, info: dict) -> Optional[str]:
        if info.get("url"):
            return info["url"]

        formats = info.get("formats") or []
        for item in formats:
            if item.get("url") and item.get("acodec") != "none":
                return item["url"]

        return None

    async def _extract_track_info(self, query: str) -> Optional[dict]:
        """Извлечь информацию о треке с yt-dlp"""
        if yt_dlp is None:
            print("[Music] yt-dlp не установлен")
            return None

        loop = asyncio.get_event_loop()
        
        def extract():
            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    return ydl.extract_info(query, download=False)
            except Exception as e:
                print(f"[Music] Ошибка yt-dlp: {e}")
                return None

        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, extract),
                timeout=30.0
            )
            return self._normalize_info(info)
        except asyncio.TimeoutError:
            print(f"[Music] Timeout при поиске: {query}")
            return None

    async def _create_audio_source(self, url: str) -> Optional[discord.AudioSource]:
        """Создать аудио-источник для стриминга"""
        try:
            return discord.FFmpegOpusAudio(url, **FFMPEG_OPTIONS)
        except Exception as e:
            print(f"[Music] Ошибка создания аудио: {e}")
            traceback.print_exc()
            return None

    async def _play_next(self, guild_id: int, voice: Optional[discord.VoiceClient] = None):
        """Проиграть следующий трек в очереди"""
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
            print(f"[Music] Голосовой клиент не найден, пытаемся переподключиться")
            queue = self.get_queue(guild_id)
            if not queue:
                return
            
            # Найти канал где находится пользователь который запросил трек
            track = queue[0]
            requester = track.get('requester')
            if requester and requester.voice and requester.voice.channel:
                try:
                    voice = await self._connect_to(requester.voice.channel)
                    print(f"[Music] Переподключились к каналу: {requester.voice.channel.name}")
                except Exception as e:
                    error_text = self._format_voice_connect_error(e)
                    print(f"[Music] Не удалось переподключиться: {error_text}")
                    self.queues.pop(guild_id, None)
                    self.now_playing.pop(guild_id, None)
                    return
            else:
                print(f"[Music] Не удалось найти голосовой канал для переподключения")
                self.queues.pop(guild_id, None)
                self.now_playing.pop(guild_id, None)
                return

        queue = self.get_queue(guild_id)
        if not queue:
            print(f"[Music] Очередь пуста, отключение через {IDLE_DISCONNECT_SECONDS} сек")
            self.now_playing.pop(guild_id, None)
            self._schedule_idle_disconnect(guild_id)
            return

        self._cancel_idle_disconnect(guild_id)
        track = queue.pop(0)
        print(f"[Music] Проигрываю: {track['title']}")

        # Получить URL для стриминга
        info = await self._extract_track_info(track['url'])
        if not info:
            print(f"[Music] Не удалось получить информацию о треке, пропускаю")
            await self._play_next(guild_id, voice)
            return

        stream_url = self._get_stream_url(info)
        if not stream_url:
            print(f"[Music] Не удалось найти URL потока, пропускаю")
            await self._play_next(guild_id, voice)
            return

        # Создать аудио-источник
        source = await self._create_audio_source(stream_url)
        if not source:
            print(f"[Music] Не удалось создать аудио-источник, пропускаю")
            await self._play_next(guild_id, voice)
            return

        # Обновить информацию о треке
        track['title'] = info.get('title', track['title'])
        track['duration'] = info.get('duration')
        self.now_playing[guild_id] = track

        # Определить callback для следующего трека
        def after_callback(error):
            if error:
                print(f"[Music] Ошибка при воспроизведении: {error}")
            
            # Запланировать следующий трек
            future = asyncio.run_coroutine_threadsafe(
                self._play_next(guild_id, voice),
                self.bot.loop
            )
            def log_play_next_result(task):
                try:
                    exc = task.exception()
                except Exception:
                    return
                if exc:
                    print(f"[Music] Ошибка перехода к следующему треку: {exc}")

            future.add_done_callback(log_play_next_result)

        try:
            voice.play(source, after=after_callback)
            print(f"[Music] Начал проигрывать: {track['title']}")
        except Exception as e:
            print(f"[Music] Ошибка voice.play(): {e}")
            traceback.print_exc()
            await self._play_next(guild_id, voice)

    @app_commands.command(
        name="join",
        description="Подключить бота к голосовому каналу"
    )
    @app_commands.guild_only()
    async def join(self, interaction: discord.Interaction):
        """Подключиться к голосовому каналу"""
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Ошибка: пользователь не является членом гильдии",
                ephemeral=True
            )

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "❌ Ты должен быть в голосовом канале",
                ephemeral=True
            )

        channel = interaction.user.voice.channel
        self._cancel_idle_disconnect(interaction.guild_id)
        
        try:
            voice = interaction.guild.voice_client
            if voice and voice.is_connected():
                await voice.move_to(channel)
            else:
                await self._connect_to(channel)
            
            await interaction.response.send_message(
                f"✅ Подключился к каналу: {channel.mention}"
            )
        except Exception as e:
            error_text = self._format_voice_connect_error(e)
            print(f"[Music] Ошибка подключения: {error_text}")
            await interaction.response.send_message(
                f"❌ Ошибка подключения: {error_text}",
                ephemeral=True
            )

    @app_commands.command(
        name="leave",
        description="Отключить бота от голосового канала"
    )
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction):
        """Отключиться от голосового канала"""
        if not interaction.guild:
            return await interaction.response.send_message(
                "Эта команда работает только на сервере",
                ephemeral=True
            )

        voice = interaction.guild.voice_client
        if not voice or not voice.is_connected():
            return await interaction.response.send_message(
                "❌ Я не нахожусь в голосовом канале",
                ephemeral=True
            )

        guild_id = interaction.guild_id
        self._cancel_idle_disconnect(guild_id)
        self.queues.pop(guild_id, None)
        self.now_playing.pop(guild_id, None)

        try:
            await voice.disconnect()
            await interaction.response.send_message("✅ Отключился от голосового канала")
        except Exception as e:
            print(f"[Music] Ошибка отключения: {e}")
            await interaction.response.send_message(
                f"❌ Ошибка отключения: {e}",
                ephemeral=True
            )

    @app_commands.command(
        name="play",
        description="Проиграть музыку по ссылке или названию"
    )
    @app_commands.guild_only()
    @app_commands.describe(query="YouTube ссылка или название песни")
    async def play(self, interaction: discord.Interaction, query: str):
        """Проиграть музыку"""
        # Проверки
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Ошибка: пользователь не является членом гильдии",
                ephemeral=True
            )

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                "❌ Ты должен быть в голосовом канале",
                ephemeral=True
            )

        if yt_dlp is None:
            return await interaction.response.send_message(
                "❌ yt-dlp не установлен. Установи: `pip install yt-dlp`",
                ephemeral=True
            )

        if shutil.which("ffmpeg") is None:
            return await interaction.response.send_message(
                "❌ ffmpeg не найден в PATH. Установи ffmpeg и добавь в PATH",
                ephemeral=True
            )

        channel = interaction.user.voice.channel
        voice = interaction.guild.voice_client

        # Проверить, что бот в том же канале
        if voice and voice.is_connected() and voice.channel != channel:
            return await interaction.response.send_message(
                "❌ Я уже подключен к другому голосовому каналу",
                ephemeral=True
            )

        await interaction.response.defer()

        # Получить информацию о треке
        print(f"[Music] Ищу: {query}")
        info = await self._extract_track_info(query)
        
        if not info:
            return await interaction.followup.send(
                "❌ Не удалось найти трек. Попробуй YouTube ссылку или другое название",
                ephemeral=True
            )

        # Подключиться к голосовому каналу если нужно
        if not voice or not voice.is_connected():
            try:
                voice = await self._connect_to(channel)
                print(f"[Music] Подключился к каналу: {channel.name}")
            except Exception as e:
                error_text = self._format_voice_connect_error(e)
                print(f"[Music] Ошибка подключения: {error_text}")
                return await interaction.followup.send(
                    f"❌ Не удалось подключиться к каналу: {error_text}",
                    ephemeral=True
                )

        # Добавить трек в очередь
        guild_id = interaction.guild_id
        self._cancel_idle_disconnect(guild_id)
        queue = self.get_queue(guild_id)
        
        track = {
            'title': info.get('title', 'Неизвестный трек'),
            'url': info.get('webpage_url') or info.get('original_url') or info.get('url') or query,
            'duration': info.get('duration'),
            'requester': interaction.user,
        }

        queue.append(track)
        print(f"[Music] Добавлен трек: {track['title']}")

        # Если уже что-то играет, просто добавить в очередь
        if voice.is_playing() or voice.is_paused():
            await interaction.followup.send(
                f"✅ Добавлено в очередь: **{track['title']}**"
            )
            return

        # Если ничего не играет, начать проигрывание
        await asyncio.sleep(0.2)  # Даем время на обновление voice_client
        await self._play_next(guild_id, voice)
        
        current = self.now_playing.get(guild_id)
        if current:
            await interaction.followup.send(
                f"🎵 Проигрываю: **{current['title']}**"
            )
        else:
            await interaction.followup.send(
                "❌ Не удалось начать воспроизведение",
                ephemeral=True
            )

    @app_commands.command(
        name="skip",
        description="Пропустить текущий трек"
    )
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        """Пропустить трек"""
        if not interaction.guild:
            return await interaction.response.send_message(
                "Эта команда работает только на сервере",
                ephemeral=True
            )

        voice = interaction.guild.voice_client
        if not voice or not voice.is_connected():
            return await interaction.response.send_message(
                "❌ Я не подключен к голосовому каналу",
                ephemeral=True
            )

        if not (voice.is_playing() or voice.is_paused()):
            return await interaction.response.send_message(
                "❌ Сейчас ничего не играет",
                ephemeral=True
            )

        voice.stop()
        await interaction.response.send_message("⏭️ Трек пропущен")

    @app_commands.command(
        name="stop",
        description="Остановить музыку"
    )
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        """Остановить воспроизведение"""
        if not interaction.guild:
            return await interaction.response.send_message(
                "Эта команда работает только на сервере",
                ephemeral=True
            )

        voice = interaction.guild.voice_client
        if not voice or not voice.is_connected():
            return await interaction.response.send_message(
                "❌ Я не подключен к голосовому каналу",
                ephemeral=True
            )

        guild_id = interaction.guild_id
        self._cancel_idle_disconnect(guild_id)
        self.queues.pop(guild_id, None)
        self.now_playing.pop(guild_id, None)
        
        voice.stop()
        self._schedule_idle_disconnect(guild_id)
        await interaction.response.send_message("⏹️ Музыка остановлена. Очередь очищена")

    @app_commands.command(
        name="queue",
        description="Показать очередь треков"
    )
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        """Показать очередь"""
        if not interaction.guild:
            return await interaction.response.send_message(
                "Эта команда работает только на сервере",
                ephemeral=True
            )

        guild_id = interaction.guild_id
        current = self.now_playing.get(guild_id)
        queue = self.get_queue(guild_id)

        if not current and not queue:
            return await interaction.response.send_message(
                "❌ Очередь пуста",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🎵 Очередь музыки",
            color=discord.Color.purple()
        )

        if current:
            embed.add_field(
                name="Сейчас играет",
                value=f"**{current['title']}**",
                inline=False
            )

        if queue:
            queue_text = ""
            for i, track in enumerate(queue[:10], 1):
                queue_text += f"{i}. **{track['title']}**\n"
            
            if len(queue) > 10:
                queue_text += f"... и ещё {len(queue) - 10} треков"
            
            embed.add_field(
                name=f"Очередь ({len(queue)} треков)",
                value=queue_text,
                inline=False
            )
        else:
            embed.add_field(
                name="Очередь",
                value="Пусто",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="now",
        description="Показать текущий трек"
    )
    @app_commands.guild_only()
    async def now(self, interaction: discord.Interaction):
        """Показать текущий трек"""
        if not interaction.guild:
            return await interaction.response.send_message(
                "Эта команда работает только на сервере",
                ephemeral=True
            )

        current = self.now_playing.get(interaction.guild_id)
        if not current:
            return await interaction.response.send_message(
                "❌ Сейчас ничего не играет",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🎵 Сейчас играет",
            description=f"**{current['title']}**",
            color=discord.Color.purple()
        )

        if current.get('duration'):
            embed.add_field(
                name="Длительность",
                value=f"{current['duration']} сек",
                inline=False
            )

        if current.get('requester'):
            embed.add_field(
                name="Запрошено",
                value=current['requester'].mention,
                inline=False
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
