import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Rows are (ts, value) for gold and (ts, lvl, rebirths) for levels.
GoldRow = Tuple[float, int]
LevelRow = Tuple[float, int, int]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gold_events (
    user_id INTEGER NOT NULL,
    ts REAL NOT NULL,
    balance INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS gold_user_ts ON gold_events (user_id, ts);
CREATE TABLE IF NOT EXISTS level_events (
    user_id INTEGER NOT NULL,
    ts REAL NOT NULL,
    lvl INTEGER NOT NULL,
    exp INTEGER NOT NULL,
    rebirths INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS level_user_ts ON level_events (user_id, ts);
"""


class StatsDB:
    """SQLite store for adventure gold and level history.

    All sqlite access runs on a single worker thread so the connection is never
    shared across threads and the event loop is never blocked. Writes are buffered
    and flushed periodically since gold changes are frequent.
    """

    def __init__(self, path: Path):
        self.path = path
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="advstats")
        self._conn: Optional[sqlite3.Connection] = None
        self._gold_buffer: List[Tuple[int, float, int]] = []
        self._level_buffer: List[Tuple[int, float, int, int, int]] = []

    async def _run(self, func, *args):
        return await asyncio.get_running_loop().run_in_executor(self._executor, func, *args)

    # ---- lifecycle -------------------------------------------------------

    def _open(self):
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    async def open(self):
        await self._run(self._open)

    def _close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    async def close(self):
        await self.flush()
        await self._run(self._close)
        self._executor.shutdown(wait=False)

    # ---- writes ----------------------------------------------------------

    def add_gold(self, user_id: int, ts: float, balance: int):
        self._gold_buffer.append((user_id, ts, int(balance)))

    def add_level(self, user_id: int, ts: float, lvl: int, exp: int, rebirths: int):
        self._level_buffer.append((user_id, ts, int(lvl), int(exp), int(rebirths)))

    def _write(self, gold, level):
        if gold:
            self._conn.executemany("INSERT INTO gold_events VALUES (?, ?, ?)", gold)
        if level:
            self._conn.executemany("INSERT INTO level_events VALUES (?, ?, ?, ?, ?)", level)
        self._conn.commit()

    async def flush(self):
        if not self._gold_buffer and not self._level_buffer:
            return
        gold, self._gold_buffer = self._gold_buffer, []
        level, self._level_buffer = self._level_buffer, []
        await self._run(self._write, gold, level)

    def _delete_user(self, user_id: int):
        self._conn.execute("DELETE FROM gold_events WHERE user_id = ?", (user_id,))
        self._conn.execute("DELETE FROM level_events WHERE user_id = ?", (user_id,))
        self._conn.commit()

    async def delete_user(self, user_id: int):
        await self.flush()
        await self._run(self._delete_user, user_id)

    # ---- reads -----------------------------------------------------------

    def _known_users(self, table: str) -> set:
        return {r[0] for r in self._conn.execute(f"SELECT DISTINCT user_id FROM {table}")}

    async def known_users(self, table: str) -> set:
        await self.flush()
        return await self._run(self._known_users, table)

    def _series(self, table: str, cols: str, user_ids: Iterable[int], since: float) -> Dict[int, list]:
        out = {}
        for uid in user_ids:
            # The last row before the window anchors the line at the window's left edge.
            anchor = self._conn.execute(
                f"SELECT ts, {cols} FROM {table} WHERE user_id = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
                (uid, since),
            ).fetchone()
            rows = self._conn.execute(
                f"SELECT ts, {cols} FROM {table} WHERE user_id = ? AND ts >= ? ORDER BY ts",
                (uid, since),
            ).fetchall()
            if anchor:
                rows.insert(0, (since, *anchor[1:]))
            if rows:
                out[uid] = rows
        return out

    async def gold_series(self, user_ids: Iterable[int], since: float) -> Dict[int, List[GoldRow]]:
        await self.flush()
        return await self._run(self._series, "gold_events", "balance", list(user_ids), since)

    async def level_series(self, user_ids: Iterable[int], since: float) -> Dict[int, List[LevelRow]]:
        await self.flush()
        return await self._run(self._series, "level_events", "lvl, rebirths", list(user_ids), since)

    def _latest(self, query: str) -> list:
        # SQLite returns the bare columns from the row holding MAX(ts).
        return self._conn.execute(query).fetchall()

    async def latest_gold(self) -> Dict[int, int]:
        await self.flush()
        rows = await self._run(
            self._latest, "SELECT user_id, balance, MAX(ts) FROM gold_events GROUP BY user_id"
        )
        return {uid: bal for uid, bal, _ in rows}

    async def latest_level(self) -> Dict[int, Tuple[int, int]]:
        await self.flush()
        rows = await self._run(
            self._latest, "SELECT user_id, lvl, rebirths, MAX(ts) FROM level_events GROUP BY user_id"
        )
        return {uid: (lvl, rb) for uid, lvl, rb, _ in rows}
