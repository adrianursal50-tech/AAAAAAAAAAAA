#!/usr/bin/env python3
"""
CODM Checker Telegram Bot – Railway‑ready
Includes robust import path handling, PostgreSQL/SQLite, license keys,
referral system, admin panel, live stats, and background zipping.
"""

import os
import sys
import time
import json
import zipfile
import logging
import threading
import asyncio
import shutil
import random
import string
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple

# ── Force the script directory into Python's import path ──────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ── Debug: show what files are present ────────────────────────────────
print(f"Current working directory: {os.getcwd()}")
print(f"Script directory: {SCRIPT_DIR}")
print("Files in script directory:")
try:
    for f in os.listdir(SCRIPT_DIR):
        print(f"  - {f}")
except Exception as e:
    print(f"  Could not list files: {e}")

# ── Import from checker.py ──────────────────────────────────────────────
try:
    from checker import (
        ProxyManager, CookieManager, DataDomeManager,
        process_account, LiveStats, ResultsManager, run_check,
        clean_account_line, format_mobile_number,
    )
    print("✅ checker.py imported successfully.")
except ImportError as e:
    print(f"❌ checker.py not found. Error: {e}")
    print("Please ensure checker.py is in the same folder as main.py.")
    sys.exit(1)

# ── Database adapter ─────────────────────────────────────────────────────
DB_URL = os.environ.get("DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres"):
    try:
        import psycopg2
        DB_TYPE = "postgres"
    except ImportError:
        print("psycopg2 not installed. Falling back to SQLite.")
        DB_TYPE = "sqlite"
else:
    DB_TYPE = "sqlite"

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest

# ──────────────────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8597114754:AAH3nvgyXWg1KpQq1_Qn2Lva2J0yozUJxGc"
    print("[WARNING] Using hardcoded token. Set BOT_TOKEN env var.")

DEFAULT_THREADS = 5
LIVE_INTERVAL = 3.0
TG_MAX_BYTES = 49 * 1024 * 1024
PH_TIMEZONE = timezone(timedelta(hours=8))

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
LOG = logging.getLogger("codm_bot")

# ──────────────────────────────────────────────────────────────────────────
#  DATABASE LAYER (SQLite / PostgreSQL)
# ──────────────────────────────────────────────────────────────────────────
class Database:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.type = DB_TYPE
        self._connect()

    def _connect(self):
        if self.type == "postgres":
            self.conn = psycopg2.connect(DB_URL, sslmode='require')
            self.conn.autocommit = False
            self.cursor = self.conn.cursor()
        else:
            import sqlite3
            self.conn = sqlite3.connect("bot_data.db", check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.cursor = self.conn.cursor()

    def execute(self, query, params=()):
        try:
            self.cursor.execute(query, params)
        except Exception as e:
            self.conn.rollback()
            raise e

    def commit(self):
        self.conn.commit()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchone(self):
        return self.cursor.fetchone()

    def close(self):
        if self.conn:
            self.conn.close()

    def init_tables(self):
        if self.type == "postgres":
            self.execute("""
                CREATE TABLE IF NOT EXISTS keys (
                    key TEXT PRIMARY KEY,
                    duration_seconds INTEGER NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_by INTEGER NULL,
                    used_at TIMESTAMP NULL,
                    is_revoked BOOLEAN DEFAULT FALSE
                )
            """)
            self.execute("""
                CREATE TABLE IF NOT EXISTS user_keys (
                    user_id INTEGER PRIMARY KEY,
                    key TEXT NOT NULL,
                    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (key) REFERENCES keys(key)
                )
            """)
            self.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY
                )
            """)
            self.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    user_id INTEGER PRIMARY KEY,
                    referral_code TEXT UNIQUE NOT NULL,
                    referred_by INTEGER NULL,
                    referral_count INTEGER DEFAULT 0,
                    reward_granted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referred_by) REFERENCES referrals(user_id)
                )
            """)
            self.execute("INSERT INTO admins (user_id) VALUES (8621676055) ON CONFLICT DO NOTHING")
        else:
            self.execute("""
                CREATE TABLE IF NOT EXISTS keys (
                    key TEXT PRIMARY KEY,
                    duration_seconds INTEGER NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_by INTEGER NULL,
                    used_at TIMESTAMP NULL,
                    is_revoked BOOLEAN DEFAULT 0
                )
            """)
            self.execute("""
                CREATE TABLE IF NOT EXISTS user_keys (
                    user_id INTEGER PRIMARY KEY,
                    key TEXT NOT NULL,
                    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (key) REFERENCES keys(key)
                )
            """)
            self.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY
                )
            """)
            self.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    user_id INTEGER PRIMARY KEY,
                    referral_code TEXT UNIQUE NOT NULL,
                    referred_by INTEGER NULL,
                    referral_count INTEGER DEFAULT 0,
                    reward_granted BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referred_by) REFERENCES referrals(user_id)
                )
            """)
            self.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (8621676055)")
        self.commit()

