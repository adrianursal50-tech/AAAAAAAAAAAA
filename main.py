#!/usr/bin/env python3
"""
CODM Checker Telegram Bot – Full production version
- Custom proxy loader for user:pass:host:port format
- License key system (SQLite)
- Admin panel with /genkey, /revokekey, /promote, /broadcast, /stats
- Instant final summary (results zipped & sent in background)
- Incremental database flushing for speed
- Fixed HTML escaping for all literal angle brackets
"""

import os
import sys
import time
import json
import zipfile
import logging
import threading
import asyncio
import tempfile
import requests
import sqlite3
import random
import string
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from queue import Queue, Empty

from telegram import Update, Document, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError

# ── Import from titacod.py ──────────────────────────────────────────────────
try:
    from titacod import (
        processaccount,
        LiveStats,
        ResultsManager,
        CookieManager,
        DataDomeManager,
        # We'll replace the original ProxyManager with our custom one
        clean_account_line,
        get_game_connections,
        save_game_folder,
        CODM_REGIONS,
        GAME_FILE_MAP,
        CHECK_OTHER_GAMES,
        sanitize_string,
        format_mobile_number,
        format_codm_region,
        applyck,
        get_datadome_cookie,
        init_ga_cookies,
    )
except ImportError:
    print("Error: titacod.py not found. Please place this bot in the same folder.")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
#  CUSTOM PROXY MANAGER (supports user:pass:host:port)
# ──────────────────────────────────────────────────────────────────────────────
class CustomProxyManager:
    """Loads proxies from proxies.txt with format: user:pass:host:port
       Returns a requests-compatible proxy dict.
    """
    def __init__(self, filename="proxies.txt"):
        self.proxies = []
        self.index = 0
        self.loaded = False
        self._load(filename)

    def _load(self, filename):
        try:
            with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # Expected format: user:pass:host:port
                    parts = line.split(":")
                    if len(parts) == 4:
                        user, pwd, host, port = parts
                        # Build proxy URL
                        proxy_url = f"http://{user}:{pwd}@{host}:{port}"
                        # For requests, we need both http and https
                        proxy_dict = {
                            "http": proxy_url,
                            "https": proxy_url
                        }
                        self.proxies.append(proxy_dict)
                    else:
                        # Fallback: treat as host:port (no auth)
                        if len(parts) == 2:
                            host, port = parts
                            proxy_url = f"http://{host}:{port}"
                            proxy_dict = {
                                "http": proxy_url,
                                "https": proxy_url
                            }
                            self.proxies.append(proxy_dict)
                        else:
                            logging.warning(f"Skipping invalid proxy line: {line}")
            if self.proxies:
                self.loaded = True
                logging.info(f"Loaded {len(self.proxies)} proxies.")
            else:
                logging.warning("No valid proxies found in proxies.txt")
        except FileNotFoundError:
            logging.info("proxies.txt not found – running without proxies.")
            self.loaded = False

    def is_loaded(self):
        return self.loaded and len(self.proxies) > 0

    def get_next(self):
        """Return next proxy dict in round-robin fashion."""
        if not self.is_loaded():
            return None
        proxy = self.proxies[self.index % len(self.proxies)]
        self.index += 1
        return proxy

# ──────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = "8597114754:AAH3nvgyXWg1KpQq1_Qn2Lva2J0yozUJxGc"  # Replace with your token
    print("[WARNING] Using hardcoded token. Set BOT_TOKEN env var to override.")

DEFAULT_THREADS = 5
LIVE_INTERVAL = 3.0
TG_MAX_BYTES = 49 * 1024 * 1024   # 49 MB
DB_PATH = Path("bot_data.db")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
LOG = logging.getLogger("codm_bot")

# ──────────────────────────────────────────────────────────────────────────────
#  DATABASE (SQLite) – thread‑safe with check_same_thread=False
# ──────────────────────────────────────────────────────────────────────────────
db_conn = None

