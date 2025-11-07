# SPL Shield Telegram Bot

Minimal aiogram v3 skeleton for the SPL Shield Telegram bot.

## Requirements

- Python 3.11+
- Poetry or pip for dependency management

Install dependencies with:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

1. Copy `.env.example` to `.env`.
2. Fill in the required variables:
   - `BOT_TOKEN`: Bot token provided by BotFather.
   - `TARGET_CHAT_ID`: Numeric chat identifier for `https://t.me/splshield`.
   - `DATABASE_URL` (optional): Defaults to `sqlite:///./affiliate.db`.

## Running

```bash
python -m app.main
```

The bot will start long polling and respond `pong` to the `/ping` command.

### Docker

Build and run everything (bot + persistent SQLite volume) with:

```bash
docker compose up --build
```

The bundled `docker-compose.yml` also contains a commented Postgres service you can enable if you migrate away from SQLite.

### Affiliate Commands

- `/mylink` (DM): Create or retrieve your personal invite link.
- `/deactivate` (DM): Disable your affiliate link without deleting history.
- `/reactivate` (DM): Re-enable a previously deactivated link.
- `/mystats` (DM): View your verified, pending, and revoked referrals.
- `/top [7d|30d] [limit]`: Show top affiliates by verified referrals (optional window/limit).
- `/who_invited <user>` (admin): Resolve which affiliate captured a specific user.
- Admin only: `/affiliates`, `/pause_links`, `/resume_links`, `/rebuild_counts`, `/review_pending`.

### Webhook Mode

Set the following variables in `.env`:

- `WEBHOOK_URL`: Public HTTPS endpoint that Telegram should call.
- `WEBHOOK_SECRET_TOKEN`: Shared secret to validate Telegram requests.
- `HOST` / `PORT`: Interface for the webhook server (defaults work for Docker).

Apply the webhook with:

```bash
make webhook_set
```

Remove it with:

```bash
make webhook_delete
```

When `WEBHOOK_URL` is populated the bot automatically serves `/webhook` and a JSON health check on `/healthz`.

## Database

- `app/models.py` contains the SQLAlchemy declarative base for defining models.
- `app/migrations.sql` is a placeholder for SQL migration statements or tooling exports.

## Project Layout

```
app/
  config.py
  db.py
  main.py
  models.py
  migrations.sql
  handlers/
  services/
  utils/
```
