import os
import sqlite3
import random
import time
import asyncio
import re
import discord
from discord.ext import commands, tasks
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
    """Məlumat bazasını, istifadəçi, tənzimləmə və çəkiliş cədvəllərini yaradır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # XP və Level Cədvəli
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
    
    # Server Tənzimləmələri
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            level_channel_id INTEGER
        )
    """)
    
    # Çəkilişlər (Giveaway) Cədvəli
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS giveaways (
            giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER UNIQUE,
            channel_id INTEGER,
            guild_id INTEGER,
            prize TEXT,
            winner_count INTEGER,
            end_timestamp INTEGER,
            ended INTEGER DEFAULT 0
        )
    """)
    
    # Çəkilişə Qatılanlar Cədvəli
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_participants (
            message_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY (message_id, user_id)
        )
    """)

    conn.commit()
    conn.close()

# --- XP Məntiqi ---
def get_user_data(user_id: int, guild_id: int):
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT level_channel_id FROM guild_settings WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_rank(user_id: int, guild_id: int):
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
    return (level + 1) * 100

# --- Giveaway DB funksiyaları ---
def add_giveaway(message_id: int, channel_id: int, guild_id: int, prize: str, winner_count: int, end_timestamp: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO giveaways (message_id, channel_id, guild_id, prize, winner_count, end_timestamp, ended)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (message_id, channel_id, guild_id, prize, winner_count, end_timestamp))
    conn.commit()
    conn.close()