db = Database()
db.init_tables()

# ──────────────────────────────────────────────────────────────────────────
#  DB HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────
def db_execute(query, params=()):
    db.execute(query, params)
    db.commit()

def db_query(query, params=()):
    db.execute(query, params)
    return db.fetchall()

def generate_key() -> str:
    chars = string.ascii_uppercase + string.digits
    raw = ''.join(random.choices(chars, k=16))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:]}"

def generate_referral_code() -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=8))
        if not db_query("SELECT 1 FROM referrals WHERE referral_code = ?", (code,)):
            return code

def parse_duration(text: str) -> int:
    text = text.strip().lower()
    if text.endswith('d'): return int(text[:-1]) * 86400
    if text.endswith('h'): return int(text[:-1]) * 3600
    if text.endswith('m'): return int(text[:-1]) * 60
    return int(text)

def is_admin(user_id: int) -> bool:
    return len(db_query("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))) > 0

def is_key_valid(key: str) -> Tuple[bool, Optional[int]]:
    rows = db_query("SELECT duration_seconds, used_by, is_revoked FROM keys WHERE key = ?", (key,))
    if not rows: return False, None
    dur, used, revoked = rows[0]
    if revoked or used is not None: return False, None
    return True, dur

def get_user_expiry(user_id: int) -> Optional[datetime]:
    rows = db_query("SELECT expires_at FROM user_keys WHERE user_id = ?", (user_id,))
    if not rows: return None
    return datetime.fromisoformat(rows[0][0])

def has_active_key(user_id: int) -> bool:
    expiry = get_user_expiry(user_id)
    if expiry is None: return False
    return datetime.now(timezone.utc) < expiry

def activate_key(user_id: int, key: str) -> bool:
    valid, dur = is_key_valid(key)
    if not valid: return False
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=dur)
    db_execute(
        "INSERT OR REPLACE INTO user_keys (user_id, key, activated_at, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, key, now.isoformat(), expires.isoformat())
    )
    db_execute("UPDATE keys SET used_by = ?, used_at = ? WHERE key = ?", (user_id, now.isoformat(), key))
    return True

def grant_key_to_user(user_id: int, duration_seconds: int, created_by: int = 0) -> bool:
    key = generate_key()
    db_execute(
        "INSERT INTO keys (key, duration_seconds, created_by) VALUES (?, ?, ?)",
        (key, duration_seconds, created_by)
    )
    return activate_key(user_id, key)

def get_referral_info(user_id: int):
    rows = db_query(
        "SELECT referral_code, referred_by, referral_count, reward_granted FROM referrals WHERE user_id = ?",
        (user_id,)
    )
    return rows[0] if rows else None

def create_referral(user_id: int, referred_by: int = None) -> str:
    code = generate_referral_code()
    db_execute(
        "INSERT INTO referrals (user_id, referral_code, referred_by, referral_count, reward_granted) VALUES (?, ?, ?, 0, 0)",
        (user_id, code, referred_by)
    )
    return code

def format_ph_time(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PH_TIMEZONE).strftime('%Y-%m-%d %I:%M:%S %p PHT')

# ──────────────────────────────────────────────────────────────────────────
#  BOT STATE, SESSION, LIVE STATS
# ──────────────────────────────────────────────────────────────────────────
class BotState:
    def __init__(self, user_id: int, chat_id: int, threads: int, stop_event: threading.Event):
        self.user_id = user_id
        self.chat_id = chat_id
        self.threads = threads
        self.stop_event = stop_event
        self.live_stats = LiveStats()
        self.proxy_mgr = ProxyManager()
        self.cookie_mgr = CookieManager()
        self.datadome_mgr = DataDomeManager()
        self.results_mgr = None
        self.is_running = True
        self.finished = False

    def should_stop(self):
        return self.stop_event.is_set()

    def finish(self):
        self.is_running = False
        self.finished = True

class CheckerSession:
    def __init__(self, user_id, chat_id, combo_file, threads):
        self.user_id = user_id
        self.chat_id = chat_id
        self.combo_file = combo_file
        self.threads = threads
        self.stop_event = threading.Event()
        self.state = BotState(user_id, chat_id, threads, self.stop_event)
        self.thread = None
        self.live_message_id = None
        self.finished = False
        self.is_running = True
        self.combo_stem = Path(combo_file).stem

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.is_running = False

    def mark_finished(self):
        self.is_running = False
        self.finished = True

    def get_stats(self):
        return self.state.live_stats.snap()

active_sessions: Dict[int, CheckerSession] = {}
session_lock = threading.Lock()
app_instance = None
event_loop = None

# ──────────────────────────────────────────────────────────────────────────
#  HELPERS: ZIP + SEND
# ──────────────────────────────────────────────────────────────────────────
def zip_results_folder(folder: Path, out: Path) -> List[Path]:
    files = sorted([f for f in folder.rglob("*") if f.is_file() and f != out and not f.name.endswith(".zip")])
    if not files:
        return []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(folder))
    if out.stat().st_size <= TG_MAX_BYTES:
        return [out]
    out.unlink()
    parts = []
    part_num = 1
    cur_files = []
    cur_size = 0
    for f in files:
        fsize = f.stat().st_size
        if cur_files and cur_size + fsize > TG_MAX_BYTES:
            pout = out.parent / f"{out.stem}_part{part_num}{out.suffix}"
            with zipfile.ZipFile(pout, "w", zipfile.ZIP_DEFLATED) as zf:
                for cf in cur_files:
                    zf.write(cf, cf.relative_to(folder))
            parts.append(pout)
            part_num += 1
            cur_files = []
            cur_size = 0
        cur_files.append(f)
        cur_size += fsize
    if cur_files:
        pout = out.parent / f"{out.stem}_part{part_num}{out.suffix}"
        with zipfile.ZipFile(pout, "w", zipfile.ZIP_DEFLATED) as zf:
            for cf in cur_files:
                zf.write(cf, cf.relative_to(folder))
        parts.append(pout)
    return parts

