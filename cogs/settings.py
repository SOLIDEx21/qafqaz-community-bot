import datetime
import discord
from discord.ext import commands
from discord import app_commands
import database as db

# ==========================================
# MASTER CONTROL PANEL (ÜMUMİ İDARƏETMƏ PANENLİ)
# ==========================================

class MasterCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Log Sistemi Tənzimləmələri", value="logs", description="Server log kanallarını ayarlayın", emoji="📜"),
            discord.SelectOption(label="XP və Level Sistemi", value="level", description="Səviyyə bildiriş kanalı və səviyyə rolları", emoji="🏆"),
            discord.SelectOption(label="Çəkiliş Sistemi Statusu", value="giveaway", description="Aktiv çəkilişlər və məlumatlar", emoji="🎉"),
            discord.SelectOption(label="Server və Bot Haqqında", value="info", description="Bot statusu, server statistikası və kömək", emoji="ℹ️")
        ]
        super().__init__(placeholder="🛠️ Tənzimləmək istədiyiniz Bölməni Seçin...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.current_category = self.values[0]
        embed = self.view.get_embed_for_category(interaction.guild, self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)

class LevelChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="🏆 Səviyyə Atlama Kanalını Seçin...", channel_types=[discord.ChannelType.text], row=1)

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        db.set_guild_level_channel(interaction.guild_id, channel.id)
        embed = self.view.get_embed_for_category(interaction.guild, "level")
        await interaction.response.edit_message(embed=embed, view=self.view)
        await interaction.followup.send(f"✅ Səviyyə atlama bildirişləri {channel.mention} kanalına bağlandı!", ephemeral=True)

class LogTypeSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="mesaj-log", description="Mesaj silinmələri/redaktələri", emoji="💬"),
            discord.SelectOption(label="giriş-çıkış-log", description="Serverə giriş və çıxışlar", emoji="📥"),
            discord.SelectOption(label="rol-log", description="Rol dəyişiklikləri", emoji="🎭"),
            discord.SelectOption(label="isim-log", description="Nikneym dəyişiklikləri", emoji="🏷️"),
            discord.SelectOption(label="ses-log", description="Səs kanalı aktivliyi", emoji="🔊"),
            discord.SelectOption(label="kanal-log", description="Kanal yaradılması/silinməsi", emoji="#️⃣"),
            discord.SelectOption(label="ban-log", description="Ban və unban logları", emoji="⛔"),
            discord.SelectOption(label="mod-log", description="Moderasiya logları", emoji="🛠️")
        ]
        super().__init__(placeholder="📜 Log növünü seçin...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_log_type = self.values[0]
        await interaction.response.send_message(
            f"📌 **Seçilmiş Log Növü:** `{self.values[0]}`\nİndi aşağıdakı menyudan kanalı seçin və ya **🔴 Deaktiv Et** düyməsinə basıb ləğv edin.",
            ephemeral=True
        )

class LogChannelSelectMenu(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📢 Seçilmiş Log üçün kanalı təyin edin...", channel_types=[discord.ChannelType.text], row=2)

    async def callback(self, interaction: discord.Interaction):
        selected_log = getattr(self.view, 'selected_log_type', 'mesaj-log')
        channel = self.values[0]
        db.set_log_channel(interaction.guild_id, selected_log, channel.id)
        embed = self.view.get_embed_for_category(interaction.guild, "logs")
        await interaction.response.edit_message(embed=embed, view=self.view)
        await interaction.followup.send(f"✅ **{selected_log}** üçün {channel.mention} kanalı təyin olundu!", ephemeral=True)

class MasterSettingsView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.current_category = "logs"
        self.selected_log_type = "mesaj-log"

        self.add_item(MasterCategorySelect())
        self.add_item(LogTypeSelectMenu())
        self.add_item(LogChannelSelectMenu())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Bu menyudan yalnız paneli açan Administrator istifadə edə bilər!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔴 Logu Deaktiv Et", style=discord.ButtonStyle.danger, row=3)
    async def disable_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        log_type = getattr(self, 'selected_log_type', 'mesaj-log')
        db.remove_log_channel(interaction.guild_id, log_type)
        embed = self.get_embed_for_category(interaction.guild, "logs")
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"🔴 **{log_type}** ləğv edildi.", ephemeral=True)

    @discord.ui.button(label="🔄 Paneli Yenilə", style=discord.ButtonStyle.secondary, row=3)
    async def refresh_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.get_embed_for_category(interaction.guild, self.current_category)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send("🔄 Panel yeniləndi!", ephemeral=True)

    def get_embed_for_category(self, guild: discord.Guild, category: str) -> discord.Embed:
        now_str = datetime.datetime.now().strftime("%d.%m.%Y – %H:%M:%S")

        if category == "logs":
            log_channels = db.get_log_channels(guild.id)
            def status(lt):
                cid = log_channels.get(lt)
                if cid and guild.get_channel(cid):
                    return f"🟢 {guild.get_channel(cid).mention}"
                return "🔘 `Deaktif`"

            embed = discord.Embed(
                title="📜 QAFQAZ GAMING COMMUNITY - Log Tənzimləmələri",
                color=discord.Color.blue()
            )
            embed.add_field(name="💬 Mesaj Log:", value=status("mesaj-log"), inline=True)
            embed.add_field(name="📥 Giriş-Çıxış Log:", value=status("giriş-çıkış-log"), inline=True)
            embed.add_field(name="🎭 Rol Log:", value=status("rol-log"), inline=True)
            embed.add_field(name="🏷️ İsim Log:", value=status("isim-log"), inline=True)
            embed.add_field(name="🔊 Ses Log:", value=status("ses-log"), inline=True)
            embed.add_field(name="#️⃣ Kanal Log:", value=status("kanal-log"), inline=True)
            embed.add_field(name="⛔ Ban Log:", value=status("ban-log"), inline=True)
            embed.add_field(name="🛠️ Mod Log:", value=status("mod-log"), inline=True)
            embed.set_footer(text=f"Aşağıdakı menyulardan 1 kliklə kanalları dəyişin | {now_str}")
            return embed

        elif category == "level":
            saved_ch_id = db.get_guild_level_channel_id(guild.id)
            level_ch = guild.get_channel(saved_ch_id) if saved_ch_id else None
            ch_str = level_ch.mention if level_ch else "🔘 `Təyin edilməyib (Avtomatik kanal)`"

            roles_data = db.get_level_roles(guild.id)
            roles_str = "\n".join([f"🏆 **Level {lvl}** $\rightarrow$ <@&{rid}>" for lvl, rid in roles_data]) if roles_data else "📜 `Hələ rol təyin edilməyib`"

            embed = discord.Embed(
                title="🏆 QAFQAZ GAMING COMMUNITY - Level & XP Tənzimləmələri",
                color=discord.Color.gold()
            )
            embed.add_field(name="📢 Səviyyə Atlama Bildiriş Kanali:", value=ch_str, inline=False)
            embed.add_field(name="🎖️ Avtomatik Səviyyə Rol Mükafatları:", value=roles_str, inline=False)
            embed.set_footer(text="Aşağıdakı menyudan Səviyyə Kanalını seçə bilərsiniz.")
            return embed

        elif category == "giveaway":
            active = db.get_active_giveaways()
            count = len(active)
            embed = discord.Embed(
                title="🎉 QAFQAZ GAMING COMMUNITY - Çəkiliş Sistemi",
                color=discord.Color.purple()
            )
            embed.add_field(name="🔥 Aktiv Çəkiliş Sayı:", value=f"`{count}` ədəd", inline=False)
            embed.add_field(name="💡 Çəkiliş Başlatmaq üçün:", value="`/giveaway start <vaxt> <qalib_sayı> <mükafat>`", inline=False)
            return embed

        else:
            embed = discord.Embed(
                title="🇦🇿 Qafqaz Gaming Community Bot",
                description="Server üçün xüsusi hazırlanmış 7/24 Aktiv XP, Level, Rol, Çəkiliş və Moderasiya Log Botu.",
                color=discord.Color.green()
            )
            embed.add_field(name="🟢 Bot Statusu:", value="`Online 7/24 (Render Cloud PostgreSQL)`", inline=True)
            embed.add_field(name="📊 Server İştirakçısı:", value=f"`{guild.member_count}` nəfər", inline=True)
            return embed

class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ayarlar", aliases=["menu", "panel", "settings"], description="[Admin] Qafqaz Community Ümumi İdarəetmə və Tənzimləmə Menyusu")
    @commands.has_permissions(administrator=True)
    async def master_settings(self, ctx: commands.Context):
        view = MasterSettingsView(author_id=ctx.author.id)
        embed = view.get_embed_for_category(ctx.guild, "logs")
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))
