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
        channel_id = log_channels.get(log_type)
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
        embed = discord.Embed(
            title="📥 Serverə Yeni İştirakçı Qatıldı (giriş-çıkış-log)",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="İstifadəçi", value=f"{member.mention} ({member.name})", inline=True)
        embed.add_field(name="İstifadəçi ID", value=f"`{member.id}`", inline=True)
        created_at = member.created_at.strftime("%d.%m.%Y %H:%M")
        embed.add_field(name="Hesab Yaradılma Tarixi", value=f"`{created_at}`", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)

        await self.send_log(member.guild, "giriş-çıkış-log", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="📤 İştirakçı Serverdən Ayrıldı (giriş-çıkış-log)",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="İstifadəçi", value=f"{member.display_name} ({member.name})", inline=True)
        embed.add_field(name="İstifadəçi ID", value=f"`{member.id}`", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)

        await self.send_log(member.guild, "giriş-çıkış-log", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Nikneym dəyişikliyi (isim-log)
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

        # Rol dəyişikliyi (rol-log)
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

    # ==========================================
    # DASHBOARD VƏ SETTINGS COMMANDS
    # ==========================================

    @commands.hybrid_command(name="logs", description="Serverin Bütün Log Sisteminin Panelinə (Dashboard) baxın.")
    async def logs_dashboard(self, ctx: commands.Context):
        log_channels = db.get_log_channels(ctx.guild.id)
        now_str = datetime.datetime.now().strftime("%d.%m.%Y – %H:%M:%S")

        def status_str(l_type: str) -> str:
            ch_id = log_channels.get(l_type)
            if ch_id:
                ch = ctx.guild.get_channel(ch_id)
                if ch:
                    return f"🟢 {ch.mention}"
            return "🔘 `Deaktif`"

        embed = discord.Embed(
            title="📋 QAFQAZ GAMING COMMUNITY AZ Logları",
            color=discord.Color.dark_theme(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        mod_logs_desc = (
            f"• 👤 · **ban-log:** {status_str('ban-log')}\n"
            f"• 👤 · **mute-log:** {status_str('mute-log')}\n"
            f"• ⛓️ · **jail-log:** {status_str('jail-log')}\n"
            f"• 🛠️ · **mod-log:** {status_str('mod-log')}"
        )

        genel_logs_desc = (
            f"🎭 `@` · **rol-log:** {status_str('rol-log')}  |  "
            f"🎭 ➕ · **tepki-log:** {status_str('tepki-log')}  |  "
            f"😀 · **emoji-log:** {status_str('emoji-log')}\n"
            f"📞 ⚙️ · **talep-log:** {status_str('talep-log')}  |  "
            f"💬 · **mesaj-log:** {status_str('mesaj-log')}  |  "
            f"🏆 · **seviye-log:** {status_str('seviye-log')}\n"
            f"🏷️ · **isim-log:** {status_str('isim-log')}  |  "
            f"🔊 · **ses-log:** {status_str('ses-log')}  |  "
            f"#️⃣ · **kanal-log:** {status_str('kanal-log')}\n"
            f"🔗 · **davet-log:** {status_str('davet-log')}  |  "
            f"📥📤 · **giriş-çıkış-log:** {status_str('giriş-çıkış-log')}  |  "
            f"#️⃣ · **tag-log:** {status_str('tag-log')}"
        )

        embed.add_field(name="🛡️ Moderasyon Logları:", value=mod_logs_desc, inline=False)
        embed.add_field(name="📜 Genel Loglar:", value=genel_logs_desc, inline=False)

        embed.set_thumbnail(url="https://i.imgur.com/b4z0S8u.png")
        embed.set_footer(text=f"Sorgulayan: {ctx.author.display_name} | Son güncellenme: {now_str}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setlogchannel", description="[Admin] Müəyyən log növü üçün kanalı təyin edin və ya silin.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        log_type="Log növü (məs: mesaj-log, giriş-çıkış-log, mod-log...)",
        channel="Logların göndəriləcəyi kanal (seçməsəniz, ləğv olunur)"
    )
    @app_commands.choices(log_type=[
        app_commands.Choice(name=lt, value=lt) for lt in LOG_TYPES
    ])
    async def setlogchannel(self, ctx: commands.Context, log_type: str, channel: discord.TextChannel = None):
        if log_type not in LOG_TYPES:
            await ctx.send(f"❌ Yanlış log növü! Nümunələr: `{', '.join(LOG_TYPES[:5])}...`", ephemeral=True)
            return

        if channel:
            db.set_log_channel(ctx.guild.id, log_type, channel.id)
            await ctx.send(f"✅ **{log_type}** üçün log kanalı təyin olundu: {channel.mention}")
        else:
            db.remove_log_channel(ctx.guild.id, log_type)
            await ctx.send(f"✅ **{log_type}** ləğv edildi (Deaktif).")

async def setup(bot: commands.Bot):
    await bot.add_cog(LogsCog(bot))
