# Scholar-Tracker Architecture

## Overview

Scholar-Tracker is a Python FastAPI service that monitors Google Scholar citations and sends WhatsApp notifications when new citations are detected. It connects to WhatsApp via a Node.js bridge (Baileys) using the WhatsApp Web protocol.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  ┌──────────────┐     ┌────────────────────────────────────────────┐   │
│  │  Your Phone  │◄───►│  WhatsApp Web Bridge (bridge/index.js)    │   │
│  │  (WhatsApp)  │     │  - Baileys (QR code scan, no Meta API)    │   │
│  └──────────────┘     │  - Forwards messages via HTTP POST        │   │
│                       │  - Text menu rendering (numbered options) │   │
│                       │  - Sender whitelist, group chat filter     │   │
│                       └──────────────┬─────────────────────────────┘   │
│                                      │ POST /ui-api/chat               │
│  ┌───────────────────────────────────▼─────────────────────────────┐   │
│  │                     FastAPI Server (main.py, port 8000)          │   │
│  │                                                                  │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │   │
│  │  │  /webhook     │  │  /ui-api/*   │  │  / (health check)    │  │   │
│  │  │  webhook.py   │  │  chat.py     │  │  DB + scheduler info │  │   │
│  │  │  (Meta API)   │  │  (bridge +   │  └───────────────────────┘  │   │
│  │  └──────┬───────┘  │   UI sim)    │                              │   │
│  │         │          └──────┬───────┘                              │   │
│  │         │                 │                                      │   │
│  │         ▼                 ▼                                      │   │
│  │  ┌────────────────────────────────────┐                          │   │
│  │  │       Intent Handler                │                         │   │
│  │  │  menu     → interactive button list │                         │   │
│  │  │  stats    → per-paper citations     │                         │   │
│  │  │  help     → command reference       │                         │   │
│  │  │  get_stats → alias for stats        │                         │   │
│  │  └──────────┬─────────────────────────┘                          │   │
│  │             │                                                    │   │
│  │  ┌──────────▼──────────┐  ┌──────────────────────────────────┐  │   │
│  │  │  database.py (SQLite) │  │  notifier.py (WhatsApp Cloud)   │  │   │
│  │  │  data/citations.db   │  │  Meta Graph API v18.0            │  │   │
│  │  │                      │  │  (only for webhook mode)         │  │   │
│  │  └──────────▲──────────┘  └──────────────────────────────────┘  │   │
│  │             │                                                    │   │
│  │  ┌──────────┴──────────┐  ┌──────────────────────────────────┐  │   │
│  │  │  scheduler.py        │  │  ORCID / OpenAlex lookup         │  │   │
│  │  │  APScheduler         │  │  ui_api.py /lookup-orcid         │  │   │
│  │  │  → scraper.py        │  │  Seeds papers into DB            │  │   │
│  │  │    (scholarly lib)   │  │  Free, no API key needed         │  │   │
│  │  └─────────────────────┘  └──────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Map

| Module | Purpose | Key Exports |
|---|---|---|
| `main.py` | App entry, lifespan, route mounting, health check | `app`, `lifespan()` |
| `config.py` | Pydantic settings from `.env` | `Settings`, `settings` |
| `models/database.py` | SQLite CRUD for papers and citation history | `init_db()`, `update_paper_citations()`, `get_tracked_papers()` |
| `models/schemas.py` | Pydantic request/response models | `ChatRequest`, `ChatResponse`, `TextResponse`, `ImageResponse` |
| `routes/webhook.py` | WhatsApp Cloud API webhook (verify + receive) | `verify_webhook()`, `receive_message()`, `handle_intent()` |
| `routes/chat.py` | Bridge chat endpoint, ORCID lookup, meme command | `/ui-api/chat`, `/ui-api/lookup-orcid` |
| `services/notifier.py` | Outbound WhatsApp messages (text, interactive, template) | `WhatsAppNotifier`, `notifier` |
| `services/scraper.py` | Google Scholar scraping with rate limiting | `ScholarScraper`, `scraper_client` |
| `services/scheduler.py` | APScheduler periodic citation checks with retry | `check_citations()`, `scheduler` |
| `utils/logger.py` | Centralized logging with 7-day rotation | `setup_logger()`, `logger` |
| `bridge/index.js` | WhatsApp Web bridge via Baileys | QR scan, message forwarding, image sending |

## Database Schema

### `papers` table
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| title | TEXT UNIQUE | Paper title (unique identifier) |
| current_citations | INTEGER | Latest known citation count |
| last_checked | DATETIME | Last scrape timestamp (UTC) |

### `citation_history` table
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| paper_id | INTEGER FK | References papers.id |
| citation_count | INTEGER | Snapshot of total citations |
| delta | INTEGER | Change from previous check |
| recorded_at | DATETIME | When recorded (UTC) |

## Data Flows

### WhatsApp Message via Bridge (primary)
1. User sends message on WhatsApp
2. Baileys bridge receives via WebSocket (WhatsApp Web protocol)
3. Bridge resolves numbered replies (`1` → `get_stats`, `2` → `help`)
4. Bridge POSTs `{type: "text", text: {body: "..."}}` to `/ui-api/chat`
5. `routes/chat.py` routes intent → returns response payload
6. Bridge formats interactive menus as numbered text lists
7. Bridge sends reply back via Baileys `sock.sendMessage()`

### WhatsApp Message via Meta Webhook (alternative)
1. Meta sends POST to `/webhook` with message payload
2. HMAC signature verified via `verify_signature()`
3. Sender checked against whitelist
4. `handle_intent()` routes to handler, calls notifier for response

### Scheduled Citation Check
1. APScheduler fires `check_citations()` every `CHECK_INTERVAL_HOURS`
2. Each tracked paper re-scraped via `scholarly` with rate limiting
3. If citations increased → DB updated, history recorded
4. Notification sent to whitelisted numbers (webhook mode only)

### ORCID Paper Loading
1. User calls `/ui-api/lookup-orcid?orcid_id=...`
2. OpenAlex API queried for author + works (free, no key)
3. Papers seeded into SQLite via `update_paper_citations()`
4. Citation counts available immediately via `stats` command

## Two Connection Modes

| | QR Code Bridge | Meta Webhook |
|---|---|---|
| **Protocol** | WhatsApp Web (Baileys) | WhatsApp Business Cloud API |
| **Auth** | QR code scan | Meta App + token + webhook |
| **Interactive buttons** | Text-based numbered menu | Native tap-to-reply buttons |
| **Notifications** | Via bridge only when running | Server push anytime |
| **Best for** | Personal use, testing | Production deployment |
