import json
import sqlite3
from pathlib import Path
from .simulation import fresh


class Store:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(Path(directory)/"waypoint.sqlite"), check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        if not self.connection.execute("SELECT 1 FROM workspace").fetchone():
            self.save(fresh())

    def load(self):
        return json.loads(self.connection.execute("SELECT payload FROM workspace WHERE id=1").fetchone()[0])

    def save(self, state):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO workspace VALUES (1, ?)", (json.dumps(state),))

    def save_run(self, run):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO runs VALUES (?, ?)", (run["id"], json.dumps(run)))

    def commit_decision(self, state, run):
        with self.connection:
            self.connection.execute("UPDATE workspace SET payload=? WHERE id=1", (json.dumps(state),))
            self.connection.execute("INSERT OR REPLACE INTO runs VALUES (?, ?)", (run["id"], json.dumps(run)))

    def runs(self):
        return [json.loads(r[0]) for r in self.connection.execute("SELECT payload FROM runs ORDER BY rowid DESC LIMIT 50")]

    def run(self, run_id):
        row = self.connection.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None
