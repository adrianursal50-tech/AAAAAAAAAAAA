# db.py – PostgreSQL manager for persistent storage
import os
import json
import psycopg2
from psycopg2.extras import Json
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

class DatabaseManager:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self._init_tables()

    def _init_tables(self):
        with self.conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Keys table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS keys_table (
                    key_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Daily usage table (quota, bonus, etc.)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_usage (
                    user_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Referrals table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    user_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Config table (bot settings)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            self.conn.commit()

    # ── Users ────────────────────────────────────────────────
    def load_users(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT user_id, data FROM users")
            rows = cur.fetchall()
            return {row[0]: row[1] for row in rows}

    def save_users(self, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM users")
            for user_id, user_data in data.items():
                cur.execute(
                    "INSERT INTO users (user_id, data) VALUES (%s, %s)",
                    (user_id, Json(user_data))
                )
            self.conn.commit()

    # ── Keys ──────────────────────────────────────────────────
    def load_keys(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT key_id, data FROM keys_table")
            rows = cur.fetchall()
            return {row[0]: row[1] for row in rows}

    def save_keys(self, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM keys_table")
            for key_id, key_data in data.items():
                cur.execute(
                    "INSERT INTO keys_table (key_id, data) VALUES (%s, %s)",
                    (key_id, Json(key_data))
                )
            self.conn.commit()

    # ── Daily Usage ───────────────────────────────────────────
    def load_daily(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT user_id, data FROM daily_usage")
            rows = cur.fetchall()
            return {row[0]: row[1] for row in rows}

    def save_daily(self, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM daily_usage")
            for user_id, usage_data in data.items():
                cur.execute(
                    "INSERT INTO daily_usage (user_id, data) VALUES (%s, %s)",
                    (user_id, Json(usage_data))
                )
            self.conn.commit()

    # ── Referrals ─────────────────────────────────────────────
    def load_referrals(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT user_id, data FROM referrals")
            rows = cur.fetchall()
            return {row[0]: row[1] for row in rows}

    def save_referrals(self, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM referrals")
            for user_id, ref_data in data.items():
                cur.execute(
                    "INSERT INTO referrals (user_id, data) VALUES (%s, %s)",
                    (user_id, Json(ref_data))
                )
            self.conn.commit()

    # ── Config ────────────────────────────────────────────────
    def load_config(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT key, value FROM config")
            rows = cur.fetchall()
            # Expected: one row with key='bot_config'
            for k, v in rows:
                if k == 'bot_config':
                    return v
            return {}

    def save_config(self, data: dict):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO config (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                ('bot_config', Json(data))
            )
            self.conn.commit()

# Singleton instance
_db = None
def get_db():
    global _db
    if _db is None:
        _db = DatabaseManager()
    return _db