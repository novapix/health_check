# Health Check Reporter

This is a Python-based async service that performs health checks on services like Supabase, Neo4j, Pinecone, and Redis. It sends periodic status reports to a Discord webhook.

## Features

- Hourly automated health checks
- Sends reports to Discord
- Async support for better performance

## Services Checked

- **Supabase** — Checks if storage buckets are accessible
- **Neo4j** — Verifies database connectivity
- **Pinecone** — Checks if indexes are present
- **Redis** — Pings the Redis server

## Requirements

- Python 3.11+
- Docker (optional)
- uv (optional but recommended)

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/novapix/health_check.git
cd health-check-reporter
```

### 2. Create `.env` File

Create a `.env` file in the root directory with the following content:

```env
# Supabase
SUPABASE_URL=https://your-supabase-url.supabase.co
SUPABASE_KEY=your-supabase-key

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

# Pinecone
PINECONE_API_KEY=your-pinecone-api-key

# Discord Webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Redis
REDIS_URL=redis://:yourpassword@localhost:6379/0
```

### 3. Install Dependencies

```bash
uv sync
```

### 4. Run the Script

```bash
uv run python main.py
```

The health checks will run immediately and then every hour.

## Docker

### Build Docker Image

```bash
docker build -t health-check-reporter .
```

### Run Container with `.env`

```bash
docker run --env-file .env health-check-reporter
```

## Example Output (in Discord)

```
Automated report at August 26, 2025 10:00 AM
Next scheduled run: August 26, 2025 11:00 AM

✅ Supabase: healthy (3 buckets found)
✅ Neo4j: healthy (connection verified)
⚠️ Pinecone: warning: no indexes found
❌ Redis: error: Connection refused
```

> The actual output will use Discord's timestamp formatting and embed layout.

## License

MIT