def init_db():
    global db_conn
    db_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db_conn.execute("PRAGMA journal_mode=WAL")
    db_conn.execute("""
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
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS user_keys (
            user_id INTEGER PRIMARY KEY,
            key TEXT NOT NULL,
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (key) REFERENCES keys(key)
        )
    """)
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    """)
    db_conn.commit()

    # Auto-promote primary admin if no admins exist
    cur = db_conn.execute("SELECT COUNT(*) FROM admins")
    if cur.fetchone()[0] == 0:
        db_conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (8621676055,))
        db_conn.commit()
        LOG.info("Primary admin 8621676055 added.")

def db_query(query, params=()):
    with db_conn:  # auto-commit
        return db_conn.execute(query, params).fetchall()

def db_execute(query, params=()):
    with db_conn:
        db_conn.execute(query, params)

# ──────────────────────────────────────────────────────────────────────────────
#  KEY HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def generate_key() -> str:
    chars = string.ascii_uppercase + string.digits
    raw = ''.join(random.choices(chars, k=16))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:]}"

def parse_duration(text: str) -> int:
    """Convert 1h, 7d, 30m, 3600 -> seconds."""
    text = text.strip().lower()
    if text.endswith('d'):
        return int(text[:-1]) * 86400
    if text.endswith('h'):
        return int(text[:-1]) * 3600
    if text.endswith('m'):
        return int(text[:-1]) * 60
    return int(text)

def is_admin(user_id: int) -> bool:
    res = db_query("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    return len(res) > 0

def is_key_valid(key: str) -> Tuple[bool, Optional[int]]:
    """Returns (is_valid, duration_seconds). Checks revoked and used_by."""
    rows = db_query("SELECT duration_seconds, used_by, is_revoked FROM keys WHERE key = ?", (key,))
    if not rows:
        return False, None
    dur, used_by, revoked = rows[0]
    if revoked:
        return False, None
    if used_by is not None:
        return False, None
    return True, dur

def get_user_expiry(user_id: int) -> Optional[datetime]:
    rows = db_query("SELECT expires_at FROM user_keys WHERE user_id = ?", (user_id,))
    if not rows:
        return None
    return datetime.fromisoformat(rows[0][0])

def has_active_key(user_id: int) -> bool:
    expiry = get_user_expiry(user_id)
    if expiry is None:
        return False
    return datetime.now(timezone.utc) < expiry

def activate_key(user_id: int, key: str) -> bool:
    """Assign key to user, set expiry, mark key as used."""
    valid, dur = is_key_valid(key)
    if not valid:
        return False
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=dur)
    db_execute(
        "INSERT OR REPLACE INTO user_keys (user_id, key, activated_at, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, key, now.isoformat(), expires.isoformat())
    )
    db_execute("UPDATE keys SET used_by = ?, used_at = ? WHERE key = ?", (user_id, now.isoformat(), key))
    return True

# ──────────────────────────────────────────────────────────────────────────────
#  SESSION MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class CheckerSession:
    def __init__(self, user_id: int, chat_id: int, combo_file: str, threads: int):
        self.user_id = user_id
        self.chat_id = chat_id
        self.combo_file = combo_file
        self.threads = threads
        self.stop_event = threading.Event()
        self.live_stats = LiveStats()
        self.results_mgr = None
        self.cookie_mgr = CookieManager()
        self.datadome_mgr = DataDomeManager()
        # Use our custom proxy manager instead of the original
        self.proxy_mgr = CustomProxyManager("proxies.txt")
        self.thread = None
        self.live_message_id = None
        self.finished = False
        self.accounts_processed = 0
        self.total_accounts = 0
        self.is_running = True
        self.combo_stem = Path(combo_file).stem
        self.base_dir = None
        self.zip_ready = threading.Event()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.is_running = False

    def should_stop(self):
        return self.stop_event.is_set()

    def mark_finished(self):
        self.is_running = False
        self.finished = True

    def get_stats(self) -> dict:
        return self.live_stats.get_stats()

    def get_progress(self) -> float:
        stats = self.get_stats()
        checked = stats.get('checked', 0)
        total = stats.get('total', 1)
        return (checked / total * 100) if total > 0 else 0

# ──────────────────────────────────────────────────────────────────────────────
#  GLOBALS
# ──────────────────────────────────────────────────────────────────────────────

active_sessions: Dict[int, CheckerSession] = {}
session_lock = threading.Lock()
app_instance = None
event_loop = None

# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS: ZIP + SEND (BACKGROUND)
# ──────────────────────────────────────────────────────────────────────────────

def zip_results_folder(folder: Path, out: Path) -> List[Path]:
    """Zip all result files. Returns list of paths (split if > 49 MB)."""
    files = sorted([f for f in folder.rglob("*") if f.is_file() and f != out and not f.name.endswith(".zip")])
    if not files:
        return []
    # Try single zip first
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(folder))
    if out.stat().st_size <= TG_MAX_BYTES:
        return [out]
    # Too big – split
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
    """Background thread: zip and send results, then clean up."""
    try:
        rm = session.results_mgr
        if not rm or not rm.base_dir.exists():
            return
        zip_parts = zip_results_folder(rm.base_dir, rm.base_dir / "results.zip")
        if zip_parts:
            total_parts = len(zip_parts)
            for idx, zp in enumerate(zip_parts, 1):
                caption = f"📦 Results part {idx}/{total_parts}" if total_parts > 1 else "📦 Your results"
                with open(zp, "rb") as f:
                    safe_send_document(session.chat_id, f, zp.name, caption)
                try:
                    zp.unlink()
                except:
                    pass
        safe_send_message(session.chat_id, "✅ All result files have been delivered.")
    except Exception as e:
        LOG.error(f"Background zipping failed: {e}")
        safe_send_message(session.chat_id, f"❌ Error while zipping/sending results: {e}")
    finally:
        session.zip_ready.set()

def safe_send_message(chat_id: int, text: str, parse_mode=ParseMode.HTML, **kwargs):
    global app_instance, event_loop
    if not app_instance or not event_loop:
        return None
    coro = app_instance.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, **kwargs)
    fut = asyncio.run_coroutine_threadsafe(coro, event_loop)
    try:
        msg = fut.result(timeout=25)
        return msg.message_id
    except Exception as e:
        LOG.error(f"send failed: {e}")
        return None

def safe_edit_message(chat_id: int, message_id: int, text: str):
    global app_instance, event_loop
    if not app_instance or not event_loop:
        return False
    coro = app_instance.bot.edit_message_text(
        chat_id=chat_id, message_id=message_id, text=text, parse_mode=ParseMode.HTML
    )
    fut = asyncio.run_coroutine_threadsafe(coro, event_loop)
    try:
        fut.result(timeout=15)
        return True
    except Exception as e:
        LOG.debug(f"edit failed: {e}")
        return False

def safe_send_document(chat_id: int, document, filename: str, caption: str = ""):
    global app_instance, event_loop
    if not app_instance or not event_loop:
        return
    coro = app_instance.bot.send_document(chat_id=chat_id, document=document, filename=filename, caption=caption)
    asyncio.run_coroutine_threadsafe(coro, event_loop)

# ──────────────────────────────────────────────────────────────────────────────
#  CHECKER THREAD
# ──────────────────────────────────────────────────────────────────────────────

def run_checker_thread(session: CheckerSession):
    """Main checker thread – processes all accounts, flushes DB incrementally."""
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

        session.total_accounts = len(accounts)
        session.live_stats.total_accounts = len(accounts)

        # Results manager
        combo_stem = session.combo_stem
        base_dir = Path(f"Results/user_{session.user_id}/{combo_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(base_dir, exist_ok=True)
        session.base_dir = base_dir
        session.results_mgr = ResultsManager(combo_stem)
        session.results_mgr.base_dir = base_dir
        for sub in ('Country', 'Level', 'Games', 'Garena Shells'):
            (base_dir / sub).mkdir(parents=True, exist_ok=True)

        cm = session.cookie_mgr
        dm = session.datadome_mgr
        pm = session.proxy_mgr   # custom proxy manager
        ls = session.live_stats
        rm = session.results_mgr
        stop_ev = session.stop_event

        _thread_local = threading.local()

        def get_thread_resources():
            if not hasattr(_thread_local, 'session'):
                _thread_local.session = requests.Session()
                _thread_local.datadome = DataDomeManager()
                # Apply proxy from our custom manager
                if pm and pm.is_loaded():
                    proxy = pm.get_next()
                    if proxy:
                        _thread_local.session.proxies.update(proxy)
                # Cookies and datadome setup (unchanged)
                valid_cookies = cm.get_valid_cookies()
                if valid_cookies:
                    combined = '; '.join(valid_cookies)
                    applyck(_thread_local.session, combined)
                    for ck in valid_cookies:
                        if 'datadome=' in ck:
                            val = ck.split('datadome=')[1].split(';')[0].strip()
                            _thread_local.datadome.set_datadome(val)
                            break
                else:
                    proxy_dict = dict(_thread_local.session.proxies) if _thread_local.session.proxies else None
                    dd = get_datadome_cookie(_thread_local.session, proxies=proxy_dict)
                    if dd:
                        _thread_local.datadome.set_datadome(dd)
                        _thread_local.session.cookies.set('datadome', dd, domain='.garena.com')
                        cm.save_cookie(dd)
                init_ga_cookies(_thread_local.session)
                if _thread_local.datadome.get_datadome():
                    _thread_local.datadome.set_session_datadome(_thread_local.session)
            return _thread_local.session, _thread_local.datadome

        import concurrent.futures

        def worker(acc: str, pwd: str):
            if stop_ev.is_set():
                return None, None
            try:
                sess, datadome = get_thread_resources()
                if datadome.get_datadome():
                    datadome.set_session_datadome(sess)
                # processaccount expects a proxy manager – we pass our custom one
                # but it might call get_next() internally – we'll let it use our pm
                status, account_data = processaccount(
                    sess, acc, pwd,
                    cm, datadome, ls, rm,
                    None, None, False, False, True, pm
                )
                return status, account_data
            except Exception as e:
                LOG.error(f"Worker error for {acc}: {e}", exc_info=True)
                return None, None

        processed = 0
        BATCH_SIZE = 50
        with concurrent.futures.ThreadPoolExecutor(max_workers=session.threads) as executor:
            futures = {executor.submit(worker, acc, pwd): (acc, pwd) for acc, pwd in accounts}
            for future in concurrent.futures.as_completed(futures):
                if stop_ev.is_set():
                    for f in futures:
                        f.cancel()
                    break
                try:
                    status, account_data = future.result(timeout=60)
                    if status:
                        processed += 1
                        if processed % BATCH_SIZE == 0:
                            rm.db_flush_final()
                        LOG.info(f"Processed {processed}/{len(accounts)}: {status}")
                except Exception as e:
                    LOG.error(f"Future error: {e}")

        rm.db_flush_final()
        session.mark_finished()

        final_text = build_final_summary(session)
        safe_send_message(session.chat_id, final_text)

        zip_thread = threading.Thread(target=send_results_background, args=(session,), daemon=True)
        zip_thread.start()

        try:
            Path(session.combo_file).unlink()
        except:
            pass

    except Exception as e:
        LOG.error(f"Checker thread crashed: {e}", exc_info=True)
        safe_send_message(session.chat_id, f"❌ Error: {e}")
    finally:
        with session_lock:
            if session.user_id in active_sessions:
                del active_sessions[session.user_id]

# ──────────────────────────────────────────────────────────────────────────────
#  LIVE STATS UPDATER
# ──────────────────────────────────────────────────────────────────────────────

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
            proc = session.live_stats.get_processed_count()
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

# ──────────────────────────────────────────────────────────────────────────────
#  TEXT BUILDERS
# ──────────────────────────────────────────────────────────────────────────────

def build_live_text(session: CheckerSession) -> str:
    stats = session.get_stats()
    checked = stats.get('checked', 0)
    total = stats.get('total', 1)
    elapsed = stats.get('elapsed', 0)
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
        f"✅ Valid: <b>{stats.get('valid',0)}</b>  ❌ Invalid: <b>{stats.get('invalid',0)}</b>  ⚠️ Errors: <b>{stats.get('error',0)}</b>",
        f"✨ Clean: <b>{stats.get('clean',0)}</b>  ⊘ Not Clean: <b>{stats.get('not_clean',0)}</b>",
        f"🎮 Has CODM: <b>{stats.get('has_codm',0)}</b>  ○ No CODM: <b>{stats.get('no_codm',0)}</b>",
        f"🏆 Top Level: <b>{stats.get('high_lvl',0)}</b>  💰 Top Shell: <b>{stats.get('high_shell',0)}</b>",
    ]
    return "\n".join(lines)

def build_final_summary(session: CheckerSession) -> str:
    stats = session.get_stats()
    checked = stats.get('checked', 0)
    total = stats.get('total', 1)
    elapsed = stats.get('elapsed', 0)
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    lines = [
        "🏁 <b>Checking Complete</b>" if session.finished else "🛑 <b>Checking Stopped</b>",
        "",
        f"📊 Processed: <code>{checked}/{total}</code>  ·  ⏱ {mins}m {secs}s",
        f"✅ Valid: <b>{stats.get('valid',0)}</b>  ❌ Invalid: <b>{stats.get('invalid',0)}</b>  ⚠️ Errors: <b>{stats.get('error',0)}</b>",
        f"✨ Clean: <b>{stats.get('clean',0)}</b>  ⊘ Not Clean: <b>{stats.get('not_clean',0)}</b>",
        f"🎮 Has CODM: <b>{stats.get('has_codm',0)}</b>  ○ No CODM: <b>{stats.get('no_codm',0)}</b>",
        f"🏆 Top Level: <b>{stats.get('high_lvl',0)}</b>  💰 Top Shell: <b>{stats.get('high_shell',0)}</b>",
        "",
        "📁 <i>Your result files are being zipped and sent in the background. They will appear shortly.</i>",
    ]
    return "\n".join(lines)

# ──────────────────────────────────────────────────────────────────────────────
#  TELEGRAM HANDLERS
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>CODM Checker Bot</b>\n\n"
        "Upload a <code>.txt</code> combo file (account:password per line).\n"
        "You need a valid license key. Use /key &lt;code&gt; to activate.\n\n"
        "Commands:\n"
        "/key &lt;code&gt; – activate your license\n"
        "/mykey – check your license status\n"
        "/check – upload a file (or just send it directly)\n"
        "/stop – stop the current check\n"
        "/status – see live progress\n\n"
        "Admin commands (if you have privileges):\n"
        "/admin – open admin panel\n"
        "/genkey 7d – generate a key (suffix: m, h, d)\n"
        "/revokekey &lt;key&gt; – revoke a key\n"
        "/promote &lt;user_id&gt; – make admin\n"
        "/demote &lt;user_id&gt; – remove admin\n"
        "/broadcast – send a message to all users\n"
        "/stats – bot statistics",
        parse_mode=ParseMode.HTML
    )

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Please upload a <code>.txt</code> combo file.\n"
        "I'll start checking immediately if your license is active.",
        parse_mode=ParseMode.HTML
    )

async def cmd_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ Usage: /key &lt;XXXX-XXXX-XXXX-XXXX&gt;", parse_mode=ParseMode.HTML)
        return
    key = context.args[0].strip().upper()
    key = key.replace(" ", "").replace("-", "")
    if len(key) != 16:
        await update.message.reply_text("❌ Invalid key format. Must be 16 alphanumeric characters.")
        return
    formatted = f"{key[:4]}-{key[4:8]}-{key[8:12]}-{key[12:]}"

    existing = db_query("SELECT expires_at FROM user_keys WHERE user_id = ?", (user_id,))
    if existing:
        expiry = datetime.fromisoformat(existing[0][0])
        if datetime.now(timezone.utc) < expiry:
            await update.message.reply_text("ℹ️ You already have an active key. Use /mykey to check expiry.")
            return

    if activate_key(user_id, formatted):
        expiry = get_user_expiry(user_id)
        await update.message.reply_text(
            f"✅ <b>Key activated successfully!</b>\n"
            f"📅 Valid until: <code>{expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("❌ Invalid, expired, or already used key. Please check and try again.")

async def cmd_mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expiry = get_user_expiry(user_id)
    if not expiry:
        await update.message.reply_text("ℹ️ You don't have an active license. Use /key &lt;code&gt; to activate.", parse_mode=ParseMode.HTML)
        return
    now = datetime.now(timezone.utc)
    if expiry < now:
        await update.message.reply_text("⚠️ Your license has expired. Use /key &lt;code&gt; to get a new one.", parse_mode=ParseMode.HTML)
        return
    remaining = expiry - now
    hours, rem = divmod(remaining.total_seconds(), 3600)
    minutes = rem // 60
    await update.message.reply_text(
        f"🔑 <b>Your license</b>\n"
        f"🕒 Valid until: <code>{expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}</code>\n"
        f"⏳ Remaining: <b>{int(hours)}h {int(minutes)}m</b>",
        parse_mode=ParseMode.HTML
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("❌ Please upload a <code>.txt</code> file.", parse_mode=ParseMode.HTML)
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not has_active_key(user_id):
        await update.message.reply_text(
            "⚠️ <b>No active license found.</b>\n"
            "Please use /key &lt;code&gt; to activate your license.\n"
            "Contact @admin if you need to purchase one.",
            parse_mode=ParseMode.HTML
        )
        return

    with session_lock:
        if user_id in active_sessions and active_sessions[user_id].is_running:
            await update.message.reply_text("⚠️ You already have a check running. Use /stop first.")
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

    threads = DEFAULT_THREADS

    session = CheckerSession(user_id, chat_id, str(file_path), threads)
    with session_lock:
        active_sessions[user_id] = session

    stats_thread = threading.Thread(target=live_stats_updater, args=(session,), daemon=True)
    stats_thread.start()

    check_thread = threading.Thread(target=run_checker_thread, args=(session,), daemon=True)
    check_thread.start()
    session.thread = check_thread

    await update.message.reply_text(
        f"✅ Check started with {threads} threads.\n"
        f"File: <code>{doc.file_name}</code>\n"
        f"Live stats will appear shortly.",
        parse_mode=ParseMode.HTML
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with session_lock:
        session = active_sessions.get(user_id)
        if not session or not session.is_running:
            await update.message.reply_text("ℹ️ No active check to stop.")
            return
        session.stop()
        await update.message.reply_text("🛑 Stop signal sent. Final summary will be sent.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with session_lock:
        session = active_sessions.get(user_id)
        if not session or not session.is_running:
            await update.message.reply_text("ℹ️ No active check.")
            return
        text = build_live_text(session)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ──────────────────────────────────────────────────────────────────────────────
#  ADMIN COMMANDS
# ──────────────────────────────────────────────────────────────────────────────

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
            "⏳ <b>Generate Key</b>\n"
            "Use command: /genkey &lt;duration&gt;\n"
            "Examples: /genkey 1h, /genkey 7d, /genkey 3600",
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
            lines.append(f"<code>{k}</code> – {status} (created {created[:10]})")
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)

    elif data == "admin_broadcast":
        context.user_data['broadcast_mode'] = True
        await query.edit_message_text(
            "📢 <b>Broadcast Mode</b>\n"
            "Send me the message you want to broadcast to all users.\n"
            "Type /cancel to abort.",
            parse_mode=ParseMode.HTML
        )

    elif data == "admin_stats":
        total_users = db_query("SELECT COUNT(*) FROM user_keys")[0][0]
        total_keys = db_query("SELECT COUNT(*) FROM keys")[0][0]
        active_checks = len([s for s in active_sessions.values() if s.is_running])
        text = (
            f"📊 <b>Bot Statistics</b>\n"
            f"👤 Registered users: {total_users}\n"
            f"🔑 Total keys generated: {total_keys}\n"
            f"⚡ Active checks: {active_checks}\n"
            f"🗄️ Database: {DB_PATH.stat().st_size // 1024} KB"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

async def cmd_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /genkey &lt;duration&gt;\nExamples: /genkey 1h, /genkey 7d, /genkey 3600", parse_mode=ParseMode.HTML)
        return
    try:
        seconds = parse_duration(context.args[0])
        if seconds <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Invalid duration. Use e.g. 30m, 2h, 7d, or seconds.")
        return

    key = generate_key()
    db_execute(
        "INSERT INTO keys (key, duration_seconds, created_by) VALUES (?, ?, ?)",
        (key, seconds, user_id)
    )
    await update.message.reply_text(
        f"✅ <b>Key generated</b>\n"
        f"🔑 <code>{key}</code>\n"
        f"⏳ Duration: {seconds // 3600}h { (seconds % 3600) // 60}m\n"
        f"👤 Created by: {user_id}",
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
    key = context.args[0].strip().upper().replace("-", "")
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
        await update.message.reply_text("❌ Cannot demote the primary admin.")
        return
    db_execute("DELETE FROM admins WHERE user_id = ?", (target,))
    await update.message.reply_text(f"✅ User {target} is no longer an admin.")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    context.user_data['broadcast_mode'] = True
    await update.message.reply_text(
        "📢 Send me the message you want to broadcast.\nType /cancel to abort."
    )

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
        f"👤 Registered users: {total_users}\n"
        f"🔑 Total keys generated: {total_keys}\n"
        f"⚡ Active checks: {active_checks}\n"
        f"🗄️ Database: {DB_PATH.stat().st_size // 1024} KB"
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
        await update.message.reply_text("No users to broadcast to.")
        context.user_data['broadcast_mode'] = False
        return

    await update.message.reply_text(f"📢 Broadcasting to {total} users... This may take a while.")
    sent = 0
    for (uid,) in rows:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 <b>Broadcast from admin</b>\n\n{text}", parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.1)
        except:
            pass
    context.user_data['broadcast_mode'] = False
    await update.message.reply_text(f"✅ Broadcast sent to {sent}/{total} users.")

# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    global app_instance, event_loop

    init_db()

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    request = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=30.0,
        pool_timeout=10.0,
    )

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .get_updates_request(request)
        .build()
    )
    app_instance = app

    app.add_handler(CommandHandler("start", cmd_start))
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

    LOG.info("Bot started with custom proxy support (user:pass:host:port). Send /start to begin.")
    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        LOG.info("Stopped.")
    finally:
        if db_conn:
            db_conn.close()

if __name__ == "__main__":
    main()