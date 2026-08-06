import random
import time
import discord
from discord.ext import commands
from discord import app_commands
import database as db

class LevelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_and_grant_level_roles(self, member: discord.Member, new_level: int) -> list:
        granted_roles = []
        level_roles = db.get_level_roles(member.guild.id)
        for lvl, role_id in level_roles:
            if new_level >= lvl:
                role = member.guild.get_role(role_id)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                        granted_roles.append(role)
                    except Exception as e:
                        print(f"[ERROR] Rol verilərkən xəta: {e}")
        return granted_roles

    async def send_level_up_notice(self, member: discord.Member, new_level: int, new_roles: list, fallback_channel: discord.TextChannel = None):
        guild = member.guild
        target_channel = None
        saved_channel_id = db.get_guild_level_channel_id(guild.id)
        
        if saved_channel_id:
            target_channel = guild.get_channel(saved_channel_id)
        
        if target_channel is None:
            for ch in guild.text_channels:
                if "seviye" in ch.name.lower() or "level" in ch.name.lower():
                    target_channel = ch
                    break

        if target_channel is None:
            target_channel = fallback_channel

        if target_channel is None:
            return

        role_text = ""
        if new_roles:
            role_names = ", ".join([f"**{r.name}**" for r in new_roles])
            role_text = f"\n🎖️ **Qazanılan Yeni Rol(lar):** {role_names}"

        embed = discord.Embed(
            title="🎉 SƏVİYYƏ ATLANDI!",
            description=f"Təbrik edirik {member.mention}!\nSənin aktivliyin **Qafqaz Community** serverində yüksəlir!{role_text}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Yeni Səviyyə", value=f"🏆 **Level {new_level}**", inline=True)
        embed.add_field(name="Növbəti Hədəf", value=f"✨ `{db.xp_needed_for_level(new_level)} XP`", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Qafqaz Community Bot • XP System")

        try:
            await target_channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Level mesajı göndərilərkən xəta: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        current_time = int(time.time())

        xp, level, last_msg = db.get_user_data(user_id, guild_id)

        # HƏR MESAJA XP: 2-3 XP verilir
        gained_xp = random.randint(2, 3)
        new_xp = xp + gained_xp
        needed_xp = db.xp_needed_for_level(level)

        if new_xp >= needed_xp:
            new_xp -= needed_xp
            new_level = level + 1
            db.update_user_data(user_id, guild_id, new_xp, new_level, current_time)

            new_roles = await self.check_and_grant_level_roles(message.author, new_level)
            await self.send_level_up_notice(message.author, new_level, new_roles, message.channel)
        else:
            db.update_user_data(user_id, guild_id, new_xp, level, current_time)

    @commands.hybrid_command(name="rank", description="Özünüzün və ya başqa istifadəçinin XP və Level göstəricilərinə baxın.")
    @app_commands.describe(member="Göstəricilərinə baxmaq istədiyiniz istifadəçi")
    async def rank(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        if target.bot:
            await ctx.send("🤖 Botların XP və Level sistemi yoxdur!", ephemeral=True)
            return

        xp, level, _ = db.get_user_data(target.id, ctx.guild.id)
        rank_pos = db.get_user_rank(target.id, ctx.guild.id)
        needed_xp = db.xp_needed_for_level(level)

        progress_ratio = min(xp / needed_xp, 1.0)
        bar_length = 10
        filled = int(progress_ratio * bar_length)
        bar = "🟩" * filled + "⬜" * (bar_length - filled)

        embed = discord.Embed(
            title=f"📊 {target.display_name} - Qafqaz Community Statları",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="🏆 Level (Səviyyə)", value=f"`{level}`", inline=True)
        embed.add_field(name="✨ Cari XP", value=f"`{xp} / {needed_xp} XP`", inline=True)
        embed.add_field(name="🥇 Server Sıralaması", value=f"`#{rank_pos}`", inline=True)
        embed.add_field(name="📈 İrəliləyiş", value=f"{bar} (`{int(progress_ratio * 100)}%`)", inline=False)
        embed.set_footer(text="Qafqaz Community Bot")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="Serverin ən aktiv 10 istifadəçisini göstərir.")
    async def leaderboard(self, ctx: commands.Context):
        top_users = db.get_top_users(ctx.guild.id, limit=10)

        if not top_users:
            await ctx.send("📜 Hələ ki heç kim XP qazanmayıb!")
            return

        embed = discord.Embed(
            title="🏆 Qafqaz Community - Liderlər Lövhəsi (Top 10)",
            color=discord.Color.purple()
        )

        medal_icons = ["🥇", "🥈", "🥉"]

        description_lines = []
        for index, (user_id, level, xp) in enumerate(top_users, start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"İstifadəçi_{user_id}"
            prefix_icon = medal_icons[index - 1] if index <= 3 else f"**#{index}**"
            description_lines.append(f"{prefix_icon} **{name}** — Level `{level}` | `{xp} XP`")

        embed.description = "\n".join(description_lines)
        embed.set_footer(text="Qafqaz Community Bot • 7/24 Onlayn")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setlevelchannel", description="[Admin] Səviyyə atlama bildirişlərinin göndəriləcəyi kanalı seçin.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(channel="Kanal (seçməsəniz, əmrin yazıldığı kanal avtomatik təyin olunur)")
    async def setlevelchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        db.set_guild_level_channel(ctx.guild.id, target.id)
        await ctx.send(f"✅ Səviyyə atlama bildirişləri artıq {target.mention} kanalına göndəriləcək!")

    @commands.hybrid_command(name="addlevelrole", description="[Admin] Müəyyən səviyyə üçün avtomatik rol mükafatı təyin edin.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(level="Tələb olunan Level (məs: 5)", role="Veriləcək rol")
    async def addlevelrole(self, ctx: commands.Context, level: int, role: discord.Role):
        if level <= 0:
            await ctx.send("❌ Level müsbət ədəd olmalıdır!", ephemeral=True)
            return

        db.set_level_role(ctx.guild.id, level, role.id)
        await ctx.send(f"✅ **Level {level}** üçün avtomatik rol mükafatı təyin olundu: {role.mention}")

    @commands.hybrid_command(name="removelevelrole", description="[Admin] Səviyyə rol mükafatını silin.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(level="Silinəcək Level (məs: 5)")
    async def removelevelrole(self, ctx: commands.Context, level: int):
        db.remove_level_role(ctx.guild.id, level)
        await ctx.send(f"✅ **Level {level}** rol mükafatı ləğv edildi!")

    @commands.hybrid_command(name="levelroles", description="Serverdə təyin olunmuş bütün səviyyə rollarını göstərir.")
    async def levelroles(self, ctx: commands.Context):
        roles_data = db.get_level_roles(ctx.guild.id)
        if not roles_data:
            await ctx.send("📜 Hələ ki heç bir səviyyə rolu təyin olunmayıb!")
            return

        embed = discord.Embed(
            title="🎖️ Qafqaz Community - Səviyyə Rol Mükafatları",
            color=discord.Color.gold()
        )
        lines = []
        for lvl, role_id in roles_data:
            role = ctx.guild.get_role(role_id)
            role_mention = role.mention if role else f"Silinmiş Rol ({role_id})"
            lines.append(f"🏆 **Level {lvl}** $\rightarrow$ {role_mention}")

        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="addxp", description="[Admin] İstifadəçiyə xüsusi XP əlavə et.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(member="XP verilməli olan istifadəçi", amount="Əlavə ediləcək XP miqdarı")
    async def addxp(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            await ctx.send("❌ Miqdar müsbət ədəd olmalıdır!", ephemeral=True)
            return

        xp, level, last_msg = db.get_user_data(member.id, ctx.guild.id)
        new_xp = xp + amount
        needed_xp = db.xp_needed_for_level(level)

        leveled_up = False
        while new_xp >= needed_xp:
            new_xp -= needed_xp
            level += 1
            needed_xp = db.xp_needed_for_level(level)
            leveled_up = True

        db.update_user_data(member.id, ctx.guild.id, new_xp, level, last_msg)

        new_roles = []
        if leveled_up:
            new_roles = await self.check_and_grant_level_roles(member, level)
            await self.send_level_up_notice(member, level, new_roles, ctx.channel)

        msg = f"✅ **{member.display_name}** istifadəçisinə `{amount}` XP əlavə olundu!"
        if leveled_up:
            msg += f" Yeni Səviyyəsi: **Level {level}** 🚀"
            if new_roles:
                role_names = ", ".join([r.name for r in new_roles])
                msg += f" (Qazanılan Rol: **{role_names}**)"

        await ctx.send(msg)

async def setup(bot: commands.Bot):
    await bot.add_cog(LevelCog(bot))
