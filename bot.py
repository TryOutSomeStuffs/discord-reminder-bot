import discord
from discord.ext import commands, tasks
import asyncio
import os
import time
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

active_reminders = {}
panel_message = None
panel_end_time = None


# -----------------------------
# Format remaining time
# -----------------------------
def format_duration(seconds):

    days = seconds // 86400
    seconds %= 86400

    hours = seconds // 3600
    seconds %= 3600

    minutes = seconds // 60

    parts = []

    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")

    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")

    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return " ".join(parts) if parts else "Less than a minute"


# -----------------------------
# Update panel message
# -----------------------------
async def update_panel():

    global panel_message

    if panel_message is None:
        return

    if panel_end_time:

        remaining = panel_end_time - int(time.time())

        if remaining < 0:
            remaining = 0

        remaining_text = format_duration(remaining)

        status = (
            f"{remaining_text}\n\n"
            f"Ends:\n<t:{panel_end_time}:F>"
        )

    else:
        status = "None"

    view = ReminderPanel()

    await panel_message.edit(
        content=(
            "━━━━━━━━━━━━━━\n"
            "🌳 **Guild Tree Reminder**\n"
            "━━━━━━━━━━━━━━\n\n"
            f"Active Reminder:\n{status}"
        ),
        view=view
    )


# -----------------------------
# Live panel refresh (1 min)
# -----------------------------
@tasks.loop(minutes=1)
async def refresh_panel():

    if panel_end_time:
        await update_panel()


# -----------------------------
# Custom modal
# -----------------------------
class CustomTimeModal(discord.ui.Modal, title="Custom Reminder Time"):

    hours = discord.ui.TextInput(
        label="Hours",
        placeholder="Enter hours",
        required=False
    )

    minutes = discord.ui.TextInput(
        label="Minutes",
        placeholder="Enter minutes",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):

        h = int(self.hours.value or 0)
        m = int(self.minutes.value or 0)

        duration = h * 3600 + m * 60

        if duration <= 0:
            await interaction.response.send_message(
                "Please enter a valid duration.",
                ephemeral=True
            )
            return

        await start_reminder(interaction, duration)


# -----------------------------
# Start reminder logic
# -----------------------------
async def start_reminder(interaction, duration):

    global panel_end_time

    user = interaction.user

    if user.id in active_reminders:

        end_time = active_reminders[user.id]["end"]

        remaining = end_time - int(time.time())

        await interaction.response.send_message(
            f"⏰ Reminder already running.\n\nRemaining:\n{format_duration(remaining)}",
            ephemeral=True
        )

        return

    end_time = int(time.time()) + duration

    async def reminder_task():

        global panel_end_time

        try:

            await asyncio.sleep(duration)

            await user.send("Time to contribute for the guild tree.")

            del active_reminders[user.id]

            panel_end_time = None

            await update_panel()

        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(reminder_task())

    active_reminders[user.id] = {
        "task": task,
        "end": end_time
    }

    panel_end_time = end_time

    await update_panel()

    await interaction.response.send_message(
        f"⏰ Reminder started.\n\nRemaining:\n{format_duration(duration)}",
        ephemeral=True
    )


# -----------------------------
# Panel buttons
# -----------------------------
class ReminderPanel(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        if panel_end_time is None:
            self.children[2].disabled = True

    @discord.ui.button(
        label="24h Reminder",
        style=discord.ButtonStyle.green
    )
    async def reminder_24h(self, interaction: discord.Interaction, button):

        await start_reminder(interaction, 86400)

    @discord.ui.button(
        label="Custom Time",
        style=discord.ButtonStyle.blurple
    )
    async def custom(self, interaction: discord.Interaction, button):

        await interaction.response.send_modal(CustomTimeModal())

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.red
    )
    async def cancel(self, interaction: discord.Interaction, button):

        user = interaction.user

        if user.id not in active_reminders:

            await interaction.response.send_message(
                "No active reminder.",
                ephemeral=True
            )

            return

        active_reminders[user.id]["task"].cancel()

        del active_reminders[user.id]

        global panel_end_time
        panel_end_time = None

        await update_panel()

        await interaction.response.send_message(
            "❌ Reminder cancelled.",
            ephemeral=True
        )


# -----------------------------
# Bot startup
# -----------------------------
@bot.event
async def on_ready():

    global panel_message

    print(f"Logged in as {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)

    panel_message = await channel.send(
        "━━━━━━━━━━━━━━\n"
        "🌳 **Guild Tree Reminder**\n"
        "━━━━━━━━━━━━━━\n\n"
        "Active Reminder:\nNone",
        view=ReminderPanel()
    )

    refresh_panel.start()


bot.run(TOKEN)
