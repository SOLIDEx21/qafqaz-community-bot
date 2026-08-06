import os
import sqlite3
import random
import time
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from aiohttp import web

# .env faylından mühit dəyişənlərini yükləyirik
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot üçün tələb olunan hüquqlar (Intents)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot obyekti
bot = commands.Bot(command_prefix="!", intents=intents, help_command=commands.DefaultHelpCommand())

# ==========================================
# WEBSERVER (Render.com Free Web Service üçün)
# ==========================================
async def handle_ping(request):
    return web.Response(text="Qafqaz Community Bot 7/24 Aktivdir!")

async def start_web_server():
    """Render.com-da Web Service-in pulsuz çalışması üçün kiçik HTTP server."""
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/health', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"[INFO] Web server port {port}-de aktivlesdirildi (Render Free Ready)")

# ==========================================
# MƏLUMAT BAZASI (SQLite) İDARƏETMƏSİ
# ==========================================
DB_NAME = "qafqaz_community.db"

def init_db():
    """Məlumat bazasını, istifadəçi cədvəlini və tənzimləmələri yaradır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER,
            guild_id INTEGER,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            last_msg INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            level_channel_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

def get_user_data(user_id: int, guild_id: int):
    """İstifadəçinin bazadakı məlumatlarını qaytarır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT xp, level, last_msg FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    row = cursor.fetchone()
    
    if row is None:
        cursor.execute("INSERT INTO users (user_id, guild_id, xp, level, last_msg) VALUES (?, ?, 0, 0, 0)", (user_id, guild_id))
        conn.commit()
        xp, level, last_msg = 0, 0, 0
    else:
        xp, level, last_msg = row

    conn.close()
    return xp, level, last_msg

def update_user_data(user_id: int, guild_id: int, xp: int, level: int, last_msg: int):
    """İstifadəçinin XP, Level və son mesaj vaxtını yeniləyir."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET xp = ?, level = ?, last_msg = ?
        WHERE user_id = ? AND guild_id = ?
    """, (xp, level, last_msg, user_id, guild_id))
    conn.commit()
    conn.close()

def set_guild_level_channel(guild_id: int, channel_id: int):
    """Server üçün səviyyə-atlama bildiriş kanalını bazada yadda saxlayır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO guild_settings (guild_id, level_channel_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET level_channel_id = excluded.level_channel_id
    """, (guild_id, channel_id))
    conn.commit()
    conn.close()

