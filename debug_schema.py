import asyncio, tempfile, os, aiosqlite

async def debug():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name

    # Check what tables/triggers actually exist after init
    from ambrio.router.memory.db import Database
    db = Database(path)
    await db.init()

    async with aiosqlite.connect(path) as c:
        cur = await c.execute("SELECT type, name FROM sqlite_master ORDER BY type, name")
        rows = await cur.fetchall()
        print('Schema objects:')
        for r in rows:
            print(f'  {r[0]:10} {r[1]}')

    os.unlink(path)

asyncio.run(debug())