def send_results_background(session: CheckerSession):
    try:
        rm = session.state.results_mgr
        if not rm or not rm.base.exists():
            return
        zip_parts = zip_results_folder(rm.base, rm.base / "results.zip")
        if zip_parts:
            total = len(zip_parts)
            for idx, zp in enumerate(zip_parts, 1):
                caption = f"📦 Results part {idx}/{total}" if total > 1 else "📦 Your results"
                with open(zp, "rb") as f:
                    safe_send_document(session.chat_id, f, zp.name, caption)
                try:
                    zp.unlink()
                except:
                    pass
        safe_send_message(session.chat_id, "✅ All result files have been delivered.")
    except Exception as e:
        LOG.error(f"Background zipping failed: {e}")
        safe_send_message(session.chat_id, f"❌ Error: {e}")

def safe_send_message(chat_id, text, parse_mode=ParseMode.HTML, **kwargs):
    global app_instance, event_loop
    if not app_instance or not event_loop:
        return None
    coro = app_instance.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, **kwargs)
    fut = asyncio.run_coroutine_threadsafe(coro, event_loop)
    try:
        return fut.result(timeout=25)
    except Exception as e:
        LOG.error(f"send failed: {e}")
        return None

def safe_edit_message(chat_id, message_id, text):
    global app_instance, event_loop
    if not app_instance or not event_loop:
        return False
    coro = app_instance.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode=ParseMode.HTML)
    fut = asyncio.run_coroutine_threadsafe(coro, event_loop)
    try:
        fut.result(timeout=15)
        return True
    except Exception as e:
        LOG.debug(f"edit failed: {e}")
        return False

