import datetime
import discord
from discord.ext import commands
from discord import app_commands
import database as db

LOG_TYPES = [
    "ban-log", "mute-log", "jail-log", "mod-log",
    "rol-log", "tepki-log", "emoji-log", "talep-log",
    "mesaj-log", "seviye-log", "isim-log", "ses-log",
    "kanal-log", "davet-log", "giriş-çıkış-log", "tag-log"
]

class LogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_log(self, guild: discord.Guild, log_type: str, embed: discord.Embed):
        if not guild:
            return
        log_channels = db.get_log_channels(guild.id)
        
        # Ban və Mute loglarını birləşdiririk
        target_log_type = log_type
        if log_type in ["ban-log", "mute-log"]:
            channel_id = log_channels.get("ban-log") or log_channels.get("mute-log")
        else:
            channel_id = log_channels.get(target_log_type)

        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    print(f"[LOG ERROR] {log_type} kanalına mesaj göndərilə bilmədi: {e}")

    # ==========================================
    # LOG EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        embed = discord.Embed(
            title="🗑️ Mesaj Silindi (mesaj-log)",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Müəllif", value=message.author.mention, inline=True)
        embed.add_field(name="Kanal", value=message.channel.mention, inline=True)
        embed.add_field(name="Məzmun", value=message.content or "*(Media/Embed)*", inline=False)
        embed.set_thumbnail(url=message.author.display_avatar.url)

        await self.send_log(message.guild, "mesaj-log", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.guild is None or before.content == after.content:
            return

        embed = discord.Embed(
            title="✏️ Mesaj Redaktə Edildi (mesaj-log)",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Müəllif", value=before.author.mention, inline=True)
        embed.add_field(name="Kanal", value=before.channel.mention, inline=True)
        embed.add_field(name="Əvvəlki Məzmun", value=before.content or "*(Boş)*", inline=False)
        embed.add_field(name="Yeni Məzmun", value=after.content or "*(Boş)*", inline=False)
        embed.set_thumbnail(url=before.author.display_avatar.url)

        await self.send_log(before.guild, "mesaj-log", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        member_count = guild.member_count

        embed = discord.Embed(
            title="🎉 YENİ İŞTİRAKÇI QATILDI!",
            description=f"Serverə **xoş gəldin** {member.mention}! Səninlə bərabər `{member_count}` nəfər olduq! 🥳",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        created_at = member.created_at.strftime("%d.%m.%Y %H:%M")
        embed.add_field(name="👤 İstifadəçi", value=f"{member.display_name} (`{member.name}`)", inline=True)
        embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="📅 Hesab Yaradılma Tarixi", value=f"`{created_at}`", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Qafqaz Gaming Community • Xoş Gəldiniz")

        await self.send_log(guild, "giriş-çıkış-log", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        member_count = guild.member_count

        embed = discord.Embed(
            title="📤 İŞTİRAKÇI AYRILDI",
            description=f"**{member.display_name}** serverdən ayrıldı. İndi `{member_count}` nəfər qaldıq.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Qafqaz Gaming Community")

        await self.send_log(guild, "giriş-çıkış-log", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            embed = discord.Embed(
                title="🏷️ Nikneym Dəyişdirildi (isim-log)",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="İstifadəçi", value=after.mention, inline=True)
            embed.add_field(name="Əvvəlki Ad", value=f"`{before.nick or before.name}`", inline=True)
            embed.add_field(name="Yeni Ad", value=f"`{after.nick or after.name}`", inline=True)
            embed.set_thumbnail(url=after.display_avatar.url)
            await self.send_log(after.guild, "isim-log", embed)

        if before.roles != after.roles:
            added_roles = [r for r in after.roles if r not in before.roles]
            removed_roles = [r for r in before.roles if r not in after.roles]

            if added_roles or removed_roles:
                embed = discord.Embed(
                    title="🎭 Rol Yenilənməsi (rol-log)",
                    color=discord.Color.purple(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="İstifadəçi", value=after.mention, inline=False)
                if added_roles:
                    embed.add_field(name="Əlavə Olunan Rol(lar)", value=", ".join([r.mention for r in added_roles]), inline=False)
                if removed_roles:
                    embed.add_field(name="Silinən Rol(lar)", value=", ".join([r.mention for r in removed_roles]), inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)
                await self.send_log(after.guild, "rol-log", embed)

        # Mute / Timeout yoxlanışı (mute-log)
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                until_str = after.timed_out_until.strftime("%d.%m.%Y %H:%M")
                embed = discord.Embed(
                    title="🔇 İstifadəçi MUTE Edildi (mute-log)",
                    color=discord.Color.dark_orange(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="İstifadəçi", value=after.mention, inline=True)
                embed.add_field(name="Mute Bitiş Vaxtı", value=f"`{until_str}`", inline=True)
                embed.set_thumbnail(url=after.display_avatar.url)
                await self.send_log(after.guild, "mute-log", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel != after.channel:
            embed = discord.Embed(
                title="🎙️ Səs Kanalı Aktivliyi (ses-log)",
                color=discord.Color.teal(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="İstifadəçi", value=member.mention, inline=True)

            if before.channel is None and after.channel is not None:
                embed.description = f"🔊 **{after.channel.name}** kanalına daxil oldu."
            elif before.channel is not None and after.channel is None:
                embed.description = f"🔇 **{before.channel.name}** kanalından çıxdı."
            elif before.channel is not None and after.channel is not None:
                embed.description = f"🔄 **{before.channel.name}** $\rightarrow$ **{after.channel.name}** kanalına keçdi."

            embed.set_thumbnail(url=member.display_avatar.url)
            await self.send_log(member.guild, "ses-log", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="📁 Yeni Kanal Yaradıldı (kanal-log)",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Kanal Adı", value=f"`#{channel.name}`", inline=True)
        embed.add_field(name="Kanal ID", value=f"`{channel.id}`", inline=True)
        await self.send_log(channel.guild, "kanal-log", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="🗑️ Kanal Silindi (kanal-log)",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Silinən Kanal", value=f"`#{channel.name}`", inline=True)
        embed.add_field(name="Kanal ID", value=f"`{channel.id}`", inline=True)
        await self.send_log(channel.guild, "kanal-log", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="⛔ İstifadəçi Banlandı (ban-log)",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Banlanan Şəxs", value=f"{user.mention} ({user.name})", inline=True)
        embed.add_field(name="ID", value=f"`{user.id}`", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)
        await self.send_log(guild, "ban-log", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="✅ İstifadəçinin Banı Qaldırıldı (mod-log)",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="İstifadəçi", value=f"{user.mention} ({user.name})", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)
        await self.send_log(guild, "mod-log", embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(LogsCog(bot))
