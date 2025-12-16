# XBot: AI-Powered Social Media Automation System

An automated content generation and publishing pipeline for X (Twitter) leveraging Google's Gemini large language models for text synthesis and image generation, with persistent campaign management via Supabase.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Database Schema](#database-schema)
- [Usage](#usage)
- [Campaign Management](#campaign-management)
- [Mentions Auto-Reply](#mentions-auto-reply)
- [CI/CD Pipeline](#cicd-pipeline)
- [API Reference](#api-reference)
- [Error Handling](#error-handling)
- [Limitations](#limitations)
- [License](#license)

## Overview

XBot implements an end-to-end automated social media content pipeline consisting of:

1. **Content Generation** — Utilizes Gemini 2.5 Flash for generating contextually relevant tweet text based on campaign-defined system prompts and topic lists.

2. **Image Synthesis** — Employs Gemini's image generation models to create visual content aligned with the generated tweet.

3. **Mentions Auto-Reply** — Monitors and responds to @mentions using AI-generated contextual replies.

4. **Multi-Platform Integration** — Interfaces with X API v2 for tweet publishing and v1.1 for media uploads.

5. **Persistent Storage** — Maintains campaign configurations, post history, mentions, and operational logs in Supabase (PostgreSQL).

6. **Fault Tolerance** — Implements exponential backoff retry logic for transient API failures.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        XBot Pipeline                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │ Supabase │───▶│   Campaign   │───▶│  Content Generation  │  │
│  │    DB    │    │   Selector   │    │   (Gemini 2.5 Flash) │  │
│  └──────────┘    └──────────────┘    └──────────┬───────────┘  │
│       │                                         │              │
│       │                                         ▼              │
│       │                              ┌──────────────────────┐  │
│       │                              │  Image Generation    │  │
│       │                              │  (Gemini Image Model)│  │
│       │                              └──────────┬───────────┘  │
│       │                                         │              │
│       │                                         ▼              │
│       │                              ┌──────────────────────┐  │
│       │                              │    X API Publisher   │  │
│       │                              │  (v2 Tweet + v1.1    │  │
│       │                              │   Media Upload)      │  │
│       │                              └──────────┬───────────┘  │
│       │                                         │              │
│       ▼                                         ▼              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Logging & Analytics                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                     Mentions Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  X API v2    │───▶│   Mention    │───▶│  Reply Generator │  │
│  │  Mentions    │    │   Filter     │    │  (Gemini 2.5)    │  │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘  │
│                             │                      │            │
│                             ▼                      ▼            │
│                      ┌──────────────┐    ┌──────────────────┐  │
│                      │  Supabase    │◀───│   Post Reply     │  │
│                      │  (mentions)  │    │   (X API v2)     │  │
│                      └──────────────┘    └──────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | ≥3.10 | Runtime environment |
| X Developer Account | API v2 | Tweet publishing, mentions |
| Google AI Studio | Gemini API | Content & image generation |
| Supabase | Any | PostgreSQL database |

## Installation

```bash
git clone https://github.com/yourusername/xbot.git
cd xbot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Dependencies

```
tweepy==4.14.0           # X API client
google-generativeai==0.8.3  # Gemini SDK
supabase==2.11.0         # Database client
python-dotenv==1.0.1     # Environment management
Pillow                   # Image processing
```

## Configuration

### Environment Variables

Create `.env` from template:

```bash
cp .env.example .env
```

| Variable | Description | Source |
|----------|-------------|--------|
| `X_API_KEY` | X API consumer key | [X Developer Portal](https://developer.x.com/en/portal/dashboard) |
| `X_API_SECRET` | X API consumer secret | X Developer Portal |
| `X_ACCESS_TOKEN` | User access token | X Developer Portal |
| `X_ACCESS_TOKEN_SECRET` | User access token secret | X Developer Portal |
| `GEMINI_API_KEY` | Google Gemini API key | [Google AI Studio](https://aistudio.google.com/apikey) |
| `SUPABASE_URL` | Supabase project URL | [Supabase Dashboard](https://supabase.com/dashboard) → Project Settings → API |
| `SUPABASE_KEY` | Supabase anon/public key | Supabase Dashboard → Project Settings → API |

### `.env.example`

```bash
# X (Twitter) API
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_ACCESS_TOKEN=your_x_access_token
X_ACCESS_TOKEN_SECRET=your_x_access_token_secret

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

## Database Schema

Execute the following DDL in Supabase SQL Editor:

```sql
-- Campaign definitions
CREATE TABLE campaigns (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    system_prompt TEXT,
    topic_list JSONB DEFAULT '[]'::jsonb,
    active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Post history
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    x_post_id TEXT,
    posted_at TIMESTAMPTZ
);

-- Mentions tracking
CREATE TABLE mentions (
    id SERIAL PRIMARY KEY,
    mention_id TEXT NOT NULL UNIQUE,
    author_username TEXT,
    mention_text TEXT,
    reply_text TEXT,
    reply_id TEXT,
    replied_at TIMESTAMPTZ DEFAULT NOW()
);

-- Operational logs
CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    message TEXT NOT NULL,
    level TEXT CHECK (level IN ('INFO', 'WARNING', 'ERROR')) DEFAULT 'INFO',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for query optimization
CREATE INDEX idx_campaigns_active ON campaigns(active);
CREATE INDEX idx_posts_campaign_id ON posts(campaign_id);
CREATE INDEX idx_mentions_mention_id ON mentions(mention_id);
CREATE INDEX idx_logs_level ON logs(level);
CREATE INDEX idx_logs_created_at ON logs(created_at DESC);
```

## Usage

### Command Line Interface

```bash
# Execute with any active campaign
python bot.py

# Execute specific campaign
python bot.py --campaign "Campaign Name"

# Dry run (no API calls to X)
python bot.py --test

# Campaign management
python bot.py --add           # Interactive campaign creation
python bot.py --list          # List all campaigns
python bot.py --toggle <id>   # Toggle campaign active state

# Mentions auto-reply
python bot.py --mentions              # Process mentions
python bot.py --mentions --limit 10   # Process up to 10 mentions
python bot.py --mentions --test       # Dry run mentions
```

### CLI Reference

| Flag | Type | Description |
|------|------|-------------|
| `--campaign` | `string` | Target campaign name or ad-hoc description |
| `--test` | `flag` | Enable dry-run mode |
| `--add` | `flag` | Launch interactive campaign creator |
| `--list` | `flag` | Display all campaigns with status |
| `--toggle` | `integer` | Toggle active state by campaign ID |
| `--mentions` | `flag` | Process and reply to mentions |
| `--limit` | `integer` | Max mentions to process (default: 5) |

## Campaign Management

### Creating a Campaign

```
$ python bot.py --add

=== Add New Campaign ===
Campaign name: Blockchain News
System prompt: You are a blockchain analyst sharing breaking news. Write concise tweets explaining complex concepts simply. Use #Blockchain #Web3 #Crypto.
Topics (comma-separated): DeFi updates, NFT innovations, Layer 2 solutions, Smart contracts
Activate now? (y/n): y
Campaign 'Blockchain News' added successfully!
```

### Campaign Data Model

| Field | Type | Description |
|-------|------|-------------|
| `name` | `TEXT` | Unique campaign identifier |
| `system_prompt` | `TEXT` | LLM system instruction defining tone and style |
| `topic_list` | `JSONB` | Array of topics for random selection |
| `active` | `BOOLEAN` | Eligibility for automated execution |

## Mentions Auto-Reply

The mentions feature automatically monitors and responds to @mentions using AI-generated contextual replies.

### How It Works

1. **Fetch Mentions** — Retrieves recent mentions via X API v2
2. **Filter Processed** — Skips mentions already in the `mentions` table
3. **Generate Reply** — Uses Gemini to create contextual response based on mention content
4. **Post Reply** — Sends reply as a threaded response
5. **Log to Database** — Records mention and reply for tracking

### Example

```
$ python bot.py --mentions

Starting mentions bot...
Authenticated as @yourbot (ID: 123456789)

Mention from @user1: What's the latest on Ethereum upgrades?...
Generated reply: The Pectra upgrade is scheduled for Q1 2025, bringing account abstraction and improved validator operations. Exciting times for ETH!
Replied! ID: 987654321

Processed 1 mentions.
```

### Mentions Data Model

| Field | Type | Description |
|-------|------|-------------|
| `mention_id` | `TEXT` | Original mention tweet ID |
| `author_username` | `TEXT` | Username who mentioned the bot |
| `mention_text` | `TEXT` | Content of the mention |
| `reply_text` | `TEXT` | AI-generated reply |
| `reply_id` | `TEXT` | Posted reply tweet ID |
| `replied_at` | `TIMESTAMPTZ` | Timestamp of reply |

## CI/CD Pipeline

### GitHub Actions Workflows

| File | Schedule | Action |
|------|----------|--------|
| `.github/workflows/post.yml` | `0 9,18 * * *` | Post content (9 AM & 6 PM UTC) |
| `.github/workflows/mentions.yml` | `0 */4 * * *` | Check mentions (every 4 hours) |

### Required Repository Secrets

Configure in: Repository → Settings → Secrets and variables → Actions

| Secret | Required |
|--------|----------|
| `X_API_KEY` | ✓ |
| `X_API_SECRET` | ✓ |
| `X_ACCESS_TOKEN` | ✓ |
| `X_ACCESS_TOKEN_SECRET` | ✓ |
| `GEMINI_API_KEY` | ✓ |
| `SUPABASE_URL` | ✓ |
| `SUPABASE_KEY` | ✓ |

### Manual Workflow Dispatch

**Post workflow** (`post.yml`):
- `campaign`: Specific campaign name (optional)
- `dry_run`: Boolean flag for test mode

**Mentions workflow** (`mentions.yml`):
- `dry_run`: Boolean flag for test mode

## API Reference

### Internal Functions

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `get_active_campaign` | `supabase`, `campaign_name?` | `dict \| None` | Fetches active campaign from database |
| `generate_content` | `supabase`, `campaign_data?`, `campaign_description?` | `tuple[str, str]` | Generates tweet text and image prompt |
| `generate_reply` | `mention_text`, `author_username` | `str \| None` | Generates contextual reply for mention |
| `run_bot` | `dry_run`, `campaign_name?` | `None` | Main post execution pipeline |
| `run_mentions_bot` | `dry_run`, `limit` | `None` | Mentions processing pipeline |
| `retry_api_call` | `func`, `max_retries`, `delay` | `Any` | Exponential backoff wrapper |
| `add_campaign` | — | `None` | Interactive campaign creation |
| `list_campaigns` | — | `None` | Prints campaign list |
| `toggle_campaign` | `campaign_id` | `None` | Toggles campaign active state |

### External API Dependencies

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Gemini | `generativelanguage.googleapis.com` | Text & image generation |
| X API v2 | `api.twitter.com/2/tweets` | Tweet creation |
| X API v2 | `api.twitter.com/2/users/:id/mentions` | Fetch mentions |
| X API v1.1 | `upload.twitter.com/1.1/media/upload` | Media upload |
| Supabase | `<project>.supabase.co/rest/v1` | Database operations |

## Error Handling

### Retry Mechanism

All external API calls are wrapped with exponential backoff:

```
Attempt 1 → Failure → Wait 2s
Attempt 2 → Failure → Wait 4s
Attempt 3 → Failure → Raise Exception
```

### Logging Levels

| Level | Description |
|-------|-------------|
| `INFO` | Successful operations, content generation |
| `WARNING` | Non-fatal failures (e.g., image generation failed, posting text-only) |
| `ERROR` | Fatal failures logged before exit |

## Limitations

- **Rate Limits**: X API allows 300 tweets per 3-hour window (user auth)
- **Mentions Limit**: X API v2 free tier has limited mention access
- **Character Limit**: Tweets truncated to 280 characters
- **Image Generation**: May fail silently; bot continues with text-only post
- **Single Campaign**: Scheduled runs execute one active campaign per invocation

## Project Structure

```
xbot/
├── bot.py                 # Core application logic
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
├── .env                   # Local credentials (git-ignored)
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        ├── post.yml       # Scheduled posting
        └── mentions.yml   # Scheduled mention replies
```

## License

MIT License. See [LICENSE](LICENSE) for details.