def safe_send_document(chat_id, document, filename, caption=""):
    global app_instance, event_loop
    if not app_instance or not event_loop:
        return
    coro = app_instance.bot.send_document(chat_id=chat_id, document=document, filename=filename, caption=caption)
    asyncio.run_coroutine_threadsafe(coro, event_loop)

def send_hit_to_user(chat_id, result):
    if not result.get('has_codm'):
        return
    acc = result.get('account','')
    pwd = result.get('password','')
    clean = result.get('is_clean', False)
    lvl = result.get('codm_level', 'N/A')
    region = result.get('codm_region', 'N/A')
    nick = result.get('codm_nickname', 'N/A')
    shell = result.get('shell_balance', 0)
    country = result.get('country', 'N/A')
    status = "✨ CLEAN" if clean else "⊘ NOT CLEAN"
    text = (f"🎯 <b>Account Hit</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📧 <code>{acc}:{pwd}</code>\n"
            f"📊 Status: {status}\n"
            f"🎮 CODM: Level {lvl}  |  {nick}\n"
            f"🌍 Region: {region}  |  Country: {country}\n"
            f"💰 Shells: {shell}\n"
            f"━━━━━━━━━━━━━━━━")
    safe_send_message(chat_id, text)

def send_final_summary(chat_id, ls: LiveStats, stopped: bool):
    stats = ls.snap()
    checked = stats['valid'] + stats['invalid'] + stats['error']
    total = stats.get('total', checked)
    elapsed = time.time() - stats['start_time']
    mins, secs = divmod(int(elapsed), 60)
    lines = [
        "🏁 <b>Checking Complete</b>" if not stopped else "🛑 <b>Checking Stopped</b>",
        "",
        f"📊 Processed: <code>{checked}/{total}</code>  ·  ⏱ {mins}m {secs}s",
        f"✅ Valid: <b>{stats['valid']}</b>  ❌ Invalid: <b>{stats['invalid']}</b>  ⚠️ Errors: <b>{stats['error']}</b>",
        f"✨ Clean: <b>{stats['clean']}</b>  ⊘ Not Clean: <b>{stats['not_clean']}</b>",
        f"🎮 Has CODM: <b>{stats['has_codm']}</b>  ○ No CODM: <b>{stats['no_codm']}</b>",
        f"🏆 Top Level: <b>{stats['highest_level']}</b>  💰 Top Shell: <b>{stats['highest_shell']}</b>",
        "",
        "📁 <i>Your result files are being zipped and sent in the background. They will appear shortly.</i>"
    ]
    safe_send_message(chat_id, "\n".join(lines))

def send_result_files(chat_id, rm: ResultsManager):
    base = rm.base
    if not base.exists():
        safe_send_message(chat_id, "ℹ️ No result files to send.")
        return
    zip_parts = zip_results_folder(base, base / "results.zip")
    if not zip_parts:
        safe_send_message(chat_id, "ℹ️ No result files to send.")
        return
    total = len(zip_parts)
    for idx, zp in enumerate(zip_parts, 1):
        caption = f"📦 Results part {idx}/{total}" if total > 1 else "📦 Your results"
        with open(zp, "rb") as f:
            safe_send_document(chat_id, f, zp.name, caption)
        try:
            zp.unlink()
        except:
            pass
    safe_send_message(chat_id, "✅ All result files have been delivered.")

def log_terminal(result):
    pass

def process_next():
    pass

