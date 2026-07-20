"""
order_notification_bot.py

Reads new and updated orders from an OpenCart-compatible MySQL database
and sends status notifications to a Telegram channel or group.

Usage:
    cp .env.example .env  # fill in your credentials
    python order_notification_bot.py

The bot polls oc_order every CHECK_INTERVAL seconds and sends a message
for each order whose status has changed since the last check.
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime

import pymysql
import pymysql.cursors
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Config from environment ---
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))  # seconds

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
    "db": os.getenv("DB_NAME", ""),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

DB_PREFIX = os.getenv("DB_PREFIX", "oc_")
STATE_FILE = Path("notified_orders.json")

# Status emoji mapping
STATUS_EMOJI = {
    "Pending": "🕐",
    "Processing": "⚙️",
    "Shipped": "🚚",
    "Delivered": "✅",
    "Cancelled": "❌",
    "Refunded": "💸",
    "Failed": "⚠️",
    "Ожидает": "🕐",
    "Обрабатывается": "⚙️",
    "Отправлен": "🚚",
    "Доставлен": "✅",
    "Отменен": "❌",
}


# --- State management ---

def load_notified() -> dict:
    """Load the dict of already-notified order_id -> status_id."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_notified(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --- Database ---

def get_connection():
    return pymysql.connect(**DB_CONFIG)


def fetch_recent_orders(limit: int = 50) -> list[dict]:
    """Fetch the most recently modified orders."""
    prefix = DB_PREFIX
    sql = f"""
        SELECT
            o.order_id,
            o.firstname,
            o.lastname,
            o.email,
            o.telephone,
            o.total,
            o.currency_code,
            o.date_added,
            o.date_modified,
            os.name AS status_name,
            o.order_status_id
        FROM {prefix}order o
        LEFT JOIN {prefix}order_status os
            ON o.order_status_id = os.order_status_id
            AND os.language_id = 1
        WHERE o.order_status_id > 0
        ORDER BY o.date_modified DESC
        LIMIT %s
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            return cur.fetchall()
    finally:
        conn.close()


# --- Formatting ---

def format_order_message(order: dict) -> str:
    status = order.get("status_name") or "Unknown"
    emoji = STATUS_EMOJI.get(status, "📋")
    total = order.get("total", 0)
    currency = order.get("currency_code", "")
    date = order.get("date_modified", "")
    if isinstance(date, datetime):
        date = date.strftime("%Y-%m-%d %H:%M")

    name = f"{order.get('firstname', '')} {order.get('lastname', '')}".strip()

    return (
        f"{emoji} Order #{order['order_id']} — {status}\n"
        f"Customer: {name}\n"
        f"Total: {total} {currency}\n"
        f"Updated: {date}"
    )


# --- Main loop ---

async def run_bot() -> None:
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Set TELEGRAM_TOKEN and CHAT_ID environment variables")

    bot = Bot(token=TOKEN)
    notified = load_notified()

    logger.info("Order notification bot started. Checking every %d seconds.", CHECK_INTERVAL)

    while True:
        try:
            orders = fetch_recent_orders()
            changed = False

            for order in orders:
                oid = str(order["order_id"])
                current_status_id = order["order_status_id"]
                prev_status_id = notified.get(oid)

                if prev_status_id != current_status_id:
                    msg = format_order_message(order)
                    try:
                        await bot.send_message(chat_id=CHAT_ID, text=msg)
                        logger.info("Notified: order #%s → %s", oid, order.get("status_name"))
                    except TelegramError as e:
                        logger.error("Telegram error for order #%s: %s", oid, e)
                        continue

                    notified[oid] = current_status_id
                    changed = True

            if changed:
                save_notified(notified)

        except pymysql.Error as e:
            logger.error("Database error: %s", e)
        except Exception as e:
            logger.error("Unexpected error: %s", e)

        await asyncio.sleep(CHECK_INTERVAL)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
