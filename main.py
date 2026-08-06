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
    """Məlumat bazasını və bütün cədvəlləri yaradır."""
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
    
    # Avtomatik Səviyyə Rolları Cədvəli
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS level_roles (
            guild_id INTEGER,
            level INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, level)
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

# --- Level Role DB funksiyaları ---
def set_level_role(guild_id: int, level: int, role_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO level_roles (guild_id, level, role_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id
    """, (guild_id, level, role_id))
    conn.commit()
    conn.close()

def remove_level_role(guild_id: int, level: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM level_roles WHERE guild_id = ? AND level = ?", (guild_id, level))
    conn.commit()
    conn.close()

def get_level_roles(guild_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level ASC", (guild_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

async def check_and_grant_level_roles(member: discord.Member, new_level: int) -> list:
    granted_roles = []
    level_roles = get_level_roles(member.guild.id)
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

async def send_level_up_notice(member: discord.Member, new_level: int, new_roles: list, fallback_channel: discord.TextChannel = None):
    """Level atlama kartını müvafiq kanala (seviye-atlama) tərəf göndərir."""
    guild = member.guild
    target_channel = None
    saved_channel_id = get_guild_level_channel_id(guild.id)
    
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
    embed.add_field(name="Növbəti Hədəf", value=f"✨ `{xp_needed_for_level(new_level)} XP`", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Qafqaz Community Bot • XP System")

    try:
        await target_channel.send(embed=embed)
    except Exception as e:
        print(f"[ERROR] Level mesajı göndərilərkən xəta: {e}")

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

def add_giveaway_participant(message_id: int, user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM giveaway_participants WHERE message_id = ? AND user_id = ?", (message_id, user_id))
    exists = cursor.fetchone()
    
    if exists:
        conn.close()
        return False
    else:
        cursor.execute("INSERT INTO giveaway_participants (message_id, user_id) VALUES (?, ?)", (message_id, user_id))
        conn.commit()
        conn.close()
        return True

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
        
        added = add_giveaway_participant(msg_id, user_id)
        count = len(get_giveaway_participants(msg_id))

        if added:
            await interaction.response.send_message(f"🎉 **Təbrik edirik {interaction.user.mention}!** Çəkilişə uğurla qatıldınız! (Cəmi qatılan: {count})", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ **{interaction.user.mention}**, siz artıq bu çəkilişə qatılmısınız!", ephemeral=True)

# ==========================================
# BOT HADİSƏLƏRİ VƏ BACKGROUND TASK
# ==========================================
@tasks.loop(seconds=10)
async def check_giveaways():
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

# ==========================================
# GIVEAWAY GROUP COMMANDS (/giveaway start/reroll/end)
# ==========================================
giveaway_group = app_commands.Group(name="giveaway", description="Çəkiliş idarəetmə əmrləri")

@giveaway_group.command(name="start", description="[Admin] Yeni çəkiliş başladın.")
@app_commands.describe(
    duration="Çəkiliş vaxtı (məs: 10s, 5m, 2h, 1d)",
    winners="Qalib sayı (məs: 1)",
    prize="Mükafatın adı"
)
async def giveaway_start_slash(interaction: discord.Interaction, duration: str, winners: int, prize: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Bu əmri istifadə etmək üçün Mesajları İdarə Et hüququnuz olmalıdır!", ephemeral=True)
        return

    seconds = parse_duration(duration)
    if seconds <= 0:
        await interaction.response.send_message("❌ Yanlış vaxt formatı! Nümunə: `10m` (10 dəqiqə), `2h` (2 saat), `1d` (1 gün).", ephemeral=True)
        return

    if winners <= 0:
        await interaction.response.send_message("❌ Qalib sayı ən azı 1 olmalıdır!", ephemeral=True)
        return

    end_timestamp = int(time.time()) + seconds

    embed = discord.Embed(
        title=f"🎉 ÇƏKİLİŞ: {prize}",
        description=f"Qatılmaq üçün aşağıdakı **🎉 Çəkilişə Qatıl** düyməsinə klikləyin!\n\n"
                    f"🏆 **Qalib Sayı:** `{winners}`\n"
                    f"⏱️ **Bitiş Vaxtı:** <t:{end_timestamp}:R> (<t:{end_timestamp}:f>)\n"
                    f"👑 **Təşkilatçı:** {interaction.user.mention}",
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Qafqaz Community Giveaway System")

    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    view = GiveawayView(message_id=msg.id)
    await msg.edit(view=view)

    add_giveaway(msg.id, interaction.channel_id, interaction.guild_id, prize, winners, end_timestamp)

@giveaway_group.command(name="reroll", description="[Admin] Bitmiş çəkilişdə yeni qalib seçin.")
@app_commands.describe(message_id="Çəkiliş mesajının ID-si")
async def giveaway_reroll_slash(interaction: discord.Interaction, message_id: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Bu əmri istifadə etmək üçün hüququnuz çatmir!", ephemeral=True)
        return

    try:
        msg_id = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ Yanlış Mesaj ID-si!", ephemeral=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT prize, winner_count FROM giveaways WHERE message_id = ?", (msg_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        await interaction.response.send_message("❌ Bu ID ilə çəkiliş tapılmadı!", ephemeral=True)
        return

    prize, winner_count = row
    participants = get_giveaway_participants(msg_id)

    if not participants:
        await interaction.response.send_message("❌ Bu çəkilişə heç kim qatılmadığı üçün yeni qalib seçilə bilməz!", ephemeral=True)
        return

    winners_count = min(len(participants), winner_count)
    new_winners = random.sample(participants, winners_count)
    winner_mentions = ", ".join([f"<@{uid}>" for uid in new_winners])

    await interaction.response.send_message(f"🎉 **YENİ QALİB SEÇİLDİ!**\n**Mükafat:** {prize}\n**Yeni Qalib(lər):** {winner_mentions} 🥳")

@giveaway_group.command(name="end", description="[Admin] Çəkilişi vaxtından əvvəl bitirin.")
@app_commands.describe(message_id="Çəkiliş mesajının ID-si")
async def giveaway_end_slash(interaction: discord.Interaction, message_id: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Bu əmri istifadə etmək üçün hüququnuz çatmir!", ephemeral=True)
        return

    try:
        msg_id = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ Yanlış Mesaj ID-si!", ephemeral=True)
        return

    mark_giveaway_ended(msg_id)
    await interaction.response.send_message("✅ Çəkiliş uğurla vaxtından əvvəl bitirildi!")

bot.tree.add_command(giveaway_group)

# ==========================================
# ON READY
# ==========================================
@bot.event
async def on_ready():
    init_db()
    asyncio.create_task(start_web_server())
    bot.add_view(GiveawayView())
    
    if not check_giveaways.is_running():
        check_giveaways.start()

    # ANINDA (INSTANT) SLASH COMMAND SYNC
    try:
        global_synced = await bot.tree.sync()
        print(f"[GLOBAL SYNC] {len(global_synced)} qlobal slash əmri sinxronlaşdırıldı.")
    except Exception as e:
        print(f"[GLOBAL SYNC ERROR] {e}")

    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"[INSTANT SYNC] '{guild.name}' serveri üçün {len(synced)} slash əmri anında yeniləndi!")
        except Exception as e:
            print(f"[INSTANT SYNC ERROR] '{guild.name}' xətası: {e}")

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

        # Level rolunu avtomatik veririk
        new_roles = await check_and_grant_level_roles(message.author, new_level)
        # Səviyyə atlama bildirişini göndəririk
        await send_level_up_notice(message.author, new_level, new_roles, message.channel)
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
@app_commands.describe(channel="Kanal (seçməsəniz, əmrin yazıldığı kanal avtomatik təyin olunur)")
async def setlevelchannel(ctx: commands.Context, channel: discord.TextChannel = None):
    target = channel or ctx.channel
    set_guild_level_channel(ctx.guild.id, target.id)
    await ctx.send(f"✅ Səviyyə atlama bildirişləri artıq {target.mention} kanalına göndəriləcək!")

# --- LEVEL ROLE ADMİN ƏMRLƏRİ ---
@bot.hybrid_command(name="addlevelrole", description="[Admin] Müəyyən səviyyə üçün avtomatik rol mükafatı təyin edin.")
@commands.has_permissions(administrator=True)
@app_commands.describe(level="Tələb olunan Level (məs: 5)", role="Veriləcək rol")
async def addlevelrole(ctx: commands.Context, level: int, role: discord.Role):
    if level <= 0:
        await ctx.send("❌ Level müsbət ədəd olmalıdır!", ephemeral=True)
        return

    set_level_role(ctx.guild.id, level, role.id)
    await ctx.send(f"✅ **Level {level}** üçün avtomatik rol mükafatı təyin olundu: {role.mention}")

@bot.hybrid_command(name="removelevelrole", description="[Admin] Səviyyə rol mükafatını silin.")
@commands.has_permissions(administrator=True)
@app_commands.describe(level="Silinəcək Level (məs: 5)")
async def removelevelrole(ctx: commands.Context, level: int):
    remove_level_role(ctx.guild.id, level)
    await ctx.send(f"✅ **Level {level}** rol mükafatı ləğv edildi!")

@bot.hybrid_command(name="levelroles", description="Serverdə təyin olunmuş bütün səviyyə rollarını göstərir.")
async def levelroles(ctx: commands.Context):
    roles_data = get_level_roles(ctx.guild.id)
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

# --- ADMİN: XP ƏLAVƏ ET (/addxp) ---
@bot.hybrid_command(name="addxp", description="[Admin] İstifadəçiyə xüsusi XP əlavə et.")
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

    new_roles = []
    if leveled_up:
        new_roles = await check_and_grant_level_roles(member, level)
        await send_level_up_notice(member, level, new_roles, ctx.channel)

    msg = f"✅ **{member.display_name}** istifadəçisinə `{amount}` XP əlavə olundu!"
    if leveled_up:
        msg += f" Yeni Səviyyəsi: **Level {level}** 🚀"
        if new_roles:
            role_names = ", ".join([r.name for r in new_roles])
            msg += f" (Qazanılan Rol: **{role_names}**)"

    await ctx.send(msg)

@addxp.error
async def addxp_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu əmri istifadə etmək üçün Administrator hüququnuz olmalıdır!", ephemeral=True)

# --- ADMİN: MESAJ SİL / CLEAR / PURGE (/clear) ---
@bot.hybrid_command(name="clear", aliases=["purge", "sil"], description="[Admin] Kanaldakı mesajları toplu şəkildə silin (Maksimum 100).")
@commands.has_permissions(manage_messages=True)
@app_commands.describe(amount="Silinəcək mesaj sayı (1-100)")
async def clear_messages(ctx: commands.Context, amount: int):
    if amount <= 0 or amount > 100:
        await ctx.send("❌ Silinəcək mesaj sayı 1 ilə 100 arasında olmalıdır!", ephemeral=True)
        return

    try:
        deleted = await ctx.channel.purge(limit=amount)
        deleted_count = len(deleted)
        await ctx.send(f"🧹 **{deleted_count}** ədəd mesaj uğurla silindi!", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Mesajlar silinərkən xəta yarandı: {e}", ephemeral=True)

@clear_messages.error
async def clear_messages_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Bu əmri istifadə etmək üçün Mesajları İdarə Et hüququnuz olmalıdır!", ephemeral=True)

# Alternativ Prefiks/Hybrid Çəkiliş Əmrləri
@bot.hybrid_command(name="gstart", description="[Admin] Yeni çəkiliş başladın.")
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

@bot.hybrid_command(name="botinfo", description="Bot haqqında məlumat və server qaydalarını göstərir.")
async def botinfo(ctx: commands.Context):
    embed = discord.Embed(
        title="🇦🇿 Qafqaz Community Bot",
        description="Qafqaz Community serveri üçün xüsusi hazırlanmış XP, Level, Rol və Çəkiliş botu.",
        color=discord.Color.green()
    )
    embed.add_field(name="📌 Admin & Təmizlik Əmrləri", value="`/clear <say>` - Mesajları sil (maks 100)\n`/addxp <user> <amount>` - XP ver\n`/addlevelrole <level> <role>` - Rol təyin et", inline=False)
    embed.add_field(name="📌 XP & Rol Əmrləri", value="`/rank` - Statlarınıza baxın\n`/leaderboard` - Top 10\n`/levelroles` - Rol mükafatları", inline=False)
    embed.add_field(name="🎉 Çəkiliş Əmrləri", value="`/giveaway start <vaxt> <qalib_sayı> <mükafat>`\n`/gstart <vaxt> <qalib_sayı> <mükafat>`", inline=False)
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
