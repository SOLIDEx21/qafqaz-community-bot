import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web
import database as db

# .env faylından mühit dəyişənlərini yükləyirik
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot hüquqları (Intents)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot Obyekti
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
# DİNAMİK COG YÜKLƏYİCİ (MODULAR ARCHITECTURE)
# ==========================================
async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                print(f"[COG LOADED] {cog_name} uğurla yükləndi.")
            except Exception as e:
                print(f"[COG ERROR] {cog_name} yüklənərkən xəta: {e}")

# ==========================================
# ON READY
# ==========================================
@bot.event
async def on_ready():
    db.init_db()
    asyncio.create_task(start_web_server())

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

# ==========================================
# BOTU BAŞLATMAQ
# ==========================================
async def main():
    async with bot:
        await load_extensions()
        if not TOKEN or TOKEN == "BURAYA_DISCORD_TOKENINIZI_YAZIN":
            print("❌ XƏTA: .env faylına düzgün DISCORD_TOKEN daxil edin!")
        else:
            await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
