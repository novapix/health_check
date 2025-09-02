import os
import asyncio
import aiohttp
from sys import stderr
from dotenv import load_dotenv
from supabase import acreate_client, AsyncClient
from neo4j import AsyncGraphDatabase
from pinecone import Pinecone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR
import redis.asyncio as aioredis

from datetime import datetime,timedelta
import pytz
from loguru import logger
from aiohttp import web
# --- Configuration & Logging ---
load_dotenv()
logger.remove()
logger.add(stderr, level="INFO")


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
# REDIS_URL = os.getenv("REDIS_URL")
REDIS_URL = os.getenv("REDIS_URL") or f"redis://:{os.getenv('REDIS_PASSWORD')}@{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/0"


MAX_RETRIES = 3
BACKOFF_BASE = 2  # sleep for 2^0, 2^1, 2^2 seconds
timezone = pytz.timezone('Asia/Kathmandu')

latest_status_report: dict[str, str] = {}
scheduler = AsyncIOScheduler()

async def handle_health(request):
    return web.json_response({"status": "ok", "message": "Service is running."})

async def handle_status(request):
    if not latest_status_report:
        return web.json_response({"status": "pending", "message": "Health check not run yet."}, status=503)
    return web.json_response(latest_status_report)



async def get_async_supabase() -> AsyncClient:
    return await acreate_client(SUPABASE_URL, SUPABASE_KEY)
async def check_supabase() -> str:
    """Pings Supabase Storage with retries and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Checking Supabase connection (attempt {attempt + 1})...")
            if not SUPABASE_URL or not SUPABASE_KEY:
                return "error: Supabase URL or Key not configured"

            supabase: AsyncClient = await get_async_supabase()
            buckets = await supabase.storage.list_buckets()
            logger.info(f"Supabase connection successful, {len(buckets)} buckets found.")
            return f"healthy ({len(buckets)} buckets found)"

        except Exception as e:
            logger.warning(f"Supabase health check failed (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return f"error: {str(e)}"
            await asyncio.sleep(BACKOFF_BASE**attempt)
    return "error: All retry attempts failed" # Should not be reached, but for safety

async def check_neo4j() -> str:
    """Pings Neo4j with retries and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Checking Neo4j connection (attempt {attempt + 1})...")
            if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
                return "error: Neo4j credentials not fully configured"

            async with AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
                await driver.verify_connectivity()
                result = await driver.execute_query("RETURN 1 AS test")

                records = result.records
                for record in records:
                    logger.info(record["test"])
            logger.info("Neo4j connection verified successfully.")
            return "healthy (connection verified)"

        except Exception as e:
            logger.warning(f"Neo4j health check failed (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return f"error: {str(e)}"
            await asyncio.sleep(BACKOFF_BASE**attempt)
    return "error: All retry attempts failed"

async def check_pinecone() -> str:
    """Pings Pinecone with retries and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Checking Pinecone connection (attempt {attempt + 1})...")
            if not PINECONE_API_KEY:
                return "error: Pinecone API Key not configured"

            pc = Pinecone(api_key=PINECONE_API_KEY)
            indexes = pc.list_indexes().names()

            if indexes:
                logger.info(f"Pinecone connection found {len(indexes)} indexes.")
                return f"healthy ({len(indexes)} indexes found)"
            else:
                logger.info("Pinecone connection OK but no indexes found.")
                return "warning: connection OK but no indexes found"

        except Exception as e:
            logger.warning(f"Pinecone health check failed (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return f"error: {str(e)}"
            await asyncio.sleep(BACKOFF_BASE**attempt)
    return "error: All retry attempts failed"


async def check_redis() -> str:
    """Pings Redis with retries and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Checking Redis connection (attempt {attempt + 1})...")
            if not REDIS_URL:
                return "error: Redis URL not configured"

            redis = aioredis.from_url(REDIS_URL)
            pong = await redis.ping()

            if pong:
                logger.info("Redis ping successful.")
                return "healthy (ping successful)"
            else:
                return "warning: Redis responded but did not pong"
        except Exception as e:
            logger.warning(f"Redis health check failed (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return f"error: {str(e)}"
            await asyncio.sleep(BACKOFF_BASE ** attempt)

    return "error: All retry attempts failed"

async def send_to_discord(status_report: dict[str, str]):
    """Formats and sends the health check status report to a Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        logger.error("Discord Webhook URL not configured. Cannot send report.")
        return

    is_any_error = any("error:" in result for result in status_report.values())
    report_color = 0xff0000 if is_any_error else 0x00ff00

    now = datetime.now(timezone)
    next_run = now + timedelta(hours=1)


    next_run_unix = int(next_run.timestamp())
    discord_current_time = f"<t:{int(now.timestamp())}:F>"
    discord_next_time = f"<t:{next_run_unix}:F>"

    description = f"Automated report at **{discord_current_time}**\nNext scheduled run: {discord_next_time}"

    def get_icon(result_str: str) -> str:
        if result_str.startswith("healthy"): return "✅"
        if result_str.startswith("warning"): return "⚠️"
        return "❌"

    embed = {
        "title": "Service Health Check Status",
        "description": description,
        "color": report_color,
        "fields": [
            {
                "name": f"{get_icon(result)} {service_name}",
                "value": result,
                "inline": False
            } for service_name, result in status_report.items()
        ]
    }
    payload = {"embeds": [embed]}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as response:
                response.raise_for_status()
                logger.info("Successfully sent report to Discord.")
        except aiohttp.ClientError as e:
            logger.error(f"Failed to send report to Discord: {e}")

async def run_health_checks():
    """Runs all checks concurrently and sends the report."""
    logger.info("Running scheduled health checks...")

    # Run checks concurrently for better performance
    results = await asyncio.gather(
        check_supabase(),
        check_neo4j(),
        check_pinecone(),
        check_redis(),
    )
    status_report = {
        "Supabase": results[0],
        "Neo4j": results[1],
        "Pinecone": results[2],
        "Redis": results[3],
    }
    logger.info("📊 Health check complete. Sending report to Discord...")
    await send_to_discord(status_report)
    logger.info("✅ Job finished. Waiting for the next scheduled run.")
    global latest_status_report
    # latest_status_report.clear()
    latest_status_report = status_report
    latest_status_report["last_checked"]=datetime.now(timezone).isoformat()

def job_listener(event):
    if event.exception:
        logger.error("❌ Scheduled job crashed!", exc_info=event.exception)
    else:
        logger.debug("✅ Scheduled job ran successfully.")

async def on_startup(app):
    # Schedule recurring health check
    scheduler.add_job(run_health_checks, 'interval', hours=1)
    scheduler.add_listener(job_listener, EVENT_JOB_ERROR)
    scheduler.start()
    logger.info("🚀 Scheduler initialized.")

    # Run immediately on startup
    await run_health_checks()

def create_app():
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/status", handle_status)
    app.on_startup.append(on_startup)
    return app
#
# async def main():
#     """Sets up the scheduler and runs the main application loop."""
#     scheduler = AsyncIOScheduler()
#     scheduler.add_job(run_health_checks, 'interval', hours=1)
#     scheduler.start()
#
#     logger.info("🚀 Scheduler initialized. The first check will run immediately.")
#     await run_health_checks()
#
#     app = await create_app()
#
#     # Start HTTP server on port 8000
#     runner = web.AppRunner(app)
#     await runner.setup()
#     site = web.TCPSite(runner, "0.0.0.0", 8000)
#     await site.start()
#
#     logger.info("HTTP server running at http://0.0.0.0:8000/")
#
#
#     try:
#         # Wait indefinitely until interrupted
#         await asyncio.Event().wait()
#     except (KeyboardInterrupt, SystemExit):
#         logger.info("Shutting down...")
#         await runner.cleanup()

if __name__ == "__main__":
    load_dotenv()
    logger.info("🌐 Starting web server...")
    web.run_app(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", 8000)))