import asyncio
import discord
from discord.ext import commands
from discord import app_commands

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
