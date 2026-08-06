import asyncio
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import database as db

# ==========================================
# PERSISTENT TICKET BUTTONS & VIEWS
# ==========================================

class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📩 Dəstək Bileti Aç",
        style=discord.ButtonStyle.primary,
        custom_id="create_ticket_button_persistent",
        emoji="📩"
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        # Yoxlayırıq istifadəçinin artıq bilet kanalı var yoxsa yox
        existing_channel = discord.utils.get(guild.text_channels, name=f"ticket-{user.name.lower()}")
        if existing_channel:
            await interaction.response.send_message(
                f"⚠️ Sizin artıq açıq biletiniz var: {existing_channel.mention}",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Bilet kanalı üçün icazələr
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # İnzibatçı rollarına baxış icazəsi veririk
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Kateqoriya seçimi (varsa bilet kateqoriyası)
        category = discord.utils.get(guild.categories, name="DƏSTƏK BİLETLƏRİ") or discord.utils.get(guild.categories, name="TICKETS")

        try:
            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{user.name}",
                category=category,
                overwrites=overwrites,
                topic=f"Dəstək biletinin sahibi: {user.name} ({user.id})"
            )

            # Ticket kanalı daxilindəki embed
            embed = discord.Embed(
                title="📩 QAFQAZ GAMING COMMUNITY - Dəstək Mərkəzi",
                description=f"Xoş gəldiniz {user.mention}!\n"
                            f"Zəhmət olmasa probleminizi və ya sualınızı ətraflı şəkildə qeyd edin.\n"
                            f"Adminlərimiz ən qısa zamanda sizə cavab verəcəkdir.\n\n"
                            f"📌 *Bileti bağlamaq üçün aşağıdakı düyməyə klikləyin.*",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text="Qafqaz Community Support System")

            view = TicketActionView()
            await ticket_channel.send(content=f"{user.mention} | Adminlərimiz köməyinizə gələcəkdir.", embed=embed, view=view)

            await interaction.followup.send(f"✅ Dəstək biletiniz uğurla açıldı: {ticket_channel.mention}", ephemeral=True)

            # Log kanalına hesabat (talep-log)
            log_channels = db.get_log_channels(guild.id)
            log_ch_id = log_channels.get("talep-log")
            if log_ch_id:
                log_ch = guild.get_channel(log_ch_id)
                if log_ch:
                    log_embed = discord.Embed(
                        title="📩 Yeni Dəstək Bileti Açıldı (talep-log)",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.now(datetime.timezone.utc)
                    )
                    log_embed.add_field(name="İstifadəçi", value=user.mention, inline=True)
                    log_embed.add_field(name="Bilet Kanalı", value=ticket_channel.mention, inline=True)
                    await log_ch.send(embed=log_embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Bilet kanalı yaradılarkən xəta: {e}", ephemeral=True)

class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Bileti Bağla",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket_button_persistent",
        emoji="🔒"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels and not interaction.user.guild_permissions.administrator:
            # Əgər istifadəçi bilet sahibidirsə də bağlaya bilsin
            if not interaction.channel.name.startswith(f"ticket-{interaction.user.name.lower()}"):
                await interaction.response.send_message("❌ Bu bileti yalnız Adminlər və ya bilet sahibi bağlaya bilər!", ephemeral=True)
                return

        await interaction.response.send_message("🔒 **Bilet 5 saniyə sonra avtomatik olaraq bağlanır və silinir...**")
        
        # Log göndəririk (talep-log)
        guild = interaction.guild
        log_channels = db.get_log_channels(guild.id)
        log_ch_id = log_channels.get("talep-log")
        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch:
                log_embed = discord.Embed(
                    title="🔒 Dəstək Bileti Bağlandı (talep-log)",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                log_embed.add_field(name="Bağlayan Şəxs", value=interaction.user.mention, inline=True)
                log_embed.add_field(name="Kanal Adı", value=f"`{interaction.channel.name}`", inline=True)
                await log_ch.send(embed=log_embed)

        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Dəstək bileti bağlandı.")
        except Exception as e:
            print(f"[ERROR Delete Ticket Channel]: {e}")

class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(TicketSetupView())
        self.bot.add_view(TicketActionView())

    @commands.hybrid_command(name="ticketsetup", description="[Admin] Dəstək Bilet Paneli Mesajını göndərir.")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📩 QAFQAZ GAMING COMMUNITY - Dəstək Mərkəzi",
            description="Probleminizi həll etmək, suallarınızı vermək və ya Admin heyəti ilə əlaqə saxlamaq üçün aşağıdakı **📩 Dəstək Bileti Aç** düyməsinə klikləyin!\n\n"
                        "📌 *Düyməyə basdıqda sizə xüsusi gizli bilet kanalı açılacaqdır.*",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/b4z0S8u.png")
        embed.set_footer(text="Qafqaz Community Support System")

        view = TicketSetupView()
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))