def get_guild_level_channel_id(guild_id: int):
    """Serverin səviyyə bildiriş kanalının ID-sini qaytarır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT level_channel_id FROM guild_settings WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_rank(user_id: int, guild_id: int):
    """İstifadəçinin server üzrə sıralamasını (Rank) hesablayır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id FROM users 
        WHERE guild_id = ? 
        ORDER BY level DESC, xp DESC
    """, (guild_id,))
    rows = cursor.fetchall()
    conn.close()

    for rank, row in enumerate(rows, start=1):
        if row[0] == user_id:
            return rank
    return len(rows)

def get_top_users(guild_id: int, limit: int = 10):
    """Server üzrə ən yüksək səviyyəli və XP-li istifadəçiləri qaytarır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, level, xp FROM users 
        WHERE guild_id = ? 
        ORDER BY level DESC, xp DESC 
        LIMIT ?
    """, (guild_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def xp_needed_for_level(level: int) -> int:
    """Növbəti səviyyəyə keçmək üçün tələb olunan XP hesablama düsturu."""
    return (level + 1) * 100

# ==========================================
# BOT HADİSƏLƏRİ (EVENTS)
# ==========================================

@bot.event
async def on_ready():
    init_db()
    # Web serveri arxa fonda başladırıq (Render Free Tier üçün)
    asyncio.create_task(start_web_server())

    try:
        synced = await bot.tree.sync()
        print(f"[SUCCESS] Qafqaz Community Bot aktivdir! {len(synced)} eded slash (/) emri sinxronlasdirildi.")
    except Exception as e:
        print(f"[ERROR] Slash emrleri sinxronlasdirilarken xeta yarandi: {e}")
    
    print(f"[INFO] Bot adi: {bot.user.name} | ID: {bot.user.id}")
    print("[INFO] Qafqaz Community Discord serveri ucun 7/24 hazir veziyyetdedir!")

@bot.event
async def on_message(message: discord.Message):
    # Botların öz mesajlarını və ya DM mesajlarını nəzərə almırıq
    if message.author.bot or message.guild is None:
        return

    user_id = message.author.id
    guild_id = message.guild.id
    current_time = int(time.time())

    xp, level, last_msg = get_user_data(user_id, guild_id)

    # HER MESAJA XP: Heç bir delay/cooldown olmadan hər mesaja 2 ilə 3 XP verilir
    gained_xp = random.randint(2, 3)
    new_xp = xp + gained_xp
    needed_xp = xp_needed_for_level(level)

    if new_xp >= needed_xp:
        new_xp -= needed_xp
        new_level = level + 1
        update_user_data(user_id, guild_id, new_xp, new_level, current_time)

        # Level atlama mesajı üçün kanalı təyin edirik
        target_channel = None
        saved_channel_id = get_guild_level_channel_id(guild_id)
        
        if saved_channel_id:
            target_channel = message.guild.get_channel(saved_channel_id)
        
        # Əgər xüsusi kanal seçilməyibsə, adı "seviye-atlama" və ya benzer olan kanalı avtomatik axtarırıq
        if target_channel is None:
            for ch in message.guild.text_channels:
                if "seviye" in ch.name.lower() or "level" in ch.name.lower():
                    target_channel = ch
                    break

        # Əgər heç bir kanal tapılmazsa, mesajın yazıldığı kanala göndərilir
        if target_channel is None:
            target_channel = message.channel

        # Təbrik mesajı göndəririk (mention ilə)
        embed = discord.Embed(
            title="🎉 SƏVİYYƏ ATLANDI!",
            description=f"Təbrik edirik {message.author.mention}!\nSənin aktivliyin **Qafqaz Community** serverində yüksəlir!",
            color=discord.Color.gold()
        )
        embed.add_field(name="Yeni Səviyyə", value=f"🏆 **Level {new_level}**", inline=True)
        embed.add_field(name="Növbəti Hədəf", value=f"✨ `{xp_needed_for_level(new_level)} XP`", inline=True)
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.set_footer(text="Qafqaz Community Bot • XP System")

        try:
            await target_channel.send(content=f"Hey {message.author.mention}!", embed=embed)
        except Exception as e:
            print(f"[ERROR] Level mesajı göndərilərkən xəta: {e}")
    else:
        update_user_data(user_id, guild_id, new_xp, level, current_time)

    # Prefiks əmrlərini işlətmək üçün vacibdir
    await bot.process_commands(message)

# ==========================================
# ƏMRLƏR (COMMANDS & SLASH COMMANDS)
# ==========================================

# 1. RANK / STATS ƏMRİ
@bot.hybrid_command(name="rank", description="Özünüzün və ya başqa istifadəçinin XP və Level göstəricilərinə baxın.")
@app_commands.describe(member="Göstəricilərinə baxmaq istədiyiniz istifadəçi")
async def rank(ctx: commands.Context, member: discord.Member = None):
    target = member or ctx.author
    if target.bot:
        await ctx.send("🤖 Botların XP və Level sistemi yoxdur!", ephemeral=True)
        return

    xp, level, _ = get_user_data(target.id, ctx.guild.id)
    rank_pos = get_user_rank(target.id, ctx.guild.id)
    needed_xp = xp_needed_for_level(level)

    # İrəliləyiş çubuğu (Progress bar)
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

# 2. LEADERBOARD (LİDERLƏR LÖVHƏSİ) ƏMRİ
@bot.hybrid_command(name="leaderboard", description="Serverin ən aktiv 10 istifadəçisini göstərir.")
async def leaderboard(ctx: commands.Context):
    top_users = get_top_users(ctx.guild.id, limit=10)

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

# 3. KÖMƏK ƏMRİ
@bot.hybrid_command(name="botinfo", description="Bot haqqında məlumat və server qaydalarını göstərir.")
async def botinfo(ctx: commands.Context):
    embed = discord.Embed(
        title="🇦🇿 Qafqaz Community Bot",
        description="Qafqaz Community serveri üçün xüsusi hazırlanmış XP və Level idarəetmə botu.",
        color=discord.Color.green()
    )
    embed.add_field(name="📌 Əmrlər", value="`/rank` - Statlarınıza baxın\n`/leaderboard` - Top 10 sıralaması\n`/setlevelchannel` - Level atlama kanalını təyin edin\n`/botinfo` - Bot haqqında məlumat", inline=False)
    embed.add_field(name="💡 XP Təlimatı", value="Kanallarda hər yazdığınız mesaja görə dərhal 2-3 XP qazanırsınız.", inline=False)
    embed.set_footer(text="Qafqaz Community Bot • Render 7/24 Hosting Ready")

    await ctx.send(embed=embed)

# 4. ADMİN: LEVEL ATLAMAK KANALINI TƏYİN ET
@bot.hybrid_command(name="setlevelchannel", description="[Admin] Səviyyə atlama bildirişlərinin göndəriləcəyi kanalı seçin.")
@commands.has_permissions(administrator=True)
@app_commands.describe(channel="Level atlama bildirişlərinin düşəcəyi kanal")
async def setlevelchannel(ctx: commands.Context, channel: discord.TextChannel):
    set_guild_level_channel(ctx.guild.id, channel.id)
    await ctx.send(f"✅ Səviyyə atlama bildirişləri artıq {channel.mention} kanalına göndəriləcək!")

@setlevelchannel.error
async def setlevelchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu əmri istifadə etmək üçün Administrator hüququnuz olmalıdır!", ephemeral=True)

# 5. ADMİN: XP ƏLAVƏ ET
@bot.hybrid_command(name="addxp", description="[Admin] İstifadəçiyə XP əlavə et.")
@commands.has_permissions(administrator=True)
@app_commands.describe(member="XP verilməli olan istifadəçi", amount="Əlavə ediləcək XP miqdarı")
async def addxp(ctx: commands.Context, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Miqdar müsbət ədəd olmalıdır!", ephemeral=True)
        return

    xp, level, last_msg = get_user_data(member.id, ctx.guild.id)
    new_xp = xp + amount
    needed_xp = xp_needed_for_level(level)

    leveled_up = False
    while new_xp >= needed_xp:
        new_xp -= needed_xp
        level += 1
        needed_xp = xp_needed_for_level(level)
        leveled_up = True

    update_user_data(member.id, ctx.guild.id, new_xp, level, last_msg)

    msg = f"✅ **{member.display_name}** istifadəçisinə `{amount}` XP əlavə olundu!"
    if leveled_up:
        msg += f" Yeni Səviyyəsi: **Level {level}** 🚀"

    await ctx.send(msg)

# Admin xətalarını tutmaq üçün
@addxp.error
async def addxp_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu əmri istifadə etmək üçün Administrator hüququnuz olmalıdır!", ephemeral=True)

# ==========================================
# BOTU BAŞLATMAQ
# ==========================================
if __name__ == "__main__":
    if not TOKEN or TOKEN == "BURAYA_DISCORD_BOT_TOKENINIZI_YAZIN":
        print("❌ XƏTA: .env faylına düzgün DISCORD_TOKEN daxil edin!")
    else:
        bot.run(TOKEN)
