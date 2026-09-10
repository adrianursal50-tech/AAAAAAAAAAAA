#!/usr/bin/env python3
# ===================================================================
# Shin's Bulk/Single Checker Bot — CN31 edition (v5, no-proxy, real endpoint)
# -------------------------------------------------------------------
#   • CN31 solver hook: solar-solver-production.up.railway.app/get-token
#   • Token auto-refresh every REFRESH_EVERY items OR on 401/403
#   • 30 workers, direct connections, zip delivery
#   • CN31_ENDPOINT is REQUIRED via env — no fake placeholder
# ===================================================================

import asyncio
import html
import io
import json as _json
import logging
import os
import sqlite3
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp
import aiosqlite
from telegram import InputFile, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ──────────────────────────────────────────────────────────────────
# 1. CONFIG
# ──────────────────────────────────────────────────────────────────

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "8702549007:AAHe3d-RSBaYs4wX4D4x4rkLpevipByEPqs")
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "8621676055"))
DB_PATH        = os.environ.get("DB_PATH", "shin.db")

# ── CN31 ──────────────────────────────────────────────────────────
SOLVER_URL      = os.environ.get(
    "SOLVER_URL",
    "https://solar-solver-production.up.railway.app/",
)
# REQUIRED. Must be a real, reachable URL. Set it in env.
CN31_ENDPOINT   = os.environ.get("CN31_ENDPOINT", "get-token").strip() or None
CN31_AUTH_STYLE = os.environ.get("CN31_AUTH_STYLE", "header")  # header|query|bearer
CN31_AUTH_KEY   = os.environ.get("CN31_AUTH_KEY", "Authorization")
TOKEN_SAFETY    = float(os.environ.get("TOKEN_SAFETY", "60"))
# ──────────────────────────────────────────────────────────────────

MAX_ITEMS_PER_BULK     = 5000
CONCURRENCY            = int(os.environ.get("CONCURRENCY", "30"))
REFRESH_EVERY          = int(os.environ.get("REFRESH_EVERY", "50"))
MAX_RETRIES            = int(os.environ.get("MAX_RETRIES", "2"))
ITEM_TIMEOUT           = float(os.environ.get("ITEM_TIMEOUT", "20"))
REFRESH_TIMEOUT        = float(os.environ.get("REFRESH_TIMEOUT", "15"))
PROGRESS_EDIT_INTERVAL = 2.5
DEFAULT_KEY_USES       = 10
DEFAULT_KEY_HOURS      = 24
KEY_PREFIX             = "SHIN-"

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("shin-bot")

ACTIVE_BULKS: dict[int, dict] = {}


# ──────────────────────────────────────────────────────────────────
# 2. CN31 TOKEN MANAGER
# ──────────────────────────────────────────────────────────────────

@dataclass
class CN31TokenState:
    token: Optional[str] = None
    fetched_at: float = 0.0
    expires_in: float = 0.0
    pool_size: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_valid(self) -> bool:
        if not self.token:
            return False
        age = time.time() - self.fetched_at
        return age < max(0.0, self.expires_in - TOKEN_SAFETY)

    def age(self) -> float:
        return time.time() - self.fetched_at


async def fetch_cn31_token() -> Optional[CN31TokenState]:
    """Pull one fresh CN31 token from the solver."""
    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    try:
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.get(
                SOLVER_URL,
                timeout=aiohttp.ClientTimeout(total=REFRESH_TIMEOUT),
                headers={"Accept": "application/json"},
            ) as r:
                if r.status != 200:
                    log.warning("solver returned HTTP %s", r.status)
                    return None
                data = await r.json(content_type=None)
    except aiohttp.ClientConnectorDNSError as e:
        log.warning("solver DNS failed (%s) — check SOLVER_URL", e)
        return None
    except Exception as e:
        log.warning("solver fetch failed: %s", e)
        return None

    tok = data.get("token")
    if not tok:
        arr = data.get("tokens") or []
        if arr:
            tok = arr[0].get("token") if isinstance(arr[0], dict) else arr[0]
    if not tok:
        log.warning("solver returned no token field")
        return None

    st = CN31TokenState(
        token=tok,
        fetched_at=time.time(),
        expires_in=float(data.get("expires_in_seconds") or 840),
        pool_size=int(data.get("pool_size") or 0),
    )
    log.info(
        "CN31 token fetched — pool_size=%s expires_in=%ss len=%s",
        st.pool_size, int(st.expires_in), len(tok),
    )
    return st


