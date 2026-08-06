import asyncio
import re
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import database as db

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==========================================
    # AVTO-MODERASİYA, REKLAM VƏ SÖYÜŞ FİLTRİ
    # ==========================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        # İnzibatçılar/Adminlər filtrlərdən keçir
        if message.author.guild_permissions.manage_messages:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        content_lower = message.content.lower()

        # 1. Anti-Link (Discord dəvət linkləri və reklamlar)
        invite_regex = r"(discord\.gg\/|discord\.com\/invite\/|https?:\/\/)"
        is_link = bool(re.search(invite_regex, content_lower))

        # 2. Qara Siyahıdakı Sözlər (Banned Words)
        banned_words = db.get_banned_words(guild_id)
        contains_bad_word = any(bw in content_lower for bw in banned_words)

        if is_link or contains_bad_word:
            reason = "Reklam / İcazəsiz Link" if is_link else "Qadağan Olunmuş Söz"
            
            try:
                await message.delete()
            except Exception:
                pass

            warn_count = db.add_warning(user_id, guild_id)

            if warn_count >= 3:
                db.reset_warnings(user_id, guild_id)
                timeout_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
                
                try:
                    await message.author.timeout(timeout_until, reason="3 Dəfə Xəbərdarlıq Aldığı Üçün Avtomatik Mute (10 dəq)")
                    muted_role = discord.utils.get(message.guild.roles, name="Muted") or discord.utils.get(message.guild.roles, name="Susturulmuş")
                    if muted_role:
                        try:
                            await message.author.add_roles(muted_role, reason="3 Xəbərdarlıq Limiti")
                        except Exception:
                            pass

                    await message.channel.send(
                        f"🚫 {message.author.mention} **3 dəfə xəbərdarlıq aldığı üçün 10 dəqiqəlik MUTE edildi!**",
                        delete_after=10
                    )
                except Exception as e:
                    print(f"[ERROR Auto-Mute]: {e}")
            else:
                await message.channel.send(
                    f"⚠️ {message.author.mention}, **{reason}** istifadə etdiyiniz üçün mesajınız silindi! "
                    f"(Xəbərdarlıq: `{warn_count}/3`)",
                    delete_after=7
                )

    # ==========================================
    # QARA SİYAHI (KEY WORDS) ƏMRLƏRİ
    # ==========================================

    @commands.hybrid_command(name="addbadword", description="[Admin] Qara siyahıya söyüş və ya qadağan olunmuş söz əlavə et.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(word="Qadağan olunacaq söz")
    async def addbadword(self, ctx: commands.Context, word: str):
        added = db.add_banned_word(ctx.guild.id, word)
        if added:
            await ctx.send(f"✅ `{word}` sözü qara siyahıya əlavə olundu!")
        else:
            await ctx.send(f"⚠️ `{word}` artıq qara siyahıdadır!", ephemeral=True)

    @commands.hybrid_command(name="removebadword", description="[Admin] Qara siyahıdan sözü sil.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(word="Silinəcək söz")
    async def removebadword(self, ctx: commands.Context, word: str):
        removed = db.remove_banned_word(ctx.guild.id, word)
        if removed:
            await ctx.send(f"✅ `{word}` qara siyahıdan silindi!")
        else:
            await ctx.send(f"⚠️ `{word}` qara siyahıda tapılmadı!", ephemeral=True)

    @commands.hybrid_command(name="badwords", description="[Admin] Serverdə qadağan olunmuş bütün sözlərin siyahısı.")
    @commands.has_permissions(manage_messages=True)
    async def badwords(self, ctx: commands.Context):
        words = db.get_banned_words(ctx.guild.id)
        if not words:
            await ctx.send("📜 Hələ ki heç bir qadağan olunmuş söz əlavə edilməyib!")
            return

        words_str = ", ".join([f"`{w}`" for w in words])
        embed = discord.Embed(
            title="🚫 Qafqaz Community - Qara Siyahıdakı Sözlər",
            description=words_str,
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    # ==========================================
    # MODERASİYA ƏMRLƏRİ (BAN, MUTE, WARN)
    # ==========================================

    @commands.hybrid_command(name="ban", description="[Admin] İstifadəçini serverdən ban edin.")
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(member="Banlanacaq istifadəçi", reason="Ban səbəbi")
    async def ban_member(self, ctx: commands.Context, member: discord.Member, reason: str = "Səbəb göstərilməyib"):
        try:
            await member.ban(reason=reason)
            await ctx.send(f"⛔ **{member.display_name}** serverdən banlandı! (Səbəb: {reason})")
        except discord.Forbidden:
            await ctx.send("❌ Xəta: Botun bu istifadəçini Banlamaq üçün hüququ çatmır! (Botun rolunu serverdə istifadəçinin rolundan yuxarı qaldırın və Bot-a 'Yasakla/Ban Members' hüququ verin)", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Banlama xətası: {e}", ephemeral=True)

    @commands.hybrid_command(name="mute", description="[Admin] İstifadəçini müəyyən müddətə səssizləşdirin (Mute).")
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="Mute olunacaq istifadəçi", minutes="Dəqiqə (məs: 10)", reason="Səbəb")
    async def mute_member(self, ctx: commands.Context, member: discord.Member, minutes: int = 10, reason: str = "Səbəb göstərilməyib"):
        try:
            until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)

            # Əgər serverdə 'Muted' və ya 'Susturulmuş' rolu varsa, həmin rolu da əlavə edirik
            muted_role = discord.utils.get(ctx.guild.roles, name="Muted") or discord.utils.get(ctx.guild.roles, name="Susturulmuş")
            if muted_role:
                try:
                    await member.add_roles(muted_role, reason=reason)
                except Exception:
                    pass

            await ctx.send(f"🔇 **{member.display_name}** `{minutes}` dəqiqəlik MUTE edildi! (Səbəb: {reason})")
        except discord.Forbidden:
            await ctx.send("❌ Xəta: Botun bu istifadəçini Mute etmək üçün hüququ çatmır! (Botun rolunu istifadəçinin rolundan yuxarı qaldırın və Bot-a 'Zamana Aşımı/Moderate Members' hüququ verin)", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Mute xətası: {e}", ephemeral=True)

    @commands.hybrid_command(name="unmute", description="[Admin] İstifadəçinin mute cəzasını ləğv edin.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="Mutesi ləğv ediləcək istifadəçi")
    async def unmute_member(self, ctx: commands.Context, member: discord.Member):
        try:
            await member.timeout(None)
            muted_role = discord.utils.get(ctx.guild.roles, name="Muted") or discord.utils.get(ctx.guild.roles, name="Susturulmuş")
            if muted_role and muted_role in member.roles:
                try:
                    await member.remove_roles(muted_role)
                except Exception:
                    pass
            await ctx.send(f"🔊 **{member.display_name}** istifadəçisinin MUTE cəzası ləğv olunumşdur!")
        except discord.Forbidden:
            await ctx.send("❌ Xəta: Botun bu istifadəçinin Mute cəzasını ləğv etmək üçün hüququ çatmır!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Xəta: {e}", ephemeral=True)

    @commands.hybrid_command(name="warn", description="[Admin] İstifadəçiyə xəbərdarlıq verin.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(member="Xəbərdarlıq veriləcək istifadəçi", reason="Səbəb")
    async def warn_member(self, ctx: commands.Context, member: discord.Member, reason: str = "Qaydaları pozma"):
        warn_count = db.add_warning(member.id, ctx.guild.id)
        msg = f"⚠️ **{member.display_name}** xəbərdarlıq aldı! (Cəmi: `{warn_count}/3` | Səbəb: {reason})"

        if warn_count >= 3:
            db.reset_warnings(member.id, ctx.guild.id)
            until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
            try:
                await member.timeout(until, reason="3 Xəbərdarlıq Limiti")
                msg += "\n🚫 **3 xəbərdarlıq limitinə çatdığı üçün avtomatik 10 dəqiqə MUTE edildi!**"
            except Exception:
                pass

        await ctx.send(msg)

    @commands.hybrid_command(name="warnings", description="İstifadəçinin xəbərdarlıq sayına baxın.")
    @app_commands.describe(member="İstifadəçi")
    async def warnings(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        count = db.get_warnings(target.id, ctx.guild.id)
        await ctx.send(f"📊 **{target.display_name}** istifadəçisinin xəbərdarlıq sayı: `{count}/3`")

    @commands.hybrid_command(name="resetwarnings", description="[Admin] İstifadəçinin xəbərdarlıqlarını sıfırlayın.")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(member="İstifadəçi")
    async def resetwarnings(self, ctx: commands.Context, member: discord.Member):
        db.reset_warnings(member.id, ctx.guild.id)
        await ctx.send(f"✅ **{member.display_name}** üçün bütün xəbərdarlıqlar sıfırlandı!")

    @commands.hybrid_command(name="clear", aliases=["purge", "sil"], description="[Admin] Kanaldakı mesajları toplu şəkildə silin (Maksimum 100).")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(amount="Silinəcək mesaj sayı (1-100)")
    async def clear_messages(self, ctx: commands.Context, amount: int):
        if amount <= 0 or amount > 100:
            if ctx.interaction:
                await ctx.interaction.response.send_message("❌ Silinəcək mesaj sayı 1 ilə 100 arasında olmalıdır!", ephemeral=True)
            else:
                await ctx.send("❌ Silinəcək mesaj sayı 1 ilə 100 arasında olmalıdır!")
            return

        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
            try:
                deleted = await ctx.channel.purge(limit=amount)
                deleted_count = len(deleted)
                await ctx.interaction.followup.send(f"🧹 **{deleted_count}** ədəd mesaj uğurla silindi!", ephemeral=True)
            except discord.Forbidden:
                await ctx.interaction.followup.send("❌ Xəta: Botun bu kanalda **Mesajları İdarə Et (Manage Messages)** hüququ yoxdur!", ephemeral=True)
            except Exception as e:
                await ctx.interaction.followup.send(f"❌ Mesajlar silinərkən xəta yarandı: {e}", ephemeral=True)
        else:
            try:
                await ctx.message.delete()
                deleted = await ctx.channel.purge(limit=amount)
                deleted_count = len(deleted)
                msg = await ctx.send(f"🧹 **{deleted_count}** ədəd mesaj uğurla silindi!")
                await asyncio.sleep(4)
                await msg.delete()
            except discord.Forbidden:
                await ctx.send("❌ Xəta: Botun bu kanalda **Mesajları İdarə Et (Manage Messages)** hüququ yoxdur!")
            except Exception as e:
                await ctx.send(f"❌ Mesajlar silinərkən xəta yarandı: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
