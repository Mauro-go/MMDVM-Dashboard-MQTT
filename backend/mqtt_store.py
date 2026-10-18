import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / 'data' / 'events.sqlite3'


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB), timeout=10)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        mode TEXT NOT NULL,
        action TEXT,
        payload TEXT NOT NULL
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp)')
    return con


def save(con, timestamp, mode, action, payload):
    con.execute('INSERT INTO events(timestamp,mode,action,payload) VALUES(?,?,?,?)',
                (timestamp, mode, action, json.dumps(payload, ensure_ascii=False)))
    con.commit()
