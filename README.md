# Scholar Citation Tracker

A lightweight Python service that tracks your Google Scholar citations and notifies you via **WhatsApp** when they change. Connects to WhatsApp by scanning a QR code — no Meta Business API setup needed.

## How It Works

```
┌──────────────┐     ┌────────────────────────┐     ┌──────────────────────┐
│  Your Phone  │◄───►│  WhatsApp Web Bridge   │◄───►│  FastAPI Backend      │
│  (WhatsApp)  │     │  bridge/index.js       │     │  python main.py      │
└──────────────┘     │  (Baileys, QR scan)    │     │                      │
                     └────────────────────────┘     │  ┌── db.py (SQLite)  │
                                                    │  ├── scraper.py      │
                                                    │  ├── scheduler.py    │
                                                    │  └── notifier.py     │
                                                    └──────────────────────┘
```

1. **Bridge** connects to WhatsApp via QR code scan (like linking a device)
2. **Backend** handles commands (`menu`, `stats`, `help`)
3. **Scheduler** checks Google Scholar periodically and notifies you of new citations
4. **ORCID lookup** seeds your publication list from OpenAlex (free, no API key)

## Features

- **QR Code WhatsApp** — scan once, stay connected (Baileys/WhatsApp Web protocol)
- **ORCID Integration** — load all your papers + citation counts via OpenAlex
- **Automated Tracking** — periodic Google Scholar scraping with rate limiting
- **Interactive Menus** — type `menu`, `stats`, `help` or reply with numbers
- **Sender Whitelist** — optionally restrict who can use the bot
- **Local UI Simulator** — test everything at `http://localhost:8000/ui/` without WhatsApp
- **Health Check** — `GET /` reports DB, scheduler, and config status
## Prerequisites

- **Python 3.11+** — `python --version`
- **Node.js 18+** — `node --version`

## Quick Start

```bash
git clone https://github.com/YOUR-USER/scholar-tracker.git
cd scholar-tracker

# Linux / macOS
chmod +x start.sh && ./start.sh

# Windows
start.bat
```

This installs dependencies, starts the backend and bridge, and shows a QR code on first run.
Scan it with **WhatsApp → Linked Devices → Link a Device**.

**Load your papers:**
```
http://localhost:8000/ui-api/lookup-orcid?orcid_id=YOUR-ORCID-HERE
```

**Test:** Send `menu` on WhatsApp.

### Manual Start (Windows / two terminals)

**Terminal 1 — Backend:**
```bash
cd scholar-tracker
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python main.py
```

**Terminal 2 — Bridge (separate terminal, no venv):**
```bash
cd scholar-tracker/bridge
npm install
node index.js
```

## WhatsApp Commands

| Command | What it does |
|---------|-------------|
| `menu`  | Shows interactive menu with numbered options |
| `stats` | Shows per-paper citation counts |
| `help`  | Lists available commands |
| `meme`  | Sends a random meme image |
| `meme help` | Lists 5 meme categories |
| `meme 1`-`5` | Meme from specific category (General, Programmer, Wholesome, Dank, Science) |
| `1`     | Same as `stats` (after seeing menu) |
| `2`     | Same as `meme` (after seeing menu) |
| `3`     | Same as `help` (after seeing menu) |

## Project Structure

```
scholar-tracker/
├── main.py                              # FastAPI app + scheduler startup
├── pyproject.toml                       # Build config + dependencies
├── .env.example                         # Environment variable template
│
├── src/scholar_tracker/
│   ├── config.py                        # Settings from .env (pydantic)
│   │
│   ├── models/                          # Data layer
│   │   ├── database.py                  # SQLite CRUD (papers, citations)
│   │   └── schemas.py                   # Pydantic request/response models
│   │
│   ├── services/                        # Business logic
│   │   ├── scraper.py                   # Google Scholar via scholarly
│   │   ├── notifier.py                  # Outbound WhatsApp messages
│   │   └── scheduler.py                 # APScheduler periodic checks
│   │
│   ├── routes/                          # API endpoints
│   │   ├── webhook.py                   # /webhook (Meta Business API)
│   │   └── chat.py                      # /ui-api/* (bridge + UI + ORCID)
│   │
│   └── utils/
│       └── logger.py                    # Logging with 7-day rotation
│
├── bridge/                              # WhatsApp Web bridge (Node.js)
│   ├── index.js                         # Baileys connector
│   ├── package.json                     # Node dependencies
│   └── auth_info/                       # Session (gitignored)
│
├── tests/
│   ├── conftest.py                      # Shared fixtures (fresh_db)
│   ├── test_db.py                       # Database layer tests
│   ├── test_ui_api.py                   # Chat endpoint tests
│   └── test_webhook.py                  # Webhook + intent tests
│
├── ui/index.html                        # Local simulator
└── docs/ARCHITECTURE.md                 # System design
```

## Configuration (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `WHATSAPP_TOKEN` | For webhook mode | Meta Cloud API token |
| `WHATSAPP_PHONE_NUMBER_ID` | For webhook mode | Meta phone number ID |
| `WHATSAPP_APP_SECRET` | For webhook mode | HMAC verification |
| `WHATSAPP_VERIFY_TOKEN` | For webhook mode | Webhook setup token |
| `ALLOWED_PHONE_NUMBERS` | No | Comma-separated whitelist (empty = allow all) |
| `SCHOLAR_AUTHOR_ID` | No | Google Scholar profile ID |
| `CHECK_INTERVAL_HOURS` | No | Scrape interval (default: 24) |
| `DB_PATH` | No | SQLite path (default: data/citations.db) |

> **Note:** The WhatsApp variables are only needed for the Meta Business API webhook mode. The QR code bridge (recommended) doesn't need them.

## Testing

```bash
pip install -e ".[dev]"
pytest -v tests/
```

## Two WhatsApp Connection Modes

| | QR Code Bridge (recommended) | Meta Webhook |
|---|---|---|
| **Setup** | `npm start` → scan QR | Meta App + ngrok + webhook verify |
| **Needs** | Node.js | Meta Developer account |
| **Interactive buttons** | Text-based numbered menu | Native WhatsApp buttons |
| **Best for** | Personal use, development | Production, business scale |