def toggle_giveaway_participant(message_id: int, user_id: int) -> bool:
    """İstifadəçini çəkilişə əlavə edir və ya çıxarır. Əgər əlavə olundusa True, çıxarıldısa False qaytarır."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM giveaway_participants WHERE message_id = ? AND user_id = ?", (message_id, user_id))
    exists = cursor.fetchone()
    
    if exists:
        cursor.execute("DELETE FROM giveaway_participants WHERE message_id = ? AND user_id = ?", (message_id, user_id))
        joined = False
    else:
        cursor.execute("INSERT INTO giveaway_participants (message_id, user_id) VALUES (?, ?)", (message_id, user_id))
        joined = True

    conn.commit()
    conn.close()
    return joined

def get_giveaway_participants(message_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM giveaway_participants WHERE message_id = ?", (message_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_active_giveaways():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, channel_id, guild_id, prize, winner_count, end_timestamp FROM giveaways WHERE ended = 0")
    rows = cursor.fetchall()
    conn.close()
    return rows

def mark_giveaway_ended(message_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))
    conn.commit()
    conn.close()

def parse_duration(duration_str: str) -> int:
    """Məsələn '10s', '5m', '2h', '1d' daxil etdikdə saniyəyə çevirir."""
    match = re.match(r"^(\d+)([smhd])$", duration_str.lower().strip())
    if not match:
        return 0
    value, unit = int(match.group(1)), match.group(2)
    unit_seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    return value * unit_seconds.get(unit, 0)

# ==========================================
# GIVEAWAY DÜYMƏSİ (UI VIEW)
# ==========================================
class GiveawayView(discord.ui.View):
    def __init__(self, message_id: int = None):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🎉 Çəkilişə Qatıl", style=discord.ButtonStyle.primary, custom_id="giveaway_entry_button")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = self.message_id or interaction.message.id
        user_id = interaction.user.id
        
        joined = toggle_giveaway_participant(msg_id, user_id)
        count = len(get_giveaway_participants(msg_id))

        if joined:
            await interaction.response.send_message(f"🎉 **Təbrik edirik {interaction.user.mention}!** Çəkilişə uğurla qatıldınız! (Cəmi qatılan: {count})", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ **{interaction.user.mention}**, siz çəkilişdən çıxdınız. (Cəmi qatılan: {count})", ephemeral=True)

# ==========================================
# BOT HADİSƏLƏRİ VƏ BACKGROUND TASK
# ==========================================
@tasks.loop(seconds=10)
async def check_giveaways():
    """Hər 10 saniyədən bir vaxtı bitən çəkilişləri yoxlayır və qalibləri elan edir."""
    active_giveaways = get_active_giveaways()
    now = int(time.time())

    for msg_id, channel_id, guild_id, prize, winner_count, end_timestamp in active_giveaways:
        if now >= end_timestamp:
            mark_giveaway_ended(msg_id)
            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            try:
                msg = await channel.fetch_message(msg_id)
            except Exception:
                continue

            participants = get_giveaway_participants(msg_id)

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

@bot.event
async def on_ready():
    init_db()
    # Web serveri arxa fonda başladırıq (Render Free Tier üçün)
    asyncio.create_task(start_web_server())
    
    # Düzgün düymə idarəçiliyi üçün persistent view register edirik
    bot.add_view(GiveawayView())
    
    # Çəkiliş taymerini başladırıq
    if not check_giveaways.is_running():
        check_giveaways.start()

    try:
        synced = await bot.tree.sync()
        print(f"[SUCCESS] Qafqaz Community Bot aktivdir! {len(synced)} eded slash (/) emri sinxronlasdirildi.")
    except Exception as e:
        print(f"[ERROR] Slash emrleri sinxronlasdirilarken xeta yarandi: {e}")
    
    print(f"[INFO] Bot adi: {bot.user.name} | ID: {bot.user.id}")
    print("[INFO] Qafqaz Community Discord serveri ucun 7/24 hazir veziyyetdedir!")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    user_id = message.author.id
    guild_id = message.guild.id
    current_time = int(time.time())

    xp, level, last_msg = get_user_data(user_id, guild_id)

    # HER MESAJA XP: 2-3 XP verilir
    gained_xp = random.randint(2, 3)
    new_xp = xp + gained_xp
    needed_xp = xp_needed_for_level(level)

    if new_xp >= needed_xp:
        new_xp -= needed_xp
        new_level = level + 1
        update_user_data(user_id, guild_id, new_xp, new_level, current_time)

        target_channel = None
        saved_channel_id = get_guild_level_channel_id(guild_id)
        
        if saved_channel_id:
            target_channel = message.guild.get_channel(saved_channel_id)
        
        if target_channel is None:
            for ch in message.guild.text_channels:
                if "seviye" in ch.name.lower() or "level" in ch.name.lower():
                    target_channel = ch
                    break

        if target_channel is None:
            target_channel = message.channel

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

    await bot.process_commands(message)

# ==========================================
# XP VƏ LEVEL ƏMRLƏRİ
# ==========================================

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

@bot.hybrid_command(name="setlevelchannel", description="[Admin] Səviyyə atlama bildirişlərinin göndəriləcəyi kanalı seçin.")
@commands.has_permissions(administrator=True)
@app_commands.describe(channel="Level atlama bildirişlərinin düşəcəyi kanal")
async def setlevelchannel(ctx: commands.Context, channel: discord.TextChannel):
    set_guild_level_channel(ctx.guild.id, channel.id)
    await ctx.send(f"✅ Səviyyə atlama bildirişləri artıq {channel.mention} kanalına göndəriləcək!")

# ==========================================
# GIVEAWAY (ÇƏKİLİŞ) ƏMRLƏRİ
# ==========================================

@bot.hybrid_command(name="gstart", description="[Admin] Yeni çəkiliş başlaşdırın.")
@commands.has_permissions(manage_messages=True)
@app_commands.describe(
    duration="Çəkiliş vaxtı (məs: 10s, 5m, 2h, 1d)",
    winners="Qalib sayı (məs: 1)",
    prize="Mükafatın adı"
)
async def gstart(ctx: commands.Context, duration: str, winners: int, prize: str):
    seconds = parse_duration(duration)
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

    add_giveaway(msg.id, ctx.channel.id, ctx.guild.id, prize, winners, end_timestamp)

@bot.hybrid_command(name="greroll", description="[Admin] Bitmiş çəkilişdə yeni qalib seçin.")
@commands.has_permissions(manage_messages=True)
@app_commands.describe(message_id="Çəkiliş mesajının ID-si")
async def greroll(ctx: commands.Context, message_id: str):
    try:
        msg_id = int(message_id)
    except ValueError:
        await ctx.send("❌ Yanlış Mesaj ID-si!", ephemeral=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT prize, winner_count FROM giveaways WHERE message_id = ?", (msg_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await ctx.send("❌ Bu ID ilə çəkiliş tapılmadı!", ephemeral=True)
        return

    prize, winner_count = row
    participants = get_giveaway_participants(msg_id)

    if not participants:
        await ctx.send("❌ Bu çəkilişə heç kim qatılmadığı üçün yeni qalib seçilə bilməz!")
        return

    winners_count = min(len(participants), winner_count)
    new_winners = random.sample(participants, winners_count)
    winner_mentions = ", ".join([f"<@{uid}>" for uid in new_winners])

    await ctx.send(f"🎉 **YENİ QALİB SEÇİLDİ!**\n**Mükafat:** {prize}\n**Yeni Qalib(lər):** {winner_mentions} 🥳")

@bot.hybrid_command(name="gend", description="[Admin] Çəkilişi vaxtından əvvəl bitirin.")
@commands.has_permissions(manage_messages=True)
@app_commands.describe(message_id="Çəkiliş mesajının ID-si")
async def gend(ctx: commands.Context, message_id: str):
    try:
        msg_id = int(message_id)
    except ValueError:
        await ctx.send("❌ Yanlış Mesaj ID-si!", ephemeral=True)
        return

    mark_giveaway_ended(msg_id)
    await ctx.send("✅ Çəkiliş uğurla vaxtından əvvəl bitirildi! (Növbəti yoxlamada qalib elan olunacaq)")

@bot.hybrid_command(name="botinfo", description="Bot haqqında məlumat və server qaydalarını göstərir.")
async def botinfo(ctx: commands.Context):
    embed = discord.Embed(
        title="🇦🇿 Qafqaz Community Bot",
        description="Qafqaz Community serveri üçün xüsusi hazırlanmış XP, Level və Çəkiliş botu.",
        color=discord.Color.green()
    )
    embed.add_field(name="📌 XP Əmrləri", value="`/rank` - Statlarınıza baxın\n`/leaderboard` - Top 10 sıralaması\n`/setlevelchannel` - Level kanalı seçin", inline=False)
    embed.add_field(name="🎉 Çəkiliş Əmrləri", value="`/gstart <vaxt> <qalib_sayı> <mükafat>` - Yeni çəkiliş\n`/greroll <message_id>` - Yeni qalib seç\n`/gend <message_id>` - Çəkilişi bitir", inline=False)
    embed.set_footer(text="Qafqaz Community Bot • Render 7/24 Hosting Ready")

    await ctx.send(embed=embed)

# ==========================================
# BOTU BAŞLATMAQ
# ==========================================
if __name__ == "__main__":
    if not TOKEN or TOKEN == "BURAYA_DISCORD_BOT_TOKENINIZI_YAZIN":
        print("❌ XƏTA: .env faylına düzgün DISCORD_TOKEN daxil edin!")
    else:
        bot.run(TOKEN)
