import time
import random
import re
import discord
from discord.ext import commands, tasks
from discord import app_commands
import database as db

class GiveawayView(discord.ui.View):
    def __init__(self, message_id: int = None):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🎉 Çəkilişə Qatıl", style=discord.ButtonStyle.primary, custom_id="giveaway_entry_button")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = self.message_id or interaction.message.id
        user_id = interaction.user.id
        
        added = db.add_giveaway_participant(msg_id, user_id)
        count = len(db.get_giveaway_participants(msg_id))

        if added:
            await interaction.response.send_message(f"🎉 **Təbrik edirik {interaction.user.mention}!** Çəkilişə uğurla qatıldınız! (Cəmi qatılan: {count})", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ **{interaction.user.mention}**, siz artıq bu çəkilişə qatılmısınız!", ephemeral=True)

class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(GiveawayView())
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(seconds=10)
    async def check_giveaways(self):
        active_giveaways = db.get_active_giveaways()
        now = int(time.time())

        for msg_id, channel_id, guild_id, prize, winner_count, end_timestamp in active_giveaways:
            if now >= end_timestamp:
                db.mark_giveaway_ended(msg_id)
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                try:
                    msg = await channel.fetch_message(msg_id)
                except Exception:
                    continue

                participants = db.get_giveaway_participants(msg_id)

                if not participants:
                    embed = discord.Embed(
                        title="🎉 ÇƏKİLİŞ BİTDİ (Qalib Yoxdur)",
                        description=f"**Mükafat:** {prize}\n\n❌ Heç kim çəkilişə qatılmadığı üçün qalib seçilmədi.",
                        color=discord.Color.red()
                    )
                    await msg.edit(embed=embed, view=None)
                    await channel.send(f"⚠️ **{prize}** çəkilişi başa çatdı, lakin heç kim qatılmadığı üçün qalib seçilmədi!")
                else:
                    winners_count = min(len(participants), winner_count)
                    winner_ids = random.sample(participants, winners_count)
                    winner_mentions = ", ".join([f"<@{uid}>" for uid in winner_ids])

                    embed = discord.Embed(
                        title="🎉 ÇƏKİLİŞ BAŞA ÇATDI!",
                        description=f"**Mükafat:** {prize}\n**Qalib(lər):** {winner_mentions}\n**Cəmi Qatılan:** `{len(participants)}` nəfər",
                        color=discord.Color.gold()
                    )
                    await msg.edit(embed=embed, view=None)
                    await channel.send(f"🎊 **TEBRİKLƏR!** {winner_mentions}\nSiz **{prize}** çəkilişində qalib gəldiniz! 🥳")

    @commands.hybrid_command(name="gstart", description="[Admin] Yeni çəkiliş başladın.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        duration="Çəkiliş vaxtı (məs: 10s, 5m, 2h, 1d)",
        winners="Qalib sayı (məs: 1)",
        prize="Mükafatın adı"
    )
    async def gstart(self, ctx: commands.Context, duration: str, winners: int, prize: str):
        seconds = db.parse_duration(duration)
        if seconds <= 0:
            await ctx.send("❌ Yanlış vaxt formatı! Nümunə: `10m` (10 dəqiqə), `2h` (2 saat), `1d` (1 gün).", ephemeral=True)
            return

        if winners <= 0:
            await ctx.send("❌ Qalib sayı ən azı 1 olmalıdır!", ephemeral=True)
            return

        end_timestamp = int(time.time()) + seconds

        embed = discord.Embed(
            title=f"🎉 ÇƏKİLİŞ: {prize}",
            description=f"Qatılmaq üçün aşağıdakı **🎉 Çəkilişə Qatıl** düyməsinə klikləyin!\n\n"
                        f"🏆 **Qalib Sayı:** `{winners}`\n"
                        f"⏱️ **Bitiş Vaxtı:** <t:{end_timestamp}:R> (<t:{end_timestamp}:f>)\n"
                        f"👑 **Təşkilatçı:** {ctx.author.mention}",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Qafqaz Community Giveaway System")

        msg = await ctx.send(embed=embed)
        view = GiveawayView(message_id=msg.id)
        await msg.edit(view=view)

        db.add_giveaway(msg.id, ctx.channel.id, ctx.guild.id, prize, winners, end_timestamp)

async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
