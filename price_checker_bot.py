"""
price_checker_bot.py

Monitors product prices on web pages and sends Telegram alerts
when price drops below a threshold or changes significantly.

Usage:
    export TELEGRAM_TOKEN="your_token"
    python price_checker_bot.py

Commands:
    /start                  — register for notifications
    /track <url> <max>      — track URL, alert if price <= max
    /check                  — check all tracked prices now
    /list                   — show tracked items
    /stop                   — stop all tracking
"""

import os
import re
import json
import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, JobQueue
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL", "30"))
STATE_FILE = Path("tracked_prices.json")

# --- Data model ---

@dataclass
class TrackedItem:
    url: str
    max_price: float
    last_price: Optional[float] = None
    chat_id: Optional[int] = None
    name: str = ""


def load_state() -> dict[str, TrackedItem]:
    if STATE_FILE.exists():
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {k: TrackedItem(**v) for k, v in raw.items()}
    return {}


def save_state(items: dict[str, TrackedItem]) -> None:
    STATE_FILE.write_text(
        json.dumps({k: asdict(v) for k, v in items.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --- Price parsing ---

PRICE_PATTERN = re.compile(r"[\d\s]+[.,]\d{2}|[\d\s]{2,}")


def fetch_price(url: str) -> Optional[float]:
    """Fetch a product page and extract the first plausible price."""
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; PriceCheckerBot/1.0)"
        })
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Common price selectors (add your site-specific ones here)
    selectors = [
        "[itemprop='price']",
        ".price", ".product-price", ".offer-price",
        "#price", ".js-price",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            digits = re.sub(r"[^\d.]", "", text.replace(",", "."))
            try:
                return float(digits)
            except ValueError:
                continue

    return None


# --- Bot handlers ---

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Price Checker Bot\n\n"
        "/track <url> <max_price> — start tracking\n"
        "/check — check prices now\n"
        "/list — show tracked items\n"
        "/stop — remove all tracking"
    )


async def cmd_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /track <url> <max_price>")
        return

    url, max_price_str = args[0], args[1]
    try:
        max_price = float(max_price_str.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Invalid price. Use a number like 1500 or 1500.00")
        return

    items = ctx.bot_data.setdefault("items", load_state())
    item = TrackedItem(url=url, max_price=max_price, chat_id=update.effective_chat.id)
    items[url] = item
    save_state(items)

    current = fetch_price(url)
    msg = f"Tracking: {url}\nAlert when price ≤ {max_price}"
    if current is not None:
        item.last_price = current
        msg += f"\nCurrent price: {current}"
    await update.message.reply_text(msg)


async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    items: dict[str, TrackedItem] = ctx.bot_data.get("items", {})
    if not items:
        await update.message.reply_text("No items tracked. Use /track <url> <max_price>")
        return

    for url, item in list(items.items()):
        price = fetch_price(url)
        if price is None:
            await update.message.reply_text(f"Could not fetch price for:\n{url}")
            continue

        change = ""
        if item.last_price and abs(price - item.last_price) / item.last_price > 0.01:
            direction = "▼" if price < item.last_price else "▲"
            change = f" ({direction} was {item.last_price})"

        item.last_price = price
        msg = f"Price: {price}{change}\n{url}"
        if price <= item.max_price:
            msg = f"🔔 PRICE ALERT!\n{msg}\nTarget: ≤ {item.max_price}"
        await update.message.reply_text(msg)

    save_state(items)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    items: dict[str, TrackedItem] = ctx.bot_data.get("items", {})
    if not items:
        await update.message.reply_text("No items tracked.")
        return

    lines = []
    for url, item in items.items():
        price_str = str(item.last_price) if item.last_price else "unknown"
        lines.append(f"• {url}\n  Current: {price_str} | Alert at: ≤ {item.max_price}")
    await update.message.reply_text("\n\n".join(lines))


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.bot_data["items"] = {}
    save_state({})
    await update.message.reply_text("All tracking stopped.")


async def job_check_prices(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job: check prices and notify if threshold crossed."""
    items: dict[str, TrackedItem] = ctx.bot_data.get("items", load_state())
    for url, item in list(items.items()):
        price = fetch_price(url)
        if price is None:
            continue
        if price <= item.max_price and item.chat_id:
            await ctx.bot.send_message(
                chat_id=item.chat_id,
                text=f"🔔 Price alert!\nPrice dropped to {price} (target ≤ {item.max_price})\n{url}",
            )
        item.last_price = price
    save_state(items)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Set TELEGRAM_TOKEN environment variable")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("track", cmd_track))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("stop", cmd_stop))

    app.job_queue.run_repeating(
        job_check_prices,
        interval=CHECK_INTERVAL_MINUTES * 60,
        first=60,
    )

    logger.info("Bot started. Checking prices every %d minutes.", CHECK_INTERVAL_MINUTES)
    app.run_polling()


if __name__ == "__main__":
    main()