# ──────────────────────────────────────────────────────────────────────────
#  CHECKER THREAD
# ──────────────────────────────────────────────────────────────────────────
def run_checker_thread(session: CheckerSession):
    try:
        accounts = []
        try:
            with open(session.combo_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    acc, pwd = clean_account_line(line)
                    if acc and pwd:
                        accounts.append((acc, pwd))
        except Exception as e:
            safe_send_message(session.chat_id, f"❌ Failed to read file: {e}")
            session.mark_finished()
            return
        if not accounts:
            safe_send_message(session.chat_id, "❌ No valid accounts found.")
            session.mark_finished()
            return
        state = session.state
        state.live_stats.total = len(accounts)
        tag = session.combo_stem
        user_id = session.user_id
        state.results_mgr = ResultsManager(tag=tag, user_id=user_id)
        class Item:
            pass
        item = Item()
        item.chat_id = session.chat_id
        item.combo_name = tag
        item.threads = session.threads
        run_check(item, accounts, state, send_hit_to_user, send_final_summary,
                  send_result_files, log_terminal, process_next)
        session.mark_finished()
    except Exception as e:
        LOG.error(f"Checker thread crashed: {e}", exc_info=True)
        safe_send_message(session.chat_id, f"❌ Error: {e}")
    finally:
        with session_lock:
            if session.user_id in active_sessions:
                del active_sessions[session.user_id]

# ──────────────────────────────────────────────────────────────────────────
#  LIVE STATS UPDATER
# ──────────────────────────────────────────────────────────────────────────
def live_stats_updater(session: CheckerSession):
    chat_id = session.chat_id
    try:
        text = build_live_text(session)
        msg_id = safe_send_message(chat_id, text)
        if msg_id:
            session.live_message_id = msg_id
    except Exception as e:
        LOG.error(f"initial live failed: {e}")
        return
    fail_count = 0
    last_proc = -1
    while session.is_running and not session.finished:
        time.sleep(LIVE_INTERVAL)
        if session.finished or not session.is_running:
            break
        try:
            text = build_live_text(session)
            stats = session.state.live_stats.snap()
            proc = stats['valid'] + stats['invalid'] + stats['error']
            if proc != last_proc:
                last_proc = proc
            if session.live_message_id:
                ok = safe_edit_message(chat_id, session.live_message_id, text)
                if not ok:
                    fail_count += 1
                    if fail_count >= 3:
                        new_id = safe_send_message(chat_id, text)
                        if new_id:
                            session.live_message_id = new_id
                            fail_count = 0
                else:
                    fail_count = 0
        except Exception as e:
            LOG.debug(f"live loop: {e}")

def build_live_text(session: CheckerSession) -> str:
    stats = session.state.live_stats.snap()
    checked = stats['valid'] + stats['invalid'] + stats['error']
    total = stats.get('total', 1)
    elapsed = time.time() - stats['start_time']
    rate = checked / elapsed if elapsed > 0 else 0
    rem = max(0, total - checked)
    eta = rem / rate if rate > 0 else 0
    eta_str = f"{int(eta//60)}m{int(eta%60)}s" if eta > 0 else "—"
    elapsed_str = f"{int(elapsed//60)}m{int(elapsed%60)}s"
    pct = (checked / total * 100) if total > 0 else 0
    bar_len = 20
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    lines = [
        f"⚡ <b>CODM Checker</b>  <code>#{session.user_id}</code>",
        f"`[{bar}] {pct:.1f}%`",
        f"📦 <code>{checked}/{total}</code>  ·  ⏱ {elapsed_str}  ·  🚀 {rate:.1f}/s  ·  ⏳ ETA {eta_str}",
        "",
        f"✅ Valid: <b>{stats['valid']}</b>  ❌ Invalid: <b>{stats['invalid']}</b>  ⚠️ Errors: <b>{stats['error']}</b>",
        f"✨ Clean: <b>{stats['clean']}</b>  ⊘ Not Clean: <b>{stats['not_clean']}</b>",
        f"🎮 Has CODM: <b>{stats['has_codm']}</b>  ○ No CODM: <b>{stats['no_codm']}</b>",
        f"🏆 Top Level: <b>{stats['highest_level']}</b>  💰 Top Shell: <b>{stats['highest_shell']}</b>",
    ]
    return "\n".join(lines)

# ──────────────────────────────────────────────────────────────────────────
#  TELEGRAM HANDLERS
# ──────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    referrer_code = args[0] if args else None
    ref_info = get_referral_info(user_id)
    if not ref_info:
        referrer_id = None
        if referrer_code:
            rows = db_query("SELECT user_id FROM referrals WHERE referral_code = ?", (referrer_code,))
            if rows and rows[0][0] != user_id:
                referrer_id = rows[0][0]
        create_referral(user_id, referrer_id)
        if referrer_id:
            db_execute("UPDATE referrals SET referral_count = referral_count + 1 WHERE user_id = ?", (referrer_id,))
            row = db_query("SELECT referral_count, reward_granted FROM referrals WHERE user_id = ?", (referrer_id,))
            if row and row[0][0] >= 5 and row[0][1] == 0:
                if grant_key_to_user(referrer_id, 1800, 0):
                    db_execute("UPDATE referrals SET reward_granted = 1 WHERE user_id = ?", (referrer_id,))
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text="🎉 You've referred 5 users! You received a **30‑minute free key**! Use /mykey.",
                        parse_mode=ParseMode.HTML
                    )
    await update.message.reply_text(
        "🤖 <b>CODM Checker Bot</b>\n\n"
        "Upload a <code>.txt</code> combo file (account:password per line).\n"
        "You need a license key. Use /key &lt;code&gt; to activate.\n\n"
        "Commands:\n"
        "/key &lt;code&gt; – activate your license\n"
        "/mykey – check your license status\n"
        "/referral – get your referral link and stats\n"
        "/check – upload a file (or just send it directly)\n"
        "/stop – stop the current check\n"
        "/status – see live progress\n\n"
        "Admin commands:\n"
        "/admin – open admin panel\n"
        "/genkey 7d – generate a key (suffix: m, h, d)\n"
        "/revokekey &lt;key&gt; – revoke a key\n"
        "/promote &lt;user_id&gt; – make admin\n"
        "/demote &lt;user_id&gt; – remove admin\n"
        "/broadcast – send a message to all users\n"
        "/stats – bot statistics",
        parse_mode=ParseMode.HTML
    )

