import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
from dotenv import load_dotenv

import sqlite3
import os
import time
import re
import random

from datetime import datetime, timedelta, timezone
from threading import Thread
from flask import Flask

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

conn = sqlite3.connect(
    "reminders.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (

    user_id INTEGER PRIMARY KEY,

    primary_time TEXT NOT NULL,
    secondary_time TEXT,

    utc_offset_minutes INTEGER NOT NULL,

    enabled INTEGER DEFAULT 1,

    reminder_count INTEGER DEFAULT 0,
    next_bonus_at INTEGER DEFAULT 8,

    last_primary_sent TEXT,
    last_secondary_sent TEXT,

    created_at INTEGER,
    updated_at INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS snoozes (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id INTEGER NOT NULL,
    reminder_time INTEGER NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS panel (
    message_id INTEGER
)
""")

conn.commit()

panel_message = None

def parse_utc_offset(offset_text):

    pattern = r"^UTC([+-])(\d{2}):(\d{2})$"

    match = re.match(pattern, offset_text)

    if not match:
        return None

    sign = match.group(1)
    hours = int(match.group(2))
    minutes = int(match.group(3))

    total = hours * 60 + minutes

    if sign == "-":
        total *= -1

    return total

def format_offset(minutes):

    sign = "+"

    if minutes < 0:
        sign = "-"
        minutes = abs(minutes)

    h = minutes // 60
    m = minutes % 60

    return f"UTC{sign}{h:02}:{m:02}"

def get_next_reminder(
    primary_time,
    secondary_time,
    utc_offset_minutes
):

    now_utc = datetime.utcnow()

    local_now = (
        now_utc +
        timedelta(minutes=utc_offset_minutes)
    )

    candidates = []

    for t in [primary_time, secondary_time]:

        if not t:
            continue

        hour, minute = map(
            int,
            t.split(":")
        )

        candidate = local_now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0
        )

        if candidate <= local_now:
            candidate += timedelta(days=1)

        candidates.append(candidate)

    if not candidates:
        return "No reminders"

    next_time = min(candidates)

    if next_time.date() == local_now.date():
        prefix = "Today"
    else:
        prefix = "Tomorrow"

    return (
        f"{prefix} "
        f"{next_time.strftime('%H:%M')}"
    )

async def send_reminder(user):

    try:

        await user.send(
            "🌳 Time to contribute for the guild tree.",
            view=SnoozeView()
        )

    except Exception as e:
        print(
            f"DM failed for {user.id}: {e}"
        )

class SnoozeView(View):

    def __init__(self):
        super().__init__(timeout=None)

    async def create_snooze(
        self,
        interaction,
        minutes
    ):

        remind_at = (
            int(time.time())
            + minutes * 60
        )

        cursor.execute(
            """
            INSERT INTO snoozes
            (
                user_id,
                reminder_time
            )
            VALUES (?, ?)
            """,
            (
                interaction.user.id,
                remind_at
            )
        )

        conn.commit()

        await interaction.response.send_message(
            f"⏰ Snoozed for {minutes} minutes.",
            ephemeral=True
        )

    @discord.ui.button(
        label="Snooze 30m",
        style=discord.ButtonStyle.blurple
    )
    async def snooze30(
        self,
        interaction,
        button
    ):
        await self.create_snooze(
            interaction,
            30
        )

    @discord.ui.button(
        label="Snooze 1h",
        style=discord.ButtonStyle.green
    )
    async def snooze1h(
        self,
        interaction,
        button
    ):
        await self.create_snooze(
            interaction,
            60
        )

    @discord.ui.button(
        label="Snooze 5h",
        style=discord.ButtonStyle.red
    )
    async def snooze5h(
        self,
        interaction,
        button
    ):
        await self.create_snooze(
            interaction,
            300
        )

class ConfigureScheduleModal(
    Modal,
    title="Configure Schedule"
):

    primary_time = TextInput(
        label="Primary Time (HH:MM)",
        placeholder="18:00",
        required=True
    )

    secondary_time = TextInput(
        label="Secondary Time (Optional)",
        placeholder="22:00",
        required=False
    )

    utc_offset = TextInput(
        label="UTC Offset",
        placeholder="UTC+05:45",
        required=True
    )

    async def on_submit(
        self,
        interaction
    ):

        primary = (
            self.primary_time.value.strip()
        )

        secondary = (
            self.secondary_time.value.strip()
        )

        utc_text = (
            self.utc_offset.value.strip()
        )

        time_pattern = (
            r"^([01]\d|2[0-3]):([0-5]\d)$"
        )

        if not re.match(
            time_pattern,
            primary
        ):
            await interaction.response.send_message(
                "Invalid primary time.",
                ephemeral=True
            )
            return

        if (
            secondary
            and
            not re.match(
                time_pattern,
                secondary
            )
        ):
            await interaction.response.send_message(
                "Invalid secondary time.",
                ephemeral=True
            )
            return

        offset_minutes = parse_utc_offset(
            utc_text
        )

        if offset_minutes is None:

            await interaction.response.send_message(
                (
                    "Invalid UTC offset.\n\n"
                    "Example:\n"
                    "UTC+05:45\n"
                    "UTC-04:00"
                ),
                ephemeral=True
            )
            return

        now_ts = int(time.time())

        cursor.execute(
            """
            INSERT OR REPLACE INTO users
            (
                user_id,

                primary_time,
                secondary_time,

                utc_offset_minutes,

                enabled,

                reminder_count,
                next_bonus_at,

                created_at,
                updated_at
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                1,
                0,
                8,
                ?,
                ?
            )
            """,
            (
                interaction.user.id,

                primary,
                secondary,

                offset_minutes,

                now_ts,
                now_ts
            )
        )

        conn.commit()

        await interaction.response.send_message(
            (
                "✅ Schedule Saved\n\n"
                f"Primary: {primary}\n"
                f"Secondary: "
                f"{secondary if secondary else 'None'}\n"
                f"Offset: {utc_text}"
            ),
            ephemeral=True
        )

class ReminderPanel(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Configure Schedule",
        style=discord.ButtonStyle.green
    )
    async def configure(
        self,
        interaction,
        button
    ):

        await interaction.response.send_modal(
            ConfigureScheduleModal()
        )

    @discord.ui.button(
        label="View Schedule",
        style=discord.ButtonStyle.blurple
    )
    async def view_schedule(
        self,
        interaction,
        button
    ):
        
        cursor.execute(
            """
            SELECT
                primary_time,
                secondary_time,
                utc_offset_minutes,
                enabled
            FROM users
            WHERE user_id = ?
            """,
            (
                interaction.user.id,
            )
        )

        row = cursor.fetchone()

        if not row:

            await interaction.response.send_message(
                "No schedule configured.",
                ephemeral=True
            )
            return
        
        primary = row[0]
        secondary = row[1]
        offset = row[2]
        enabled = row[3]

        next_reminder = (
            get_next_reminder(
                primary,
                secondary,
                offset
            )
        )

        await interaction.response.send_message(
            (
                "🌳 Your Schedule\n\n"

                f"Primary:\n{primary}\n\n"

                f"Secondary:\n"
                f"{secondary if secondary else 'None'}\n\n"

                f"UTC Offset:\n"
                f"{format_offset(offset)}\n\n"

                f"Status:\n"
                f"{'Enabled' if enabled else 'Disabled'}\n\n"

                f"Next Reminder:\n"
                f"{next_reminder}"
            ),
            ephemeral=True
        )
    
    @discord.ui.button(
        label="Enable / Disable",
        style=discord.ButtonStyle.red
    )
    async def toggle(
        self,
        interaction,
        button
    ):
        
        cursor.execute(
            """
            SELECT enabled
            FROM users
            WHERE user_id = ?
            """,
            (
                interaction.user.id,
            )
        )

        row = cursor.fetchone()

        if not row:

            await interaction.response.send_message(
                "No schedule configured.",
                ephemeral=True
            )
            return

        new_value = 0 if row[0] else 1

        cursor.execute(
            """
            UPDATE users
            SET enabled = ?
            WHERE user_id = ?
            """,
            (
                new_value,
                interaction.user.id
            )
        )

        conn.commit()

        await interaction.response.send_message(
            (
                "✅ Schedule Enabled"
                if new_value
                else
                "⏸ Schedule Disabled"
            ),
            ephemeral=True
        )

@tasks.loop(seconds=30)
async def check_reminders():

    now_utc = datetime.utcnow()

    # -------------------------
    # DAILY REMINDERS
    # -------------------------

    cursor.execute("""
        SELECT
            user_id,
            primary_time,
            secondary_time,

            utc_offset_minutes,

            enabled,

            reminder_count,
            next_bonus_at,

            last_primary_sent,
            last_secondary_sent

        FROM users
    """)

    users = cursor.fetchall()

    for row in users:

        (
            user_id,

            primary_time,
            secondary_time,

            offset_minutes,

            enabled,

            reminder_count,
            next_bonus_at,

            last_primary_sent,
            last_secondary_sent

        ) = row

        if not enabled:
            continue

        local_now = (
            now_utc +
            timedelta(minutes=offset_minutes)
        )

        current_time = (
            local_now.strftime("%H:%M")
        )

        current_date = (
            local_now.strftime("%Y-%m-%d")
        )

        if current_time == primary_time:

            if last_primary_sent != current_date:

                await send_daily_reminder(
                    user_id,
                    reminder_count,
                    next_bonus_at
                )

                cursor.execute("""
                    UPDATE users
                    SET
                        last_primary_sent = ?,
                        reminder_count = reminder_count + 1
                    WHERE user_id = ?
                """,
                (
                    current_date,
                    user_id
                ))

                conn.commit()

        if secondary_time:

            if current_time == secondary_time:

                if last_secondary_sent != current_date:

                    await send_daily_reminder(
                        user_id,
                        reminder_count,
                        next_bonus_at
                    )

                    cursor.execute("""
                        UPDATE users
                        SET
                            last_secondary_sent = ?,
                            reminder_count = reminder_count + 1
                        WHERE user_id = ?
                    """,
                    (
                        current_date,
                        user_id
                    ))

                    conn.commit()

    now_timestamp = int(time.time())

    cursor.execute("""
        SELECT
            id,
            user_id,
            reminder_time
        FROM snoozes
    """)

    snoozes = cursor.fetchall()

    for snooze in snoozes:

        snooze_id = snooze[0]
        user_id = snooze[1]
        reminder_time = snooze[2]

        if now_timestamp >= reminder_time:

            try:

                user = await bot.fetch_user(
                    user_id
                )

                await send_reminder(user)

            except Exception as e:

                print(
                    f"Snooze error: {e}"
                )

            cursor.execute("""
                DELETE FROM snoozes
                WHERE id = ?
            """,
            (
                snooze_id,
            ))

            conn.commit()

async def send_daily_reminder(
    user_id,
    reminder_count,
    next_bonus_at
):
    try:

        user = await bot.fetch_user(
            user_id
        )

    except Exception as e:

        print(
            f"User fetch failed: {e}"
        )

        return

        await send_reminder(user)

async def update_panel():

    global panel_message

    if panel_message is None:
        return

    await panel_message.edit(
        content=
        (
            "━━━━━━━━━━━━━━\n"
            "🌳 Guild Tree Reminder\n"
            "━━━━━━━━━━━━━━\n\n"

            "Configure daily reminders.\n"
            "You will receive DMs automatically.\n\n"

            "• Primary Reminder\n"
            "• Optional Secondary Reminder\n"
            "• Snooze Support\n"
        ),
        view=ReminderPanel()
    )
@bot.event
async def on_ready():

    global panel_message

    print(
        f"Logged in as {bot.user}"
    )
    channel = bot.get_channel(
        CHANNEL_ID
    )

    if channel is None:

        print(
            "Channel not found."
        )

        return
    
    async for msg in channel.history(
        limit=50
    ):

        if (
            msg.author == bot.user
            and
            "Guild Tree Reminder"
            in msg.content
        ):

            try:
                await msg.delete()

            except:
                pass

    panel_message = await channel.send(

        "🌳 Guild Tree Reminder",

        view=ReminderPanel()
    )

    cursor.execute(
        "DELETE FROM panel"
    )

    cursor.execute(
        """
        INSERT INTO panel
        (
            message_id
        )
        VALUES (?)
        """,
        (
            panel_message.id,
        )
    )

    conn.commit()

    await update_panel()

    if not check_reminders.is_running():

        check_reminders.start()

    print(
        "Scheduler started."
    )

app = Flask(__name__)
@app.route("/")
def home():

    return (
        "Guild Tree Reminder "
        "Bot Online"
    )
def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
def keep_alive():

    thread = Thread(
        target=run_web
    )

    thread.start()
keep_alive()
bot.run(
    TOKEN,
    reconnect=True
)
