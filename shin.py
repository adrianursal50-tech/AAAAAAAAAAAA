#!/usr/bin/env python3
# ===================================================================
# MLBB Device ID Checker — Telegram Bot (async, retry-hardened)
# -------------------------------------------------------------------
#   • Single /check <device_id>
#   • /bulk flow (paste lines or .txt upload)
#   • 5 concurrent workers, 3 retries w/ backoff per item
#   • Proper SDP protocol: zstd/zlib/AES-encrypted responses
# ===================================================================

import asyncio
import html
import io
import logging
import os
import socket
import struct
import time
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

import zstandard as zstd
from Crypto.Cipher import AES
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

AES_KEY      = bytes.fromhex("f5a193d50ade553e9835595f5cd75ddd")
AES_IV       = b"\x00" * 16
SERVER_HOST  = "login.ml.youngjoygame.com"
SERVER_PORT  = 30021
CLIENT_VER   = "2.1.99.1205.1"
CHANNEL      = "and_usa"
LANGUAGE     = "en"

CONNECT_TIMEOUT   = 10.0     # socket connect timeout
READ_TIMEOUT      = 10.0     # socket read timeout
MAX_RETRIES       = 3        # per-item retry count
RETRY_BACKOFF     = 1.2      # seconds, multiplied per attempt
BULK_CONCURRENCY  = 5        # parallel socket workers
BULK_MAX_ITEMS    = 1000
PROGRESS_EDIT_S   = 2.0

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("mlbb-bot")

ACTIVE_BULKS: dict[int, dict] = {}


# ──────────────────────────────────────────────────────────────────
# 2. SDP PROTOCOL
# ──────────────────────────────────────────────────────────────────

class SdpDataType:
    INTEGER_POSITIVE = 0
    INTEGER_NEGATIVE = 1
    FLOAT            = 2
    DOUBLE           = 3
    STRING           = 4
    LIST             = 5
    DICT             = 6
    STRUCT_BEGIN     = 7
    STRUCT_END       = 8


class SdpStruct(dict):
    def __init__(self, data=None):
        super().__init__()
        self.data = b""
        self.offset = 0
        if isinstance(data, bytes):
            self.data = data
            self._unpack()
        elif data is not None:
            self.update(data)
            self._pack()

    def _pack(self):
        self.data = bytes([SdpDataType.STRUCT_BEGIN << 4])
        for k, v in sorted(self.items()):
            self._pack_item(k, v)
        self.data += bytes([SdpDataType.STRUCT_END << 4])

    def _unpack(self):
        if not self.data:
            return
        if self.data[0] >> 4 == SdpDataType.STRUCT_BEGIN:
            self.offset = 1
        while self.offset < len(self.data):
            k, v = self._unpack_item()
            if v is SdpDataType.STRUCT_END:
                break
            self[k] = v

    def _write_varint(self, n: int) -> bytes:
        res = bytearray()
        while n >= 0x80:
            res.append((n & 0x7F) | 0x80)
            n >>= 7
        res.append(n & 0x7F)
        return bytes(res)

    def _read_varint(self) -> int:
        val = 0
        shift = 0
        while True:
            b = self.data[self.offset]
            self.offset += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return val

    def _pack_header(self, tag: int, dtype: int):
        if tag < 15:
            self.data += bytes([(dtype << 4) | tag])
        else:
            self.data += bytes([(dtype << 4) | 15]) + self._write_varint(tag)

    def _pack_item(self, tag: int, val):
        if isinstance(val, bool):
            self._pack_header(tag, SdpDataType.INTEGER_POSITIVE)
            self.data += self._write_varint(1 if val else 0)
        elif isinstance(val, int):
            if val < 0:
                self._pack_header(tag, SdpDataType.INTEGER_NEGATIVE)
                self.data += self._write_varint(-val)
            else:
                self._pack_header(tag, SdpDataType.INTEGER_POSITIVE)
                self.data += self._write_varint(val)
        elif isinstance(val, float):
            self._pack_header(tag, SdpDataType.DOUBLE)
            self.data += self._write_varint(8) + struct.pack("<d", val)
        elif isinstance(val, (str, bytes)):
            self._pack_header(tag, SdpDataType.STRING)
            enc = val.encode("utf-8") if isinstance(val, str) else val
            self.data += self._write_varint(len(enc)) + enc
        elif isinstance(val, list):
            self._pack_header(tag, SdpDataType.LIST)
            self.data += self._write_varint(len(val))
            for item in val:
                self._pack_item(0, item)
        elif isinstance(val, dict):
            if isinstance(val, SdpStruct):
                self._pack_header(tag, SdpDataType.STRUCT_BEGIN)
                for k, v in sorted(val.items()):
                    self._pack_item(k, v)
                self.data += bytes([SdpDataType.STRUCT_END << 4])
            else:
                self._pack_header(tag, SdpDataType.DICT)
                self.data += self._write_varint(len(val))
                for k, v in sorted(val.items()):
                    self._pack_item(0, k)
                    self._pack_item(0, v)
        else:
            raise TypeError(f"Unsupported SDP type: {type(val)}")

    def _unpack_item(self) -> Tuple[int, any]:
        if self.offset >= len(self.data):
            return 0, None
        hdr = self.data[self.offset]
        tag = hdr & 0xF
        dtype = hdr >> 4
        self.offset += 1
        if tag == 15:
            tag = self._read_varint()
        if dtype == SdpDataType.INTEGER_POSITIVE:
            return tag, self._read_varint()
        if dtype == SdpDataType.INTEGER_NEGATIVE:
            return tag, -self._read_varint()
        if dtype in (SdpDataType.FLOAT, SdpDataType.DOUBLE):
            ln = self._read_varint()
            raw = self.data[self.offset:self.offset + ln]
            self.offset += ln
            fmt = "<f" if dtype == SdpDataType.FLOAT else "<d"
            return tag, struct.unpack(fmt, raw[:struct.calcsize(fmt)])[0]
        if dtype == SdpDataType.STRING:
            ln = self._read_varint()
            raw = self.data[self.offset:self.offset + ln]
            self.offset += ln
            try:
                return tag, raw.decode("utf-8")
            except Exception:
                return tag, raw
        if dtype == SdpDataType.LIST:
            ln = self._read_varint()
            return tag, [self._unpack_item()[1] for _ in range(ln)]
        if dtype == SdpDataType.DICT:
            ln = self._read_varint()
            res = {}
            for _ in range(ln):
                _, k = self._unpack_item()
                _, v = self._unpack_item()
                res[k] = v
            return tag, res
        if dtype == SdpDataType.STRUCT_BEGIN:
            res = {}
            while True:
                k, v = self._unpack_item()
                if v is SdpDataType.STRUCT_END:
                    break
                res[k] = v
            return tag, SdpStruct(res)
        if dtype == SdpDataType.STRUCT_END:
            return tag, SdpDataType.STRUCT_END
        raise ValueError(f"Unknown SDP type: {dtype}")


