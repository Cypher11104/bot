import discord
from discord.ext import commands
from discord import app_commands
import requests
import json
import sqlite3
import asyncio
from datetime import datetime, timedelta
import hashlib
import os
from typing import Optional

# Configuration
DISCORD_TOKEN = "MTM2NzkyODA5Njk0NjEzMTExNA.GrSWIT.6QemuWSHdjuTZxReOQEHXens46Elh1nfX1hP44"
KEYAUTH_APP_NAME = "StealthVGC"
KEYAUTH_OWNER_ID = "s0nPEBJeQv"
KEYAUTH_SECRET = "fd8cab21135f9a6efa6bd30343b1d5a4ad839f29eae92e09bd633f223f7729da"
KEYAUTH_VERSION = "1.0"

class KeyAuthAPI:
    def __init__(self):
        self.app_name = KEYAUTH_APP_NAME
        self.owner_id = KEYAUTH_OWNER_ID
        self.secret = KEYAUTH_SECRET
        self.version = KEYAUTH_VERSION
        self.session_id = None
        self.base_url = "https://codeguard.cc/api/1.2/"

    def reset_hwid_by_license(self, license_key: str):
        """
        Resets HWID for a user using their username (passed as license_key here).
        """
        url = f"https://codeguard.cc/api/seller/?sellerkey=ade9938bd74c7193bfc491c235b3552c&type=resetuser&user={license_key}"
        
        try:
            response = requests.get(url, timeout=10, verify=False)
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": f"Unexpected status code: {response.status_code}"}
        except Exception as e:
            print(f"HWID reset error: {e}")
            return {"success": False, "message": "Request failed"}

