import discord
from discord.ext import commands
import asyncio
import os
import time

from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

PANEL_MESSAGE_ID = 1479070193807528089  # put message ID here after first run
TEST_DURATION = 86400
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

active_reminders = {}


@discord.ui.button(label="Cancel Reminder", style=discord.ButtonStyle.red)
async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

    if interaction.user.id != self.user_id:
        await interaction.response.send_message(
            "This button isn't for you.", ephemeral=True
        )
        return

    task = active_reminders.get(self.user_id)

    if task:
        task.cancel()
        del active_reminders[self.user_id]

    button.disabled = True

    await interaction.response.edit_message(
        content="❌ Reminder cancelled.",
        view=self
    )
    
class ReminderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start 24h Reminder", style=discord.ButtonStyle.green, custom_id="start_reminder")
    async def start_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):

        user = interaction.user

        if user.id in active_reminders:
            await interaction.response.send_message(
                "⏰ You already have a reminder running.",
                ephemeral=True
            )
            return

        end_time = int(time.time()) + TEST_DURATION

        async def reminder_task():
            try:
                await asyncio.sleep(TEST_DURATION)

                await user.send("⏰ Reminder! 24 hours have passed.")

                del active_reminders[user.id]

            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(reminder_task())

        active_reminders[user.id] = task

        await interaction.response.send_message(
            f"⏰ Reminder started!\n\nReminder ends:\n<t:{end_time}:F>",
            view=CancelView(user.id),
            ephemeral=True
        )


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    bot.add_view(ReminderView())  # makes button persistent

    channel = bot.get_channel(CHANNEL_ID)

    if PANEL_MESSAGE_ID == 0:
        message = await channel.send(
            "━━━━━━━━━━━━━━\n"
            "⏰ **24 Hour Reminder**\n"
            "━━━━━━━━━━━━━━\n\n"
            "Press the button below to start a reminder.",
            view=ReminderView()
        )

        print("Panel message ID:", message.id)



bot.run(TOKEN)
