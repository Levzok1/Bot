# cogs/ai_moderation.py
import asyncio
import os
from collections import defaultdict, deque
from datetime import datetime

import discord
from discord.ext import commands

try:
    import openai
except ImportError:
    openai = None


# Простая роль, которой можно “обходить” фильтр
ACCESS_ROLE_NAME = "Bot Access"

# Простой список токсичных слов (можешь дополнять)
BAD_WORDS = [
    "дурак", "тупой", "идиот", "сука", "блять", "хуй", "пидор", "еблан",
]

# Анти-спам
SPAM_WINDOW = 10   # секунд
SPAM_LIMIT = 6     # сообщений за окно


def user_has_access(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.name == ACCESS_ROLE_NAME for r in member.roles)


class AIModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_history: dict[int, deque[datetime]] = defaultdict(
            lambda: deque(maxlen=SPAM_LIMIT * 2)
        )

        api_key = os.getenv("OPENAI_API_KEY")
        if openai and api_key:
            openai.api_key = api_key
            self.ai_enabled = True
        else:
            self.ai_enabled = False

    def is_toxic_simple(self, content: str) -> bool:
        text = content.lower()
        return any(bad in text for bad in BAD_WORDS)

    async def is_toxic_ai(self, content: str) -> bool:
        """Опциональная проверка через OpenAI. По умолчанию отключена."""
        if not self.ai_enabled:
            return False

        try:
            resp = await asyncio.to_thread(
                openai.ChatCompletion.create,
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты фильтр токсичных сообщений. Отвечай только 'yes' или 'no'."},
                    {"role": "user", "content": f"Сообщение: {content}"},
                ],
                max_tokens=1,
            )
            answer = resp["choices"][0]["message"]["content"].strip().lower()
            return answer.startswith("y")
        except Exception:
            return False

    def is_spam(self, message: discord.Message) -> bool:
        user_id = message.author.id
        now = datetime.utcnow()
        history = self.message_history[user_id]
        history.append(now)

        while history and (now - history[0]).total_seconds() > SPAM_WINDOW:
            history.popleft()

        return len(history) >= SPAM_LIMIT

    async def apply_temporary_mute(self, member: discord.Member, duration_seconds: int, reason: str):
        guild = member.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if muted_role is None:
            muted_role = await guild.create_role(name="Muted")

        await member.add_roles(muted_role, reason=reason)

        async def unmute_later():
            await asyncio.sleep(duration_seconds)
            if muted_role in member.roles:
                try:
                    await member.remove_roles(muted_role, reason="Авто-снятие мута")
                except discord.HTTPException:
                    pass

        self.bot.loop.create_task(unmute_later())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # админов/роль доступа не фильтруем
        if user_has_access(message.author):
            return

        toxic_simple = self.is_toxic_simple(message.content)
        spam = self.is_spam(message)

        toxic_ai = False
        # Если хочешь включить AI-фильтр — раскомментируй:
        # toxic_ai = await self.is_toxic_ai(message.content)

        if not (toxic_simple or toxic_ai or spam):
            return

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        reason_parts = []
        if toxic_simple:
            reason_parts.append("токсичность")
        if toxic_ai:
            reason_parts.append("AI-фильтр")
        if spam:
            reason_parts.append("спам")

        reason = ", ".join(reason_parts) or "нарушение правил"

        try:
            await message.channel.send(
                f"⚠ {message.author.mention}, сообщение удалено: **{reason}**.",
                delete_after=8
            )
        except discord.HTTPException:
            pass

        if spam:
            try:
                await self.apply_temporary_mute(message.author, duration_seconds=60, reason="Авто-мут за спам")
                await message.channel.send(
                    f"🔇 {message.author.mention} получил мут на **60 секунд** за спам.",
                    delete_after=8
                )
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AIModeration(bot))