# ──────────────────────────────────────────────────────────────────
# 3. GAME LOGIN CLIENT (blocking — run via asyncio.to_thread)
# ──────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    ok: bool
    account_id: Optional[int] = None
    zone_id: Optional[int] = None
    status: str = ""
    error: str = ""
    elapsed: float = 0.0


class GameLogin:
    def __init__(self, device_id: str):
        self.device_id = device_id.strip()
        raw = self.device_id
        if raw.startswith(("and_", "ios_")):
            raw = raw[4:]
        self.imei    = raw[:32] if len(raw) >= 32 else raw
        self.android = raw[32:48] if len(raw) >= 48 else ""
        self.adid    = raw[48:] if len(raw) > 48 else ""
        self.sequence = 1
        self.sock: Optional[socket.socket] = None
        self.queue = b""

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(CONNECT_TIMEOUT)
        self.sock.connect((SERVER_HOST, SERVER_PORT))
        self.sock.settimeout(READ_TIMEOUT)

    def cleanup(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sequence = 1
        self.sock = None
        self.queue = b""

    def send_data(self, pid: int, sdp: SdpStruct):
        pkt = SdpStruct({0: pid, 1: self.sequence, 5: sdp.data}).data
        comp = zstd.compress(pkt)
        flags = (len(comp) + 4) | (16 << 24)
        self.sock.sendall(flags.to_bytes(4, "big") + comp)
        self.sequence += 1

    def _recv_exact(self, n: int) -> bytes:
        while len(self.queue) < n:
            chunk = self.sock.recv(8192)
            if not chunk:
                raise ConnectionError("connection closed by peer")
            self.queue += chunk
        out, self.queue = self.queue[:n], self.queue[n:]
        return out

    def recv_data(self) -> Tuple[Optional[int], Optional[SdpStruct]]:
        try:
            hdr = self._recv_exact(4)
            flags = int.from_bytes(hdr, "big")
            size  = flags & 0xFFFFFF
            ctype = flags >> 24
            payload = self._recv_exact(size - 4)

            if ctype == 1:
                data = zlib.decompress(payload)
            elif ctype == 16:
                data = zstd.decompress(payload)
            elif ctype in (2, 3, 18):
                cipher = AES.new(AES_KEY, AES.MODE_CBC, iv=AES_IV)
                dec = cipher.decrypt(payload)
                # strip PKCS7 padding
                if dec and 1 <= dec[-1] <= 16:
                    dec = dec[:-dec[-1]]
                data = dec
                if ctype == 3:
                    data = zlib.decompress(data)
                elif ctype == 18:
                    data = zstd.decompress(data)
            else:
                data = payload

            res = SdpStruct(data)
            pid = res.get(0)
            if pid is None:
                return None, None
            body = res.get(6) or res.get(5)
            if isinstance(body, bytes):
                try:
                    return pid, SdpStruct(body)
                except Exception:
                    return pid, None
            if isinstance(body, SdpStruct):
                return pid, body
            return pid, None
        except socket.timeout:
            return -1, None
        except Exception:
            return None, None

    def run(self) -> CheckResult:
        t0 = time.time()
        try:
            self.connect()
            self.send_data(1, SdpStruct({
                0: self.device_id,
                1: f"gps_adid={self.adid}&android_id={self.android}&device_unique_id={self.imei}",
                2: CLIENT_VER,
                3: CHANNEL,
                4: LANGUAGE,
            }))
            pid, res = self.recv_data()
            if pid == 2 and res:
                account_id = res.get(0)
                zone_id = None
                zone_field = res.get(2)
                if isinstance(zone_field, list) and zone_field:
                    zone_id = zone_field[0]
                elif isinstance(zone_field, int):
                    zone_id = zone_field
                return CheckResult(
                    ok=bool(account_id),
                    account_id=account_id,
                    zone_id=zone_id,
                    status="SUCCESS",
                    elapsed=time.time() - t0,
                )
            return CheckResult(
                ok=False, status=f"FAIL (pid={pid})",
                error="server rejected or malformed reply",
                elapsed=time.time() - t0,
            )
        except socket.timeout:
            return CheckResult(ok=False, status="TIMEOUT",
                               error="socket timed out", elapsed=time.time() - t0)
        except ConnectionError as e:
            return CheckResult(ok=False, status="CONN",
                               error=f"connection: {e}", elapsed=time.time() - t0)
        except Exception as e:
            return CheckResult(ok=False, status="ERR",
                               error=f"{type(e).__name__}: {e}",
                               elapsed=time.time() - t0)
        finally:
            self.cleanup()


# ──────────────────────────────────────────────────────────────────
# 4. RELIABLE WRAPPER — retries with backoff
# ──────────────────────────────────────────────────────────────────

async def check_one(device_id: str, retries: int = MAX_RETRIES) -> CheckResult:
    last: Optional[CheckResult] = None
    for attempt in range(retries):
        r = await asyncio.to_thread(GameLogin(device_id).run)
        if r.ok:
            return r
        last = r
        # don't retry a clean FAIL (server responded, just not a valid id)
        if r.status.startswith("FAIL"):
            return r
        if attempt < retries - 1:
            await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
    return last or CheckResult(ok=False, status="ERR", error="unknown")


# ──────────────────────────────────────────────────────────────────
# 5. RANK MAPPING
# ──────────────────────────────────────────────────────────────────

def map_rank(p) -> str:
    if not p or not isinstance(p, (int, float)) or p <= 0:
        return "Unranked"
    p = int(p)
    if p >= 136:
        stars = p - 136
        if stars >= 100: return f"Mythical Immortal ({stars}★)"
        if stars >= 50:  return f"Mythical Glory ({stars}★)"
        if stars >= 25:  return f"Mythical Honor ({stars}★)"
        return f"Mythic ({stars}★)"
    ranks = [
        (105, "Legend", 5, ["V","IV","III","II","I"]),
        (75,  "Epic",   5, ["V","IV","III","II","I"]),
        (45,  "Grandmaster", 5, ["V","IV","III","II","I"]),
        (25,  "Master", 4, ["IV","III","II","I"]),
        (10,  "Elite",  4, ["IV","III","II","I"]),
        (1,   "Warrior",3, ["III","II","I"]),
    ]
    for threshold, name, div_stars, div_names in ranks:
        if p >= threshold:
            offset = p - threshold
            div_idx = min(len(div_names) - 1, offset // div_stars)
            star = (offset % div_stars) + 1
            return f"{name} {div_names[div_idx]} ({star}★)"
    return "Warrior III (1★)"


# ──────────────────────────────────────────────────────────────────
# 6. HELPERS
# ──────────────────────────────────────────────────────────────────

def esc(s) -> str:
    return html.escape(str(s))

def fmt_dur(sec: float) -> str:
    s = int(max(0, sec))
    if s < 60: return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60: return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"

def is_admin(uid: int) -> bool:
    return uid == SUPER_ADMIN_ID

def render_single(device_id: str, r: CheckResult) -> str:
    if not r.ok:
        return (
            f"❌ <b>CHECK FAILED</b>\n"
            f"───────────────\n"
            f"📱 Device: <code>{esc(device_id)}</code>\n"
            f"⚠️ Status: <b>{esc(r.status)}</b>\n"
            f"💬 Detail: <code>{esc(r.error or 'n/a')}</code>\n"
            f"⏱️ Time: <b>{fmt_dur(r.elapsed)}</b>"
        )
    return (
        f"✅ <b>VALID DEVICE</b>\n"
        f"───────────────\n"
        f"📱 Device: <code>{esc(device_id)}</code>\n"
        f"🆔 Account: <b>{r.account_id}</b>\n"
        f"🗺️ Zone: <b>{r.zone_id if r.zone_id else '—'}</b>\n"
        f"⏱️ Time: <b>{fmt_dur(r.elapsed)}</b>"
    )

def render_progress(done, total, ok, fail, inflight, started, status) -> str:
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
        f"🔄 In-flight: <b>{inflight}</b>\n"
        f"⏱️ Elapsed: <b>{fmt_dur(elapsed)}</b>   ETA: <b>{fmt_dur(eta)}</b>\n"
        f"⚡ Rate: <b>{rate:.2f}/s</b>"
    )


# ──────────────────────────────────────────────────────────────────
# 7. BULK RUNNER
# ──────────────────────────────────────────────────────────────────

async def run_bulk(app, chat_id: int, user_id: int, items: list[str]) -> None:
    state = {"cancel": False, "msg_id": None}
    ACTIVE_BULKS[user_id] = state

    total = len(items)
    results: list[Optional[str]] = [None] * total
    ok = fail = 0
    inflight = 0
    started = time.time()
    last_edit = 0.0
    processed = 0
    sem = asyncio.Semaphore(BULK_CONCURRENCY)

    msg = await app.bot.send_message(
        chat_id,
        render_progress(0, total, 0, 0, 0, started, "RUNNING"),
        parse_mode=ParseMode.HTML,
    )
    state["msg_id"] = msg.message_id

    async def worker(idx: int, device_id: str):
        nonlocal ok, fail, inflight, last_edit, processed
        if state["cancel"]:
            return
        async with sem:
            if state["cancel"]:
                return
            inflight += 1
            try:
                r = await check_one(device_id)
                if r.ok:
                    results[idx] = (
                        f"=== {idx+1}. {device_id} ===\n"
                        f"VALID | account={r.account_id} zone={r.zone_id} "
                        f"time={r.elapsed:.2f}s\n"
                    )
                    ok += 1
                else:
                    results[idx] = (
                        f"=== {idx+1}. {device_id} ===\n"
                        f"INVALID | status={r.status} detail={r.error}\n"
                    )
                    fail += 1
            except Exception as e:
                results[idx] = f"=== {idx+1}. {device_id} ===\nERROR {e}\n"
                fail += 1
            finally:
                inflight -= 1
                processed += 1

            now = time.time()
            if (now - last_edit) >= PROGRESS_EDIT_S or processed == total:
                last_edit = now
                st = "CANCELLED" if state["cancel"] else "RUNNING"
                try:
                    await app.bot.edit_message_text(
                        render_progress(processed, total, ok, fail,
                                        inflight, started, st),
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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"results_{ts}.txt", "\n".join(delivered) or "(no results)")
        z.writestr("summary.txt",
                   f"Status: {final_status}\n"
                   f"Total: {total}\nProcessed: {len(delivered)}\n"
                   f"Valid: {ok}\nInvalid: {fail}\n"
                   f"Elapsed: {fmt_dur(time.time()-started)}\n"
                   f"Server: {SERVER_HOST}:{SERVER_PORT}\n")
    buf.seek(0)
    await app.bot.send_document(
        chat_id,
        InputFile(buf, filename=f"results_{ts}.zip"),
        caption=f"📦 <b>{final_status}</b> — {ok} valid / {fail} invalid",
        parse_mode=ParseMode.HTML,
    )

    ACTIVE_BULKS.pop(user_id, None)


# ──────────────────────────────────────────────────────────────────
# 8. COMMAND HANDLERS
# ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await update.message.reply_text(
        f"👋 Hey <b>{esc(u.first_name or 'friend')}</b>!\n\n"
        "🤖 <b>MLBB Device ID Checker</b>\n"
        "───────────────\n"
        "🔍 /check <code>&lt;device_id&gt;</code> — single check\n"
        "📦 /bulk — bulk check (paste lines or upload .txt)\n"
        "🛑 /cancel — abort running bulk\n"
        "👤 /whoami — your Telegram ID",
        parse_mode=ParseMode.HTML,
    )

