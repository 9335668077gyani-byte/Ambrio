import aiosqlite, asyncio
from contextlib import asynccontextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parents[3] / 'db' / 'schema.sql'

class Database:
    def __init__(self, path: str):
        self._path = path

    async def init(self):
        schema = SCHEMA_PATH.read_text()
        # executescript handles multi-statement SQL including BEGIN...END trigger blocks
        # It also implicitly commits any pending transaction
        async with aiosqlite.connect(self._path) as c:
            await c.executescript(schema)


    @asynccontextmanager
    async def conn(self):
        async with aiosqlite.connect(self._path) as c:
            c.row_factory = aiosqlite.Row
            await c.execute('PRAGMA foreign_keys=ON')
            yield c