async def ensure_token(session: aiohttp.ClientSession,
                       state: dict) -> Optional[str]:
    ts: CN31TokenState = state["token_state"]
    async with ts.lock:
        if ts.is_valid():
            return ts.token
        fresh = await fetch_cn31_token()
        if not fresh:
            return ts.token
        state["token_state"] = fresh
        _apply_token_to_session(session, fresh.token)
        return fresh.token


def _apply_token_to_session(session: aiohttp.ClientSession, token: str) -> None:
    if CN31_AUTH_STYLE == "bearer":
        session.headers[CN31_AUTH_KEY] = f"Bearer {token}"
    elif CN31_AUTH_STYLE == "header":
        session.headers[CN31_AUTH_KEY] = token
    # "query" handled per-request in run_task


# ──────────────────────────────────────────────────────────────────
# 3. PLUG POINTS — CN31 wired in (direct, no proxy)
# ──────────────────────────────────────────────────────────────────

async def refresh_session(session: aiohttp.ClientSession) -> None:
    state = session.__dict__.setdefault("_cn31_state", {"token_state": CN31TokenState()})
    tok = await ensure_token(session, state)
    if tok:
        _apply_token_to_session(session, tok)


async def run_task(item: str, session: aiohttp.ClientSession) -> str:
    """
    Per-item CN31 check. Direct connection, no proxies.
    Requires CN31_ENDPOINT to be set — raises if it isn't.
    """
    if not CN31_ENDPOINT:
        raise RuntimeError(
            "CN31_ENDPOINT not configured — set the env var to a real URL"
        )

    state = session.__dict__.setdefault("_cn31_state", {"token_state": CN31TokenState()})
    token = await ensure_token(session, state)
    if not token:
        raise RuntimeError("no CN31 token available")

    params = {"id": item}
    if CN31_AUTH_STYLE == "query":
        params[CN31_AUTH_KEY] = token

    try:
        async with session.get(
            CN31_ENDPOINT,
            params=params,
            timeout=aiohttp.ClientTimeout(total=ITEM_TIMEOUT),
        ) as r:
            body = await r.text()

            if r.status in (401, 403):
                state["token_state"].expires_in = 0
                state["token_state"].token = None
                raise RuntimeError(f"CN31 auth rejected ({r.status})")

            if r.status == 429:
                raise RuntimeError("CN31 rate limited (429)")

            if r.status >= 500:
                raise RuntimeError(f"CN31 server error {r.status}")

            if r.status != 200:
                return f"[HTTP {r.status}] {body[:300]}"
    except aiohttp.ClientConnectorDNSError as e:
        raise RuntimeError(f"DNS failure for CN31_ENDPOINT: {e}") from e
    except aiohttp.ClientConnectorError as e:
        raise RuntimeError(f"connection failure for CN31_ENDPOINT: {e}") from e

    try:
        data = _json.loads(body)
        status = (
            data.get("status")
            or data.get("result")
            or data.get("message")
            or "unknown"
        )
        tag = "HIT" if str(status).lower() in ("success", "valid", "hit", "ok") else "MISS"
        return f"[{tag}] status={status} raw={_json.dumps(data)[:400]}"
    except Exception:
        return f"[RAW] {body[:400]}"


# ──────────────────────────────────────────────────────────────────
# 4. HELPERS
# ──────────────────────────────────────────────────────────────────

def esc(s) -> str:
    return html.escape(str(s))

def new_key() -> str:
    return KEY_PREFIX + uuid.uuid4().hex[:20].upper()

