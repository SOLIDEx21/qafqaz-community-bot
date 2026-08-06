import asyncio
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import database as db

LOGO_URL = "https://raw.githubusercontent.com/SOLIDEx21/qafqaz-community-bot/main/assets/logo.png"
BANNER_URL = "https://raw.githubusercontent.com/SOLIDEx21/qafqaz-community-bot/main/assets/banner.png"

# ==========================================
# INTERACTIVE TICKET FORM MODAL & SELECT MENU
# ==========================================

class TicketFormModal(discord.ui.Modal):
    def __init__(self, category_key: str, category_label: str, category_icon: str):
        super().__init__(title=f"{category_icon} {category_label[:30]}")
        self.category_key = category_key
        self.category_label = category_label
        self.category_icon = category_icon

        self.subject = discord.ui.TextInput(
            label="Mövzu / Sualınızın Adı",
            placeholder="Məs: Level rolu verilmədi / Şikayətiniz var...",
            max_length=100,
            required=True
        )
        self.details = discord.ui.TextInput(
            label="Ətraflı Məlumat Və Ya Şikayətiniz",
            style=discord.TextStyle.paragraph,
            placeholder="Zəhmət olmasa probleminizi ətraflı və aydın şəkildə yazın...",
            max_length=1000,
            required=True
        )
        self.add_item(self.subject)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        clean_category_name = self.category_key.lower().replace(" ", "-")
        channel_name = f"ticket-{clean_category_name}-{user.name.lower()}"

        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if existing_channel:
            await interaction.response.send_message(
                f"⚠️ Sizin artıq bu kateqoriyada açıq biletiniz var: {existing_channel.mention}",
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

        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        category = discord.utils.get(guild.categories, name="DƏSTƏK BİLETLƏRİ") or discord.utils.get(guild.categories, name="TICKETS")

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Kateqoriya: {self.category_label} | İstifadəçi: {user.name} ({user.id})"
            )

            embed = discord.Embed(
                title=f"{self.category_icon} DƏSTƏK BİLETİ - {self.category_label.upper()}",
                description=f"Xoş gəldiniz {user.mention}!\n"
                            f"Form vasitəsilə göndərdiyiniz müraciət məlumatları aşağıdadır.\n"
                            f"Adminlərimiz ən qısa zamanda baxış keçirəcəkdir.",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="📌 Müraciət Mövzusu", value=f"`{self.subject.value}`", inline=False)
            embed.add_field(name="📝 Ətraflı Məlumat", value=self.details.value, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text="Qafqaz Gaming Community Support System")

            view = TicketActionView()
            await ticket_channel.send(content=f"{user.mention} | Heyy Adminlər, yeni dəstək müraciəti var!", embed=embed, view=view)

            await interaction.followup.send(f"✅ Dəstək biletiniz uğurla yaradıldı: {ticket_channel.mention}", ephemeral=True)

            # Log hesabatı (talep-log)
            log_channels = db.get_log_channels(guild.id)
            log_ch_id = log_channels.get("talep-log")
            if log_ch_id:
                log_ch = guild.get_channel(log_ch_id)
                if log_ch:
                    log_embed = discord.Embed(
                        title="📩 Yeni Dəstək Müraciəti (talep-log)",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.now(datetime.timezone.utc)
                    )
                    log_embed.add_field(name="İstifadəçi", value=user.mention, inline=True)
                    log_embed.add_field(name="Kateqoriya", value=f"`{self.category_label}`", inline=True)
                    log_embed.add_field(name="Mövzu", value=f"`{self.subject.value}`", inline=False)
                    log_embed.add_field(name="Kanal", value=ticket_channel.mention, inline=False)
                    await log_ch.send(embed=log_embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Bilet kanalı yaradılarkən xəta: {e}", ephemeral=True)

class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Ümumi Dəstək", value="umumi", description="Ümumi suallar və kömək müraciəti", emoji="💬"),
            discord.SelectOption(label="Texniki Dəstək / Bot Məsələsi", value="texniki", description="Bot xətaları və ya texniki problemlər", emoji="🛠️"),
            discord.SelectOption(label="Admin Şikayəti / Ədalətsizlik", value="sikayet", description="Şikayətlər və bildirişlər", emoji="⚖️"),
            discord.SelectOption(label="VİP & Sponsorluq Müraciəti", value="vip", description="Server əməkdaşlığı və sponsorluq", emoji="💎")
        ]
        super().__init__(
            placeholder="⚙️ Müraciət etmək istədiyiniz Kateqoriyanı seçin...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select_persistent"
        )

    async def callback(self, interaction: discord.Interaction):
        category_map = {
            "umumi": ("Ümumi Dəstək", "💬"),
            "texniki": ("Texniki Dəstək", "🛠️"),
            "sikayet": ("Admin Şikayəti", "⚖️"),
            "vip": ("VİP Müraciəti", "💎")
        }
        val = self.values[0]
        label, icon = category_map.get(val, ("Dəstək", "📩"))

        modal = TicketFormModal(category_key=val, category_label=label, category_icon=icon)
        await interaction.response.send_modal(modal)

class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())

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
            if "ticket-" not in interaction.channel.name or interaction.user.name.lower() not in interaction.channel.name:
                await interaction.response.send_message("❌ Bu bileti yalnız Adminlər və ya bilet sahibi bağlaya bilər!", ephemeral=True)
                return

        await interaction.response.send_message("🔒 **Bilet 5 saniyə sonra avtomatik olaraq bağlanır və silinir...**")
        
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

    @commands.hybrid_command(name="ticketsetup", description="[Admin] Şəkilli Və Bannerli Formlu Dəstək Bilet Paneli Mesajını göndərir.")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📩 QAFQAZ GAMING COMMUNITY - Dəstək Mərkəzi",
            description="Probleminizi həll etmək, texniki dəstək almaq və ya şikayət bildirmək üçün aşağıdakı menyudan **Müraciət Kateqoriyasını** seçin və form doldurun!\n\n"
                        "💬 **Ümumi Dəstək** — Ümumi sual və kömək müraciəti\n"
                        "🛠️ **Texniki Dəstək** — Bot və ya server texniki problemləri\n"
                        "⚖️ **Admin Şikayəti** — Şikayət və ədalətsizlik bildirişi\n"
                        "💎 **VİP & Sponsorluq** — Əməkdaşlıq müraciəti",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=LOGO_URL)
        embed.set_image(url=BANNER_URL)
        embed.set_footer(text="Qafqaz Community Interactive Ticket System • 7/24 Dəstək")

        view = TicketSetupView()
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))