async def cmd_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref = get_referral_info(user_id)
    if not ref:
        code = create_referral(user_id)
        count = 0
    else:
        code, _, count, _ = ref
    bot_username = context.bot.username
    link = f"https://t.me/{bot_username}?start={code}"
    await update.message.reply_text(
        f"🔗 <b>Your Referral Link</b>\n<code>{link}</code>\n\n"
        f"👥 Referrals: <b>{count}</b> / 5\n"
        f"🎯 When you reach 5, you get a <b>30‑minute free key</b>!",
        parse_mode=ParseMode.HTML
    )

async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Usage: /key &lt;XXXX-XXXX-XXXX-XXXX&gt;", parse_mode=ParseMode.HTML)
        return
    key = context.args[0].strip().upper().replace("-", "").replace(" ", "")
    if len(key) != 16:
        await update.message.reply_text("❌ Invalid key format.")
        return
    formatted = f"{key[:4]}-{key[4:8]}-{key[8:12]}-{key[12:]}"
    existing = db_query("SELECT expires_at FROM user_keys WHERE user_id = ?", (user_id,))
    if existing:
        expiry = datetime.fromisoformat(existing[0][0])
        if datetime.now(timezone.utc) < expiry:
            await update.message.reply_text("ℹ️ You already have an active key. Use /mykey.")
            return
    if activate_key(user_id, formatted):
        expiry = get_user_expiry(user_id)
        await update.message.reply_text(
            f"✅ <b>Key activated!</b>\n📅 Valid until: <code>{format_ph_time(expiry)}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("❌ Invalid, expired, or already used key.")

async def cmd_mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expiry = get_user_expiry(user_id)
    if not expiry:
        await update.message.reply_text("ℹ️ No active license. Use /key.")
        return
    now = datetime.now(timezone.utc)
    if expiry < now:
        await update.message.reply_text("⚠️ Your license has expired. Use /key.")
        return
    remaining = expiry - now
    hours, rem = divmod(remaining.total_seconds(), 3600)
    minutes = rem // 60
    await update.message.reply_text(
        f"🔑 <b>Your license</b>\n"
        f"🕒 Valid until: <code>{format_ph_time(expiry)}</code>\n"
        f"⏳ Remaining: <b>{int(hours)}h {int(minutes)}m</b>",
        parse_mode=ParseMode.HTML
    )

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 Please upload a <code>.txt</code> combo file.", parse_mode=ParseMode.HTML)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("❌ Please upload a <code>.txt</code> file.", parse_mode=ParseMode.HTML)
        return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not has_active_key(user_id):
        await update.message.reply_text("⚠️ No active license. Use /key.", parse_mode=ParseMode.HTML)
        return
    with session_lock:
        if user_id in active_sessions and active_sessions[user_id].is_running:
            await update.message.reply_text("⚠️ Already running. Use /stop first.")
            return
    await update.message.reply_text(f"📥 Downloading <code>{doc.file_name}</code>...", parse_mode=ParseMode.HTML)
    try:
        file = await context.bot.get_file(doc.file_id)
        tmp_dir = Path(f"temp/{user_id}")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        file_path = tmp_dir / doc.file_name
        await file.download_to_drive(file_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Download failed: {e}")
        return
    session = CheckerSession(user_id, chat_id, str(file_path), DEFAULT_THREADS)
    with session_lock:
        active_sessions[user_id] = session
    stats_thread = threading.Thread(target=live_stats_updater, args=(session,), daemon=True)
    stats_thread.start()
    check_thread = threading.Thread(target=run_checker_thread, args=(session,), daemon=True)
    check_thread.start()
    session.thread = check_thread
    await update.message.reply_text(
        f"✅ Check started with {DEFAULT_THREADS} threads.\nFile: <code>{doc.file_name}</code>",
        parse_mode=ParseMode.HTML
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with session_lock:
        session = active_sessions.get(user_id)
        if not session or not session.is_running:
            await update.message.reply_text("ℹ️ No active check.")
            return
        session.stop()
        await update.message.reply_text("🛑 Stop signal sent.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with session_lock:
        session = active_sessions.get(user_id)
        if not session or not session.is_running:
            await update.message.reply_text("ℹ️ No active check.")
            return
        text = build_live_text(session)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ──────────────────────────────────────────────────────────────────────────
#  ADMIN COMMANDS
# ──────────────────────────────────────────────────────────────────────────
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    keyboard = [
        [InlineKeyboardButton("🔑 Generate Key", callback_data="admin_genkey")],
        [InlineKeyboardButton("📋 List Keys", callback_data="admin_listkeys")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 <b>Admin Panel</b>", parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("⛔ Unauthorized.")
        return
    data = query.data
    if data == "admin_close":
        await query.edit_message_text("Panel closed.")
        return
    if data == "admin_genkey":
        await query.edit_message_text(
            "⏳ Use /genkey &lt;duration&gt;  (e.g. 1h, 7d, 3600)",
            parse_mode=ParseMode.HTML
        )
    elif data == "admin_listkeys":
        rows = db_query("SELECT key, created_at, used_by, is_revoked FROM keys ORDER BY created_at DESC LIMIT 20")
        if not rows:
            await query.edit_message_text("No keys found.")
            return
        lines = ["📋 <b>Last 20 keys</b>:\n"]
        for k, created, used, revoked in rows:
            status = "🔴 Revoked" if revoked else f"✅ Used by {used}" if used else "🟢 Unused"
            created_ph = format_ph_time(datetime.fromisoformat(created)) if created else "N/A"
            lines.append(f"<code>{k}</code> – {status} (created {created_ph})")
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)
    elif data == "admin_broadcast":
        context.user_data['broadcast_mode'] = True
        await query.edit_message_text(
            "📢 Send me the message to broadcast.\nType /cancel to abort.",
            parse_mode=ParseMode.HTML
        )
    elif data == "admin_stats":
        total_users = db_query("SELECT COUNT(*) FROM user_keys")[0][0]
        total_keys = db_query("SELECT COUNT(*) FROM keys")[0][0]
        active_checks = len([s for s in active_sessions.values() if s.is_running])
        text = (
            f"📊 <b>Bot Statistics</b>\n"
            f"👤 Users: {total_users}\n"
            f"🔑 Keys: {total_keys}\n"
            f"⚡ Active checks: {active_checks}"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

async def cmd_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /genkey &lt;duration&gt;  e.g. 30m, 2h, 7d", parse_mode=ParseMode.HTML)
        return
    try:
        seconds = parse_duration(context.args[0])
        if seconds <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Invalid duration.")
        return
    key = generate_key()
    db_execute("INSERT INTO keys (key, duration_seconds, created_by) VALUES (?, ?, ?)", (key, seconds, user_id))
    await update.message.reply_text(
        f"✅ Key generated:\n<code>{key}</code>\n⏳ {seconds//3600}h {(seconds%3600)//60}m",
        parse_mode=ParseMode.HTML
    )

async def cmd_revokekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /revokekey &lt;key&gt;", parse_mode=ParseMode.HTML)
        return
    key = context.args[0].strip().upper().replace("-", "").replace(" ", "")
    if len(key) != 16:
        await update.message.reply_text("❌ Invalid key format.")
        return
    formatted = f"{key[:4]}-{key[4:8]}-{key[8:12]}-{key[12:]}"
    db_execute("UPDATE keys SET is_revoked = 1 WHERE key = ?", (formatted,))
    await update.message.reply_text(f"✅ Key <code>{formatted}</code> revoked.", parse_mode=ParseMode.HTML)

async def cmd_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /promote &lt;user_id&gt;", parse_mode=ParseMode.HTML)
        return
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("❌ Invalid user_id.")
        return
    db_execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (target,))
    await update.message.reply_text(f"✅ User {target} is now an admin.")

async def cmd_demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /demote &lt;user_id&gt;", parse_mode=ParseMode.HTML)
        return
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("❌ Invalid user_id.")
        return
    if target == 8621676055:
        await update.message.reply_text("❌ Cannot demote primary admin.")
        return
    db_execute("DELETE FROM admins WHERE user_id = ?", (target,))
    await update.message.reply_text(f"✅ User {target} is no longer an admin.")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    context.user_data['broadcast_mode'] = True
    await update.message.reply_text("📢 Send the message to broadcast.\nType /cancel to abort.")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    total_users = db_query("SELECT COUNT(*) FROM user_keys")[0][0]
    total_keys = db_query("SELECT COUNT(*) FROM keys")[0][0]
    active_checks = len([s for s in active_sessions.values() if s.is_running])
    text = (
        f"📊 <b>Bot Statistics</b>\n"
        f"👤 Users: {total_users}\n"
        f"🔑 Keys: {total_keys}\n"
        f"⚡ Active checks: {active_checks}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('broadcast_mode'):
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    text = update.message.text
    if text == "/cancel":
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("Broadcast cancelled.")
        return
    rows = db_query("SELECT DISTINCT user_id FROM user_keys")
    total = len(rows)
    if total == 0:
        await update.message.reply_text("No users.")
        context.user_data['broadcast_mode'] = False
        return
    await update.message.reply_text(f"📢 Broadcasting to {total} users...")
    sent = 0
    for (uid,) in rows:
        try:
            await context.bot.send_message(uid, f"📢 <b>Broadcast from admin</b>\n\n{text}", parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.1)
        except:
            pass
    context.user_data['broadcast_mode'] = False
    await update.message.reply_text(f"✅ Broadcast sent to {sent}/{total} users.")

# ──────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────
def main():
    global app_instance, event_loop
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    request = HTTPXRequest(connection_pool_size=16, connect_timeout=30.0, read_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    app_instance = app

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("referral", cmd_referral))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("key", cmd_key))
    app.add_handler(CommandHandler("mykey", cmd_mykey))

    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("genkey", cmd_genkey))
    app.add_handler(CommandHandler("revokekey", cmd_revokekey))
    app.add_handler(CommandHandler("promote", cmd_promote))
    app.add_handler(CommandHandler("demote", cmd_demote))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("stats", cmd_stats))

    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message))

    LOG.info("Bot starting in polling mode.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()