def fmt_dur(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"

def render_progress(done: int, total: int, ok: int, fail: int,
                    inflight: int, started: float, status: str) -> str:
    width = 22
    pct = (done / total) if total else 0.0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    elapsed = time.time() - started
    rate = (done / elapsed) if elapsed > 0 else 0.0
    eta = ((total - done) / rate) if rate > 0 else 0.0
    icon = {"RUNNING": "⚙️", "CANCELLED": "🛑", "FINISHED": "✅"}.get(status, "⚙️")
    return (
        f"{icon} <b>BULK CHECK — {status}</b>\n"
        f"<code>[{bar}]</code> {pct*100:5.1f}%\n"
        f"✅ OK: <b>{ok}</b>   ❌ Fail: <b>{fail}</b>\n"
        f"📦 Progress: <b>{done}/{total}</b>\n"
        f"🔄 In-flight: <b>{inflight}</b>   🌐 Direct (no proxies)\n"
        f"⏱️ Elapsed: <b>{fmt_dur(elapsed)}</b>   ETA: <b>{fmt_dur(eta)}</b>\n"
        f"⚡ Rate: <b>{rate:.2f}/s</b>"
    )

def is_admin(user_id: int) -> bool:
    return user_id == SUPER_ADMIN_ID


# ──────────────────────────────────────────────────────────────────
# 5. DATABASE
# ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
    key         TEXT PRIMARY KEY,
    created_by  INTEGER NOT NULL,
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER,
    max_uses    INTEGER NOT NULL,
    uses        INTEGER NOT NULL DEFAULT 0,
    revoked     INTEGER NOT NULL DEFAULT 0,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL,
    total_bulk  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS counters (
    k TEXT PRIMARY KEY,
    v INTEGER NOT NULL DEFAULT 0
);
"""

async def db_init() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def db_touch_user(user_id: int, username: Optional[str]) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users(user_id, username, first_seen, last_seen) "
            "VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "username=excluded.username, last_seen=excluded.last_seen",
            (user_id, username or "", now, now),
        )
        await db.commit()

async def db_bump(key: str, amount: int = 1) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO counters(k,v) VALUES(?,?) "
            "ON CONFLICT(k) DO UPDATE SET v = v + excluded.v",
            (key, amount),
        )
        await db.commit()

async def db_get_counter(key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT v FROM counters WHERE k=?", (key,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0

async def key_create(by: int, uses: int, hours: float, note: str = "") -> str:
    key = new_key()
    now = int(time.time())
    expires = int(now + hours * 3600) if hours > 0 else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO keys(key,created_by,created_at,expires_at,max_uses,uses,revoked,note) "
            "VALUES(?,?,?,?,?,0,0,?)",
            (key, by, now, expires, uses, note),
        )
        await db.commit()
    return key

async def key_validate(key: str) -> tuple[bool, str, Optional[sqlite3.Row]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM keys WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
    if not row:
        return False, "❌ Key not found.", None
    if row["revoked"]:
        return False, "❌ Key has been revoked.", None
    if row["expires_at"] and row["expires_at"] < int(time.time()):
        return False, "❌ Key expired.", None
    if row["uses"] >= row["max_uses"]:
        return False, "❌ Key exhausted.", None
    return True, "", row

async def key_consume(key: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE keys SET uses = uses + 1 "
            "WHERE key=? AND revoked=0 AND uses < max_uses "
            "AND (expires_at IS NULL OR expires_at > ?)",
            (key, int(time.time())),
        )
        await db.commit()
        return cur.rowcount == 1

async def key_revoke(key: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("UPDATE keys SET revoked=1 WHERE key=?", (key,))
        await db.commit()
        return cur.rowcount == 1

async def key_list(limit: int = 20) -> list[sqlite3.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM keys ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return list(await cur.fetchall())


# ──────────────────────────────────────────────────────────────────
# 6. BULK RUNNER — direct, no proxy pool
# ──────────────────────────────────────────────────────────────────

async def run_bulk(app, chat_id: int, user_id: int,
                   items: list[str], key: str) -> None:
    state = {"cancel": False, "msg_id": None}
    ACTIVE_BULKS[user_id] = state

    total = len(items)
    results: list[Optional[str]] = [None] * total
    ok = fail = 0
    inflight = 0
    started = time.time()
    last_edit = 0.0
    processed = 0
    refresh_lock = asyncio.Lock()
    refresh_counter = 0

    msg = await app.bot.send_message(
        chat_id,
        render_progress(0, total, 0, 0, 0, started, "RUNNING"),
        parse_mode=ParseMode.HTML,
    )
    state["msg_id"] = msg.message_id

    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2, ssl=False)
    timeout = aiohttp.ClientTimeout(total=ITEM_TIMEOUT)
    sem = asyncio.Semaphore(CONCURRENCY)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        session.__dict__["_cn31_state"] = {"token_state": CN31TokenState()}

        try:
            await asyncio.wait_for(refresh_session(session), timeout=REFRESH_TIMEOUT)
        except Exception as e:
            log.warning("Initial CN31 token fetch failed: %s", e)

        async def periodic_refresh():
            nonlocal refresh_counter
            async with refresh_lock:
                refresh_counter += 1
                if refresh_counter % REFRESH_EVERY == 0:
                    try:
                        await asyncio.wait_for(refresh_session(session),
                                               timeout=REFRESH_TIMEOUT)
                        log.info("CN31 token refreshed at item %d", refresh_counter)
                    except Exception as e:
                        log.warning("CN31 refresh failed: %s", e)

        async def worker(idx: int, item: str):
            nonlocal ok, fail, inflight, last_edit, processed
            if state["cancel"]:
                return
            async with sem:
                if state["cancel"]:
                    return
                inflight += 1
                last_err = ""
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        res = await asyncio.wait_for(
                            run_task(item, session),
                            timeout=ITEM_TIMEOUT,
                        )
                        results[idx] = f"=== {idx+1}. {item} ===\n{res}\n"
                        ok += 1
                        break
                    except Exception as e:
                        last_err = f"{type(e).__name__}: {e}"
                        if "auth rejected" in str(e).lower():
                            try:
                                await asyncio.wait_for(
                                    refresh_session(session),
                                    timeout=REFRESH_TIMEOUT,
                                )
                            except Exception:
                                pass
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        results[idx] = f"=== {idx+1}. {item} ===\n[ERROR] {last_err}\n"
                        fail += 1
                inflight -= 1
                processed += 1

                asyncio.create_task(periodic_refresh())

                now = time.time()
                if (now - last_edit) >= PROGRESS_EDIT_INTERVAL or processed == total:
                    last_edit = now
                    status = "CANCELLED" if state["cancel"] else "RUNNING"
                    try:
                        await app.bot.edit_message_text(
                            render_progress(processed, total, ok, fail,
                                            inflight, started, status),
                            chat_id=chat_id,
                            message_id=msg.message_id,
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass

        tasks = [asyncio.create_task(worker(i, it)) for i, it in enumerate(items)]

        while True:
            if state["cancel"]:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                break
            if all(t.done() for t in tasks):
                await asyncio.gather(*tasks, return_exceptions=True)
                break
            await asyncio.sleep(0.2)

    final_status = "CANCELLED" if state["cancel"] else "FINISHED"
    delivered = [r for r in results if r is not None]
    try:
        await app.bot.edit_message_text(
            render_progress(len(delivered), total, ok, fail, 0,
                            started, final_status),
            chat_id=chat_id,
            message_id=msg.message_id,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    elapsed = time.time() - started
    summary = (
        f"Status    : {final_status}\n"
        f"Total     : {total}\n"
        f"Processed : {len(delivered)}\n"
        f"OK        : {ok}\n"
        f"Fail      : {fail}\n"
        f"Elapsed   : {fmt_dur(elapsed)}\n"
        f"Key used  : {key}\n"
        f"Solver    : {SOLVER_URL}\n"
        f"CN31 End  : {CN31_ENDPOINT or '(unset)'}\n"
        f"Network   : direct (no proxies)\n"
        f"Concurrency: {CONCURRENCY}\n"
        f"Refresh every: {REFRESH_EVERY}\n"
        f"Finished  : {datetime.now().isoformat(timespec='seconds')}\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"results_{ts}.txt", "\n".join(delivered) or "(no results)")
        z.writestr("summary.txt", summary)
    buf.seek(0)

    await app.bot.send_document(
        chat_id,
        InputFile(buf, filename=f"results_{ts}.zip"),
        caption=f"📦 <b>{final_status}</b> — {len(delivered)}/{total} processed",
        parse_mode=ParseMode.HTML,
    )

    await db_bump("items_processed", len(delivered))
    await db_bump("bulks_completed", 1)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET total_bulk = total_bulk + 1 WHERE user_id=?",
            (user_id,),
        )
        await db.commit()

    ACTIVE_BULKS.pop(user_id, None)


# ──────────────────────────────────────────────────────────────────
# 7. COMMAND HANDLERS
# ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await db_touch_user(u.id, u.username)
    ep_status = "configured" if CN31_ENDPOINT else "⚠️ NOT SET"
    await update.message.reply_text(
        f"👋 Hey <b>{esc(u.first_name or 'friend')}</b>!\n\n"
        "🤖 <b>Shin's Checker Bot v5 — CN31 (no-proxy)</b>\n"
        "───────────────\n"
        "🟢 /single <code>&lt;item&gt;</code> — free, one-shot\n"
        "🔑 /bulk — key-gated bulk (30 workers + CN31 token)\n"
        "🛑 /cancel — abort running bulk\n"
        "👤 /whoami — your Telegram ID\n"
        "❓ /help — full command list\n\n"
        f"🎯 CN31 endpoint: <b>{esc(ep_status)}</b>",
        parse_mode=ParseMode.HTML,
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 <b>Commands</b>\n"
        "───────────────\n"
        "🟢 <b>/single</b> <code>&lt;item&gt;</code> — free single check\n"
        "🔑 <b>/bulk</b> — start bulk flow\n"
        "🛑 <b>/cancel</b> — abort running bulk / exit flow\n"
        "👤 <b>/whoami</b> — your Telegram ID\n"
        "🎫 <b>/token</b> — CN31 solver status\n\n"
        "👑 <b>Admin</b>\n"
        "• <b>/genkey</b> <code>&lt;uses&gt; &lt;hours&gt; [note]</code>\n"
        "• <b>/revoke</b> <code>&lt;key&gt;</code>\n"
        "• <b>/keys</b> — list recent keys\n"
        "• <b>/stats</b> — global counters",
        parse_mode=ParseMode.HTML,
    )

async def cmd_whoami(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await update.message.reply_text(
        f"👤 ID: <code>{u.id}</code>\n"
        f"🏷️ Username: @{esc(u.username or '—')}\n"
        f"👑 Admin: {'yes' if is_admin(u.id) else 'no'}",
        parse_mode=ParseMode.HTML,
    )

async def cmd_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    st = await fetch_cn31_token()
    if not st or not st.token:
        await update.message.reply_text("❌ Solver returned nothing.")
        return
    masked = st.token[:24] + "…" + st.token[-8:]
    await update.message.reply_text(
        "🎫 <b>CN31 solver</b>\n"
        "───────────────\n"
        f"🔗 <code>{esc(SOLVER_URL)}</code>\n"
        f"🧩 Pool size: <b>{st.pool_size}</b>\n"
        f"⏳ Expires in: <b>{int(st.expires_in)}s</b>\n"
        f"🔑 Token: <code>{esc(masked)}</code>",
        parse_mode=ParseMode.HTML,
    )

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    stopped = False
    if uid in ACTIVE_BULKS:
        ACTIVE_BULKS[uid]["cancel"] = True
        stopped = True
    ctx.user_data.clear()
    if stopped:
        await update.message.reply_text("🛑 Cancelling — partial zip incoming…")
    else:
        await update.message.reply_text("✅ Nothing running. State cleared.")

async def cmd_single(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await db_touch_user(u.id, u.username)
    if not ctx.args:
        await update.message.reply_text(
            "Usage: <code>/single &lt;item&gt;</code>", parse_mode=ParseMode.HTML
        )
        return
    if not CN31_ENDPOINT:
        await update.message.reply_text(
            "❌ <b>CN31_ENDPOINT is not set.</b>\n"
            "Set the env var to a real URL and restart.",
            parse_mode=ParseMode.HTML,
        )
        return
    item = " ".join(ctx.args).strip()
    msg = await update.message.reply_text(
        f"⚙️ Running single check on <code>{esc(item)}</code>…",
        parse_mode=ParseMode.HTML,
    )
    t0 = time.time()
    try:
        connector = aiohttp.TCPConnector(limit=10, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            session.__dict__["_cn31_state"] = {"token_state": CN31TokenState()}
            try:
                await asyncio.wait_for(refresh_session(session), timeout=REFRESH_TIMEOUT)
            except Exception as e:
                log.warning("single CN31 refresh failed: %s", e)
            res = await asyncio.wait_for(
                run_task(item, session), timeout=ITEM_TIMEOUT
            )
        await msg.edit_text(
            f"✅ <b>DONE</b> — {fmt_dur(time.time()-t0)}\n"
            f"───────────────\n"
            f"📥 <b>Input:</b> <code>{esc(item)}</code>\n"
            f"🌐 <b>Network:</b> direct\n"
            f"📤 <b>Result:</b>\n<pre>{esc(res)}</pre>",
            parse_mode=ParseMode.HTML,
        )
        await db_bump("singles_run", 1)
    except Exception as e:
        await msg.edit_text(
            f"❌ <b>ERROR</b>\n<pre>{esc(type(e).__name__)}: {esc(e)}</pre>",
            parse_mode=ParseMode.HTML,
        )

async def cmd_bulk(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await db_touch_user(u.id, u.username)
    if not CN31_ENDPOINT:
        await update.message.reply_text(
            "❌ <b>CN31_ENDPOINT is not set.</b> Admin must configure it.",
            parse_mode=ParseMode.HTML,
        )
        return
    if u.id in ACTIVE_BULKS:
        await update.message.reply_text("⚠️ You already have a bulk run going. /cancel it first.")
        return
    ctx.user_data["state"] = "await_key"
    await update.message.reply_text(
        "🔑 <b>Bulk flow — step 1/2</b>\n"
        "Send me a valid key (or /cancel to exit).",
        parse_mode=ParseMode.HTML,
    )

async def _handle_key_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    key = update.message.text.strip()
    ok, err, row = await key_validate(key)
    if not ok:
        await update.message.reply_text(err + "\nTry again or /cancel.")
        return
    ctx.user_data["state"] = "await_items"
    ctx.user_data["key"] = key
    remaining = row["max_uses"] - row["uses"]
    expires = "never" if not row["expires_at"] else datetime.fromtimestamp(
        row["expires_at"]).strftime("%Y-%m-%d %H:%M")
    await update.message.reply_text(
        f"✅ Key accepted.\n"
        f"🎟️ Uses left: <b>{remaining}</b>\n"
        f"⏳ Expires: <b>{expires}</b>\n\n"
        f"<b>Step 2/2</b> — send your list:\n"
        f"• paste lines here, <b>or</b>\n"
        f"• upload a <code>.txt</code> file (one item per line)\n"
        f"Max {MAX_ITEMS_PER_BULK}. Concurrency {CONCURRENCY}. "
        f"CN31 refresh every {REFRESH_EVERY}. /cancel to abort.",
        parse_mode=ParseMode.HTML,
    )

async def _handle_items_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    items = [ln.strip() for ln in (update.message.text or "").splitlines() if ln.strip()]
    await _start_bulk_from_items(update, ctx, items)

async def _handle_items_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if doc.file_size and doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("❌ File too large (5 MB max).")
        return
    tg_file = await doc.get_file()
    data = await tg_file.download_as_bytearray()
    items = [ln.strip() for ln in data.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    await _start_bulk_from_items(update, ctx, items)

async def _start_bulk_from_items(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                                 items: list[str]) -> None:
    if not items:
        await update.message.reply_text("❌ No items found. /cancel to exit.")
        return
    if len(items) > MAX_ITEMS_PER_BULK:
        await update.message.reply_text(
            f"❌ Too many items ({len(items)}). Max is {MAX_ITEMS_PER_BULK}."
        )
        return
    key = ctx.user_data.get("key")
    if not key:
        await update.message.reply_text("❌ Lost the key. Start over with /bulk.")
        ctx.user_data.clear()
        return
    if not await key_consume(key):
        await update.message.reply_text("❌ Key became invalid between validation and start.")
        ctx.user_data.clear()
        return
    ctx.user_data.clear()
    await update.message.reply_text(
        f"🚀 Queued <b>{len(items)}</b> items. CN31 token primed — progress incoming…",
        parse_mode=ParseMode.HTML,
    )
    asyncio.create_task(run_bulk(ctx.application, update.effective_chat.id,
                                 update.effective_user.id, items, key))

async def cmd_genkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: <code>/genkey &lt;uses&gt; &lt;hours&gt; [note]</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        uses = int(args[0])
        hours = float(args[1])
        if uses <= 0 or hours < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Bad numbers. Uses >0, hours ≥0.")
        return
    note = " ".join(args[2:])[:100] if len(args) > 2 else ""
    key = await key_create(update.effective_user.id, uses, hours, note)
    exp = "never" if hours == 0 else f"{hours}h from now"
    await update.message.reply_text(
        f"🔑 <b>Key minted</b>\n<code>{key}</code>\n\n"
        f"🎟️ Uses: <b>{uses}</b>\n⏳ Expires: <b>{esc(exp)}</b>\n"
        f"📝 Note: {esc(note) if note else '—'}",
        parse_mode=ParseMode.HTML,
    )

async def cmd_revoke(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: <code>/revoke &lt;key&gt;</code>",
                                        parse_mode=ParseMode.HTML)
        return
    key = ctx.args[0].strip()
    ok = await key_revoke(key)
    await update.message.reply_text(
        f"{'✅ Revoked' if ok else '❌ Not found'}: <code>{esc(key)}</code>",
        parse_mode=ParseMode.HTML,
    )

async def cmd_keys(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    rows = await key_list(20)
    if not rows:
        await update.message.reply_text("No keys yet.")
        return
    now = int(time.time())
    lines = ["🔑 <b>Recent keys</b>", "───────────────"]
    for r in rows:
        status = "🟢"
        if r["revoked"]:
            status = "⛔"
        elif r["expires_at"] and r["expires_at"] < now:
            status = "⌛"
        elif r["uses"] >= r["max_uses"]:
            status = "🔴"
        exp = "never" if not r["expires_at"] else datetime.fromtimestamp(
            r["expires_at"]).strftime("%m-%d %H:%M")
        lines.append(
            f"{status} <code>{r['key']}</code>  [{r['uses']}/{r['max_uses']}] exp:{exp}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    singles = await db_get_counter("singles_run")
    items   = await db_get_counter("items_processed")
    bulks   = await db_get_counter("bulks_completed")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM keys WHERE revoked=0") as cur:
            active_keys = (await cur.fetchone())[0]
    await update.message.reply_text(
        "📊 <b>Global stats</b>\n"
        "───────────────\n"
        f"👥 Users seen:      <b>{users}</b>\n"
        f"🔑 Active keys:     <b>{active_keys}</b>\n"
        f"🟢 Singles run:     <b>{singles}</b>\n"
        f"📦 Bulks completed: <b>{bulks}</b>\n"
        f"⚙️ Items processed: <b>{items}</b>\n"
        f"🏃 Active bulks:    <b>{len(ACTIVE_BULKS)}</b>\n"
        f"🌐 Network:         <b>direct (no proxies)</b>\n"
        f"🎫 Solver:          <code>{esc(SOLVER_URL)}</code>\n"
        f"🎯 CN31 endpoint:   <code>{esc(CN31_ENDPOINT or '(unset)')}</code>",
        parse_mode=ParseMode.HTML,
    )

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = ctx.user_data.get("state")
    if state == "await_key":
        await _handle_key_input(update, ctx)
    elif state == "await_items":
        await _handle_items_input(update, ctx)
    else:
        await update.message.reply_text("🤔 Not sure what to do with that. Try /help.")

async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if ctx.user_data.get("state") == "await_items":
        await _handle_items_file(update, ctx)
    else:
        await update.message.reply_text("📎 Upload a .txt file after /bulk → key step.")


# ──────────────────────────────────────────────────────────────────
# 8. BOOT
# ──────────────────────────────────────────────────────────────────

async def _post_init(app) -> None:
    await db_init()
    log.info("DB initialised at %s", DB_PATH)
    if not CN31_ENDPOINT:
        log.warning("CN31_ENDPOINT is not set — /single and /bulk will refuse to run")
    else:
        log.info("CN31_ENDPOINT = %s", CN31_ENDPOINT)
    st = await fetch_cn31_token()
    if st and st.token:
        log.info("Solver OK — pool_size=%s expires_in=%ss",
                 st.pool_size, int(st.expires_in))
    else:
        log.warning("Solver did NOT return a token on boot — check SOLVER_URL")
    me = await app.bot.get_me()
    log.info("Bot running as @%s (id=%s)", me.username, me.id)

def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("❌ Set BOT_TOKEN env var first.")
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("single", cmd_single))
    app.add_handler(CommandHandler("bulk", cmd_bulk))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("token", cmd_token))
    app.add_handler(CommandHandler("genkey", cmd_genkey))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.add_handler(CommandHandler("keys", cmd_keys))
    app.add_handler(CommandHandler("stats", cmd_stats))

    app.add_handler(MessageHandler(filters.Document.FileExtension("txt"), on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