class DatabaseManager:
    def __init__(self):
        self.db_name = "keyauth_bot.db"
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS license_resets (
                license_hash TEXT PRIMARY KEY,
                last_reset TIMESTAMP,
                reset_count INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def hash_license(self, license_key: str):
        """Create a hash of the license key for privacy"""
        return hashlib.sha256(license_key.encode()).hexdigest()
    
    def get_license_reset_data(self, license_key: str):
        """Get license's reset data"""
        license_hash = self.hash_license(license_key)
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM license_resets WHERE license_hash = ?', (license_hash,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'license_hash': result[0],
                'last_reset': result[1],
                'reset_count': result[2]
            }
        return None
    
    def update_reset_time(self, license_key: str):
        """Update last reset time and increment counter for license"""
        license_hash = self.hash_license(license_key)
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO license_resets (license_hash, last_reset, reset_count)
            VALUES (?, ?, COALESCE((SELECT reset_count FROM license_resets WHERE license_hash = ?) + 1, 1))
        ''', (license_hash, datetime.now().isoformat(), license_hash))
        
        conn.commit()
        conn.close()

# Bot setup with minimal intents
intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize components
keyauth = KeyAuthAPI()
db = DatabaseManager()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="reset", description="reset your hardwareID")
@app_commands.describe(license="Your KeyAuth license key")
async def reset_hwid(interaction: discord.Interaction, license: str):
    
    # Defer response since this might take time
    await interaction.response.defer(ephemeral=True)
    
    # Check cooldown for this specific license
    license_data = db.get_license_reset_data(license)
    
    if license_data and license_data['last_reset']:
        last_reset = datetime.fromisoformat(license_data['last_reset'])
        time_diff = datetime.now() - last_reset
        cooldown_hours = 24
        
        if time_diff < timedelta(hours=cooldown_hours):
            remaining_time = timedelta(hours=cooldown_hours) - time_diff
            hours, remainder = divmod(remaining_time.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            
            embed = discord.Embed(
                title="⏰ License Cooldown Active",
                description=f"This license can be reset again in **{int(hours)}h {int(minutes)}m**",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="Last Reset",
                value=f"<t:{int(last_reset.timestamp())}:R>",
                inline=True
            )
            embed.add_field(
                name="Total Resets",
                value=license_data['reset_count'],
                inline=True
            )
            embed.add_field(
                name="Next Reset Available",
                value=f"<t:{int((last_reset + timedelta(hours=24)).timestamp())}:f>",
                inline=False
            )
            embed.add_field(
                name="Note",
                value="Each license has its own 24-hour cooldown timer",
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
    
    # Attempt HWID reset
    try:
        result = keyauth.reset_hwid_by_license(license)
        
        if result.get('success'):
            # Update database with this license's reset time
            db.update_reset_time(license)
            
            # Get updated data for display
            updated_data = db.get_license_reset_data(license)
            
            embed = discord.Embed(
                title="✅ HWID Reset Successful",
                description="Your HWID has been successfully reset!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Reset Time",
                value=f"<t:{int(datetime.now().timestamp())}:f>",
                inline=True
            )
            embed.add_field(
                name="Total Resets",
                value=updated_data['reset_count'] if updated_data else 1,
                inline=True
            )
            embed.add_field(
                name="Next Reset Available",
                value=f"<t:{int((datetime.now() + timedelta(hours=24)).timestamp())}:f>",
                inline=False
            )
            embed.add_field(
                name="License Status",
                value="✅ Valid and active",
                inline=True
            )
            embed.add_field(
                name="Note",
                value="You can now use your software with the new HWID",
                inline=False
            )
            
        else:
            embed = discord.Embed(
                title=f"{result.get('message', 'Unknown error')}",
                color=discord.Color.red()
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while processing your request. Please try again later.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"Error during HWID reset: {e}")

@bot.tree.command(name="status", description="Check the cooldown status for your license")
@app_commands.describe(license="license")
async def check_status(interaction: discord.Interaction, license: str):
    """Check license's reset status and cooldown"""
    license_data = db.get_license_reset_data(license)
    
    embed = discord.Embed(
        title="📊 License Reset Status",
        color=discord.Color.blue()
    )
    
    # Show partial license for identification (first 8 chars + ****)
    license_display = license[:8] + "****" if len(license) > 8 else license[:4] + "****"
    embed.add_field(
        name="License",
        value=f"`{license_display}`",
        inline=True
    )
    
    if not license_data or not license_data['last_reset']:
        embed.add_field(
            name="Reset Status",
            value="✅ **Available Now**",
            inline=True
        )
        embed.add_field(
            name="Total Resets",
            value="0",
            inline=True
        )
        embed.add_field(
            name="Usage",
            value="Use `/reset` with your license to reset HWID",
            inline=False
        )
        embed.color = discord.Color.green()
    else:
        last_reset = datetime.fromisoformat(license_data['last_reset'])
        time_diff = datetime.now() - last_reset
        
        embed.add_field(
            name="Total Resets",
            value=license_data['reset_count'],
            inline=True
        )
        
        if time_diff < timedelta(hours=24):
            remaining_time = timedelta(hours=24) - time_diff
            hours, remainder = divmod(remaining_time.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            
            embed.add_field(
                name="Reset Available In",
                value=f"**{int(hours)}h {int(minutes)}m**",
                inline=True
            )
            embed.color = discord.Color.orange()
            
            embed.add_field(
                name="Next Reset Available",
                value=f"<t:{int((last_reset + timedelta(hours=24)).timestamp())}:f>",
                inline=False
            )
        else:
            embed.add_field(
                name="Reset Status",
                value="✅ **Available Now**",
                inline=True
            )
            embed.color = discord.Color.green()
        
        embed.add_field(
            name="Last Reset",
            value=f"<t:{int(last_reset.timestamp())}:R>",
            inline=True
        )
    
    embed.add_field(
        name="How it works",
        value="Each license has its own 24-hour cooldown timer",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="Show help information for HWID reset commands")
async def help_command(interaction: discord.Interaction):
    """Show help information"""
    embed = discord.Embed(
        title="🔧 HardwareID Reset",
        description="Reset your HWID using your license key",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="/reset <license>",
        value="Reset your HWID using your license key\n• 24-hour cooldown per license\n• Each license tracked separately",
        inline=False
    )
    
    embed.add_field(
        name="/status <license>",
        value="Check cooldown status for a specific license\n• Shows remaining cooldown time\n• Displays total reset count",
        inline=False
    )
    
    embed.add_field(
        name="/help",
        value="Show this help message",
        inline=False
    )
    
    embed.add_field(
        name="🔒 Privacy & Security",
        value="• License keys are hashed and never stored in plain text\n• All interactions are private (only you can see them)\n• Each license has independent cooldown tracking",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Important Notes",
        value="• HWID resets have a 24-hour cooldown **per license**\n• Make sure your license is valid and active\n• Contact support if you encounter persistent issues",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Keep the old prefix commands for backwards compatibility
@bot.command(name='sync')
@commands.has_permissions(administrator=True)
async def sync(ctx):
    """Sync slash commands (Admin only)"""
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)")
    except Exception as e:
        await ctx.send(f"Failed to sync commands: {e}")

# Error handling for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏰ Command on Cooldown",
            description=f"Try again in {error.retry_after:.2f} seconds",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="❌ Error",
            description="An unexpected error occurred. Please try again later.",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        print(f"Slash command error: {error}")

# Error handling for regular commands
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Missing Arguments",
            description=f"Missing required argument: `{error.param.name}`\nUse `/help` for command usage",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ Missing Permissions",
            description="You don't have permission to use this command.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    else:
        embed = discord.Embed(
            title="❌ Error",
            description="An unexpected error occurred. Please try again later.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        print(f"Unexpected error: {error}")

if __name__ == "__main__":
    # Check if required environment variables are set
    if not all([DISCORD_TOKEN != "YOUR_DISCORD_BOT_TOKEN", 
                KEYAUTH_APP_NAME != "YOUR_KEYAUTH_APP_NAME",
                KEYAUTH_OWNER_ID != "YOUR_KEYAUTH_OWNER_ID",
                KEYAUTH_SECRET != "YOUR_KEYAUTH_SECRET"]):
        print("Please configure your tokens and credentials at the top of the file!")
        exit(1)
    
    bot.run(DISCORD_TOKEN)