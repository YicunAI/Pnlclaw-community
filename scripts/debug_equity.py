import asyncio
import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

async def check_equity_data():
    from app.core.dependencies import get_db_manager
    db = get_db_manager()
    if not db:
        print("Error: DB manager not found")
        return

    async with db.pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM paper_equity_history")
        print(f"Total equity points: {count}")
        
        if count > 0:
            latest = await conn.fetchrow("SELECT * FROM paper_equity_history ORDER BY timestamp DESC LIMIT 1")
            print(f"Latest record: {dict(latest)}")

if __name__ == "__main__":
    asyncio.run(check_equity_data())
