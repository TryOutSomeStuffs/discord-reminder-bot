import discord
from discord.ext import commands, tasks
import os
import time
import sqlite3
from dotenv import load_dotenv

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# DATABASE SETUP
# -----------------------------
conn = sqlite3.connect("reminders.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    user_id INTEGER PRIMARY KEY,
    end_time INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS panel (
    message_id INTEGER
)
""")

conn.commit()

panel_message = None


# -----------------------------
# FORMAT TIME
# -----------------------------
def format_duration(seconds):
    days = seconds // 86400
    seconds %= 86400

    hours = seconds // 3600
    seconds %= 3600

    minutes = seconds // 60

    parts = []

    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")

    return " ".join(parts) if parts else "<1m"


# -----------------------------
# UPDATE PANEL
# -----------------------------
async def update_panel():
    global panel_message

    if panel_message is None:
        return

    await panel_message.edit(
        content=(
            "━━━━━━━━━━━━━━\n"
            "🌳 **Guild Tree Reminder**\n"
            "━━━━━━━━━━━━━━\n\n"
            "Start a reminder.\n"
            "Your timer will be shown privately."
        ),
        view=ReminderPanel()
    )


# -----------------------------
# CHECK REMINDERS LOOP
# -----------------------------
@tasks.loop(seconds=30)
async def check_reminders():

    now = int(time.time())

    cursor.execute("SELECT user_id, end_time FROM reminders")
    rows = cursor.fetchall()

    for user_id, end_time in rows:

        if now >= end_time:

            try:
                user = await bot.fetch_user(user_id)
                await user.send("Time to contribute for the guild tree.")
            except:
                pass

            cursor.execute(
                "DELETE FROM reminders WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()


# -----------------------------
# START REMINDER
# -----------------------------
async def start_reminder(interaction, duration):

    user = interaction.user

    cursor.execute(
        "SELECT end_time FROM reminders WHERE user_id = ?",
        (user.id,)
    )
    row = cursor.fetchone()

    if row:
        remaining = row[0] - int(time.time())

        await interaction.response.send_message(
            f"⏰ Already running\n\nRemaining: {format_duration(remaining)}",
            ephemeral=True
        )
        return

    end_time = int(time.time()) + duration

    cursor.execute(
        "INSERT INTO reminders (user_id, end_time) VALUES (?, ?)",
        (user.id, end_time)
    )
    conn.commit()

    await interaction.response.send_message(
        f"⏰ Reminder started\n\nRemaining: {format_duration(duration)}",
        ephemeral=True
    )


# -----------------------------
# CUSTOM MODAL
# -----------------------------
class CustomTimeModal(discord.ui.Modal, title="Custom Reminder"):

    hours = discord.ui.TextInput(label="Hours", required=False)
    minutes = discord.ui.TextInput(label="Minutes", required=False)

    async def on_submit(self, interaction: discord.Interaction):

        h = int(self.hours.value or 0)
        m = int(self.minutes.value or 0)

        duration = h * 3600 + m * 60

        if duration <= 0:
            await interaction.response.send_message(
                "Invalid duration",
                ephemeral=True
            )
            return

        await start_reminder(interaction, duration)


# -----------------------------
# BUTTON PANEL
# -----------------------------
class ReminderPanel(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="24h Reminder", style=discord.ButtonStyle.green)
    async def r24(self, interaction: discord.Interaction, button):
        await start_reminder(interaction, 86400)

    @discord.ui.button(label="Custom Time", style=discord.ButtonStyle.blurple)
    async def custom(self, interaction: discord.Interaction, button):
        await interaction.response.send_modal(CustomTimeModal())

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button):

        cursor.execute(
            "SELECT * FROM reminders WHERE user_id = ?",
            (interaction.user.id,)
        )
        row = cursor.fetchone()

        if not row:
            await interaction.response.send_message(
                "No active reminder",
                ephemeral=True
            )
            return

        cursor.execute(
            "DELETE FROM reminders WHERE user_id = ?",
            (interaction.user.id,)
        )
        conn.commit()

        await interaction.response.send_message(
            "❌ Reminder cancelled",
            ephemeral=True
        )


# -----------------------------
# ON READY
# -----------------------------
@bot.event
async def on_ready():

    global panel_message

    print(f"Logged in as {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    # 🔥 CLEAN OLD PANELS
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and "Guild Tree Reminder" in msg.content:
            try:
                await msg.delete()
            except:
                pass

    # CREATE PANEL
    panel_message = await channel.send(
        "🌳 Guild Tree Reminder",
        view=ReminderPanel()
    )

    cursor.execute("DELETE FROM panel")
    cursor.execute(
        "INSERT INTO panel (message_id) VALUES (?)",
        (panel_message.id,)
    )
    conn.commit()

    check_reminders.start()
    await update_panel()


# -----------------------------
# KEEP ALIVE SERVER (IMPORTANT)
# -----------------------------
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

keep_alive()


# -----------------------------
# RUN BOT
# -----------------------------
bot.run(TOKEN)