async def cmd_whoami(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await update.message.reply_text(
        f"👤 ID: <code>{u.id}</code>\n"
        f"🏷️ @{esc(u.username or '—')}\n"
        f"👑 Admin: {'yes' if is_admin(u.id) else 'no'}",
        parse_mode=ParseMode.HTML,
    )

async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "Usage: <code>/check &lt;device_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    device_id = " ".join(ctx.args).strip()
    msg = await update.message.reply_text(
        f"⚙️ Checking <code>{esc(device_id)}</code>…",
        parse_mode=ParseMode.HTML,
    )
    try:
        r = await check_one(device_id)
    except Exception as e:
        await msg.edit_text(
            f"❌ <b>ERROR</b>\n<pre>{esc(type(e).__name__)}: {esc(e)}</pre>",
            parse_mode=ParseMode.HTML,
        )
        return
    await msg.edit_text(render_single(device_id, r), parse_mode=ParseMode.HTML)

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    stopped = False
    if uid in ACTIVE_BULKS:
        ACTIVE_BULKS[uid]["cancel"] = True
        stopped = True
    ctx.user_data.clear()
    await update.message.reply_text(
        "🛑 Cancelling — partial zip incoming…" if stopped else "✅ Nothing running."
    )

async def cmd_bulk(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if uid in ACTIVE_BULKS:
        await update.message.reply_text("⚠️ You already have a bulk running. /cancel first.")
        return
    ctx.user_data["state"] = "await_items"
    await update.message.reply_text(
        "📦 <b>Bulk flow</b>\n"
        "Send your list:\n"
        "• paste lines here, <b>or</b>\n"
        "• upload a <code>.txt</code> file (one device id per line)\n"
        f"Max {BULK_MAX_ITEMS}. Concurrency {BULK_CONCURRENCY}. /cancel to abort.",
        parse_mode=ParseMode.HTML,
    )

async def _handle_items_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    items = [ln.strip() for ln in (update.message.text or "").splitlines() if ln.strip()]
    await _start_bulk(update, ctx, items)

async def _handle_items_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if doc.file_size and doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("❌ File too large (5 MB max).")
        return
    f = await doc.get_file()
    data = await f.download_as_bytearray()
    items = [
        ln.strip()
        for ln in data.decode("utf-8", errors="replace").splitlines()
        if ln.strip()
    ]
    await _start_bulk(update, ctx, items)

async def _start_bulk(update: Update, ctx: ContextTypes.DEFAULT_TYPE, items: list[str]) -> None:
    if not items:
        await update.message.reply_text("❌ No items found. /cancel to exit.")
        return
    if len(items) > BULK_MAX_ITEMS:
        await update.message.reply_text(
            f"❌ Too many items ({len(items)}). Max is {BULK_MAX_ITEMS}."
        )
        return
    ctx.user_data.clear()
    await update.message.reply_text(
        f"🚀 Queued <b>{len(items)}</b> device IDs. Progress incoming…",
        parse_mode=ParseMode.HTML,
    )
    asyncio.create_task(run_bulk(
        ctx.application, update.effective_chat.id, update.effective_user.id, items
    ))

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if ctx.user_data.get("state") == "await_items":
        await _handle_items_input(update, ctx)
    else:
        await update.message.reply_text("🤔 Try /check, /bulk, or /start.")

async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if ctx.user_data.get("state") == "await_items":
        await _handle_items_file(update, ctx)
    else:
        await update.message.reply_text("📎 Upload a .txt file after /bulk.")


# ──────────────────────────────────────────────────────────────────
# 9. BOOT
# ──────────────────────────────────────────────────────────────────

async def _post_init(app) -> None:
    me = await app.bot.get_me()
    log.info("Bot running as @%s (id=%s)", me.username, me.id)
    log.info("Target: %s:%s", SERVER_HOST, SERVER_PORT)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("❌ Set BOT_TOKEN env var first.")
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("bulk", cmd_bulk))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("whoami", cmd_whoami))

    app.add_handler(MessageHandler(filters.Document.FileExtension("txt"), on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")