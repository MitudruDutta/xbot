# xbot

Automated X (Twitter) marketing bot powered by Google Gemini AI. Generates and posts AI-crafted tweets with images based on configurable campaigns.

## Features

- AI-generated tweet content using Gemini 2.5 Flash
- AI-generated images using Gemini image models
- Campaign management with topics and custom prompts
- Supabase database for campaigns, posts, and logs
- Dry-run mode for testing
- GitHub Actions for scheduled posting
- Retry logic for API resilience

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

`.env.example` contents:
```bash
# X (Twitter) API - https://developer.x.com/en/portal/dashboard
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_ACCESS_TOKEN=your_x_access_token
X_ACCESS_TOKEN_SECRET=your_x_access_token_secret

# Google Gemini API - https://aistudio.google.com/apikey
GEMINI_API_KEY=your_gemini_api_key

# Supabase - https://supabase.com/dashboard (Project Settings > API)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

### 3. Supabase tables
Create these tables in your Supabase project:

```sql
-- Campaigns
create table campaigns (
  id serial primary key,
  name text not null,
  system_prompt text,
  topic_list jsonb,
  active boolean default false,
  created_at timestamp default now()
);

-- Posts
create table posts (
  id serial primary key,
  campaign_id int references campaigns(id),
  content text,
  x_post_id text,
  posted_at timestamp
);

-- Logs
create table logs (
  id serial primary key,
  message text,
  level text,
  created_at timestamp default now()
);
```

## Usage

### Run the bot
```bash
# Run with any active campaign
python bot.py

# Run specific campaign
python bot.py --campaign "Tech News"

# Dry run (no posting)
python bot.py --test
```

### Manage campaigns
```bash
# Add new campaign
python bot.py --add

# List all campaigns
python bot.py --list

# Toggle campaign active/inactive
python bot.py --toggle <campaign_id>
```

### Example: Adding a campaign
```
$ python bot.py --add

=== Add New Campaign ===
Campaign name: Blockchain News
System prompt: You are a blockchain analyst sharing breaking news. Write concise tweets explaining complex concepts simply. Use #Blockchain #Web3 #Crypto.
Topics (comma-separated): DeFi updates, NFT innovations, Layer 2 solutions, Smart contracts
Activate now? (y/n): y
Campaign 'Blockchain News' added successfully!
```

## GitHub Actions

The bot runs automatically at 9:00 AM and 6:00 PM UTC via `.github/workflows/daily_post.yml`.

Add your environment variables as repository secrets in GitHub.

## License

MIT
