# Telegram Bot Examples

Practical Telegram bot examples in Python for e-commerce and web development workflows.

## Bots

| File | Description |
|------|-------------|
| [`price_checker_bot.py`](price_checker_bot.py) | Monitors product prices and sends alerts when price drops |
| [`order_notification_bot.py`](order_notification_bot.py) | Sends order status updates (OpenCart-compatible) |

## Setup

```bash
pip install python-telegram-bot requests beautifulsoup4 pymysql python-dotenv
```

Copy `.env.example` to `.env` and fill in your credentials:

```
TELEGRAM_TOKEN=your_bot_token_here
CHAT_ID=your_chat_id
DB_HOST=localhost
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=your_db_name
```

Get a token from [@BotFather](https://t.me/BotFather) and your chat ID from [@userinfobot](https://t.me/userinfobot).

## price_checker_bot.py

Polls a product page at a configurable interval, parses the price, and sends a Telegram alert when the price changes or drops below a threshold.

**Commands:**
```
/start          — register for notifications
/check          — check current price now
/track <url> <max_price>  — start tracking a URL
/stop           — stop all tracking
```

**How it works:**
1. User sends `/track https://example.com/product 1500`
2. Bot checks the page every N minutes (configurable)
3. Sends a Telegram message if price ≤ 1500 or changes by more than 5%

## order_notification_bot.py

Reads new and updated orders from an OpenCart-compatible MySQL database and sends status notifications to a Telegram channel or group.

**Supported statuses:** Pending → Processing → Shipped → Delivered / Cancelled

**How it works:**
1. Bot polls `oc_order` table every minute for status changes
2. Sends a formatted message with order ID, customer name, total, and status
3. Tracks already-notified orders in a local JSON file to avoid duplicates

**Example notification:**
```
🛒 Order #1042 — Processing
Customer: Ivan Ivanov
Total: 3 400 ₽
Updated: 2024-01-15 14:32
```

## Requirements

- Python 3.9+
- `python-telegram-bot` >= 20.0
- `requests` >= 2.28
- `beautifulsoup4` >= 4.12 (price_checker_bot)
- `pymysql` >= 1.1 (order_notification_bot)

## Security Notes

- Never commit `.env` or any file with credentials
- The `.gitignore` in this repo excludes `.env`, `*.log`, and `__pycache__`
- Use read-only DB credentials for the notification bot when possible

## License

MIT
