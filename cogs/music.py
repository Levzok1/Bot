import random

import discord
from discord.ext import commands
from discord import app_commands


MOOD_PLAYLISTS = {
    "весёлое": [
        "Playlist: Happy Hits (Spotify)",
        "Track: Pharrell Williams – Happy",
        "Track: Dua Lipa – Physical",
    ],
    "грусть": [
        "Playlist: Sad & Deep (Spotify)",
        "Track: Billie Eilish – lovely",
        "Track: Imagine Dragons – Demons",
    ],
    "злость": [
        "Playlist: Rage Gaming (Spotify)",
        "Track: Eminem – Lose Yourself",
        "Track: System Of A Down – Chop Suey!",
    ],
    "чилл": [
        "Playlist: Lo-Fi Beats (Spotify)",
        "Track: lofi geek – night city",
        "Track: Joji – slow dancing in the dark",
    ],
}


class SmartMusic(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="music",
        description="Подбор треков/плейлистов под настроение.",
    )
    @app_commands.describe(
        mood="Настроение: весёлое, грусть, злость, чилл и т.д."
    )
    async def music_recommend(
        self, interaction: discord.Interaction, mood: str
    ):
        mood_key = None
        text = mood.lower()
        for key in MOOD_PLAYLISTS.keys():
            if key in text:
                mood_key = key
                break

        if mood_key is None:
            mood_key = "чилл"

        options = MOOD_PLAYLISTS[mood_key]
        sample = random.sample(options, k=min(3, len(options)))

        embed = discord.Embed(
            title=f"🎧 Музыка под настроение: {mood_key}",
            description="\n".join(f"• {s}" for s in sample),
            color=discord.Color.purple(),
        )
        embed.set_footer(
            text="Это только рекомендации. Позже можно добавить полноценного музыкального бота."
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SmartMusic(bot))
