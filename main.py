"""
╔══════════════════════════════════════════════════════════════╗
║          CO-SAMA v3.0 — Téléchargeur de Scans Manga          ║
║   asyncio · aiohttp · ConsoleUI (PC) · SimpleUI (Android)    ║
╚══════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-INSTALL DES DÉPENDANCES
# ══════════════════════════════════════════════════════════════════════════════
import importlib
import importlib.util
import subprocess
import sys


def _ensure(package: str, import_as: str | None = None) -> None:
    name = import_as or package
    if importlib.util.find_spec(name) is None:
        print(f"📦 Installation de '{package}'…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"   ✅ '{package}' installé.")


_ensure("aiohttp")

# ══════════════════════════════════════════════════════════════════════════════
#  IMPORTS
# ══════════════════════════════════════════════════════════════════════════════
import asyncio
import json
import os
import platform
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

try:
    import ctypes
except ImportError:
    ctypes = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import tty
    import termios
    import select as _select
except ImportError:
    tty = termios = _select = None

import aiohttp

# ══════════════════════════════════════════════════════════════════════════════
#  DÉTECTION PLATEFORME
# ══════════════════════════════════════════════════════════════════════════════

def _is_termux() -> bool:
    return os.name != "nt" and (
        "ANDROID_STORAGE" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
    )


IS_ANDROID: bool = _is_termux()

# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE PC — ConsoleUI (flèches, logo ASCII, menus interactifs)
# ══════════════════════════════════════════════════════════════════════════════

class ConsoleUI:
    RESET  = '\033[0m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    RED    = '\033[31m'
    GREEN  = '\033[32m'
    YELLOW = '\033[33m'
    CYAN   = '\033[36m'

    ASCII_LOGO = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║    ██████╗ ██████╗       ███████╗ █████╗ ███╗  ███╗ █████╗  ║
║   ██╔════╝██╔═══██╗      ██╔════╝██╔══██╗████╗████║██╔══██╗ ║
║   ██║     ██║   ██║█████╗███████╗███████║██╔████╔██║███████║ ║
║   ██║     ██║   ██║╚════╝╚════██║██╔══██║██║╚██╔╝██║██╔══██║ ║
║   ╚██████╗╚██████╔╝      ███████║██║  ██║██║ ╚═╝ ██║██║  ██║ ║
║    ╚═════╝ ╚═════╝       ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝ ║
║                                                              ║
║              🌙  CO-SAMA  SCAN DOWNLOADER  🌙               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝"""

    MAX_VISIBLE = 8

    @staticmethod
    def enable_ansi() -> None:
        if os.name == 'nt' and ctypes:
            try:
                ctypes.windll.kernel32.SetConsoleMode(
                    ctypes.windll.kernel32.GetStdHandle(-11), 7
                )
            except Exception:
                pass

    @staticmethod
    def clear() -> None:
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def display_len(s: str) -> int:
        count, i = 0, 0
        while i < len(s):
            cp = ord(s[i])
            if cp in (0xFE0E, 0xFE0F, 0x200D, 0x20E3):
                i += 1
                continue
            if 0x0300 <= cp <= 0x036F:
                i += 1
                continue
            if 0x1F3FB <= cp <= 0x1F3FF:
                i += 1
                continue
            is_wide = (
                0x1F000 <= cp <= 0x1FFFF or 0x2600 <= cp <= 0x27BF
                or 0x2B00 <= cp <= 0x2BFF or 0xFE30 <= cp <= 0xFE4F
                or 0x2E80 <= cp <= 0x2EFF or 0x3000 <= cp <= 0x9FFF
                or 0xF900 <= cp <= 0xFAFF or 0xAC00 <= cp <= 0xD7AF
            )
            if is_wide:
                count += 2
                j = i + 1
                while j < len(s):
                    ncp = ord(s[j])
                    if ncp in (0x200D, 0xFE0E, 0xFE0F, 0x20E3) or 0x1F3FB <= ncp <= 0x1F3FF:
                        j += 1
                        continue
                    if 0x1F000 <= ncp <= 0x1FFFF or 0x2600 <= ncp <= 0x27BF:
                        j += 1
                        continue
                    break
                i = j
            else:
                count += 1
                i += 1
        return count

    @staticmethod
    def print_logo() -> None:
        print(ConsoleUI.CYAN + ConsoleUI.ASCII_LOGO + ConsoleUI.RESET)

    @staticmethod
    def show_menu(options: list, title: str = "MENU",
                  selected_index: int = 0, subtitle: str = "") -> None:
        box_w = 62
        ConsoleUI.clear()
        ConsoleUI.print_logo()
        if subtitle:
            print(f"\n  {ConsoleUI.DIM}{subtitle}{ConsoleUI.RESET}\n")
        else:
            print()

        visible = min(len(options), ConsoleUI.MAX_VISIBLE)
        half    = visible // 2
        top     = max(0, min(selected_index - half, len(options) - visible))

        h_line = "═" * box_w
        tlen   = ConsoleUI.display_len(title)
        tpad_l = max(0, (box_w - tlen) // 2)
        tpad_r = max(0, box_w - tlen - tpad_l)
        print(f"  ╔{h_line}╗")
        print(f"  ║{' '*tpad_l}{ConsoleUI.BOLD}{ConsoleUI.CYAN}{title}"
              f"{ConsoleUI.RESET}{' '*tpad_r}║")
        print(f"  ╠{h_line}╣")

        if top > 0:
            txt = f"▲  {top} élément(s) plus haut"
            pad = " " * max(0, box_w - 2 - ConsoleUI.display_len(txt))
            print(f"  ║  {ConsoleUI.CYAN}{txt}{ConsoleUI.RESET}{pad}║")
        else:
            print(f"  ║{' '*box_w}║")

        inner    = box_w - 4
        max_text = inner - 3

        for i in range(top, top + visible):
            raw = options[i]
            if ConsoleUI.display_len(raw) > max_text:
                acc, w = [], 0
                for ch in raw:
                    cw = 2 if ConsoleUI.display_len(ch) == 2 else 1
                    if w + cw > max_text - 1:
                        break
                    acc.append(ch)
                    w += cw
                raw = "".join(acc) + "…"
            prefix = "▶  " if i == selected_index else "   "
            vtext  = prefix + raw
            pad_r  = " " * max(0, inner - ConsoleUI.display_len(vtext))
            if i == selected_index:
                print(f"  ║  {ConsoleUI.CYAN}{ConsoleUI.BOLD}{vtext}"
                      f"{ConsoleUI.RESET}{pad_r}  ║")
            else:
                print(f"  ║  {vtext}{pad_r}  ║")

        remaining = len(options) - top - visible
        if remaining > 0:
            txt = f"▼  {remaining} élément(s) plus bas"
            pad = " " * max(0, box_w - 2 - ConsoleUI.display_len(txt))
            print(f"  ║  {ConsoleUI.CYAN}{txt}{ConsoleUI.RESET}{pad}║")
        else:
            print(f"  ║{' '*box_w}║")

        print(f"  ╠{h_line}╣")
        nav     = "↑ ↓  Naviguer   ↵  Valider   Échap  Retour"
        nav_pad = " " * max(0, box_w - 2 - ConsoleUI.display_len(nav))
        print(f"  ║  {ConsoleUI.YELLOW}{nav}{ConsoleUI.RESET}{nav_pad}║")
        print(f"  ╚{h_line}╝")

    @staticmethod
    def get_key() -> Optional[str]:
        if os.name == 'nt' and msvcrt:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\xe0':
                    key = msvcrt.getch()
                    if key == b'H': return 'UP'
                    if key == b'P': return 'DOWN'
                elif key == b'\r':   return 'ENTER'
                elif key == b'\x1b': return 'ESC'
        elif tty and termios and _select:
            fd = sys.stdin.fileno()
            try:
                old = termios.tcgetattr(fd)
            except Exception:
                return None
            try:
                tty.setraw(fd)
                if _select.select([sys.stdin], [], [], 0.05)[0]:
                    ch = sys.stdin.read(1)
                    if ch == '\x1b':
                        if _select.select([sys.stdin], [], [], 0.05)[0]:
                            more = sys.stdin.read(2)
                            if more == '[A': return 'UP'
                            if more == '[B': return 'DOWN'
                        return 'ESC'
                    if ch in ('\r', '\n'): return 'ENTER'
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return None

    @staticmethod
    def navigate(options: list, title: str = "MENU", subtitle: str = "") -> int:
        if not options:
            return -1
        selected = 0
        while True:
            ConsoleUI.show_menu(options, title, selected, subtitle)
            while True:
                key = ConsoleUI.get_key()
                if key:
                    break
                time.sleep(0.03)
            if   key == 'UP':    selected = (selected - 1) % len(options)
            elif key == 'DOWN':  selected = (selected + 1) % len(options)
            elif key == 'ENTER': return selected
            elif key == 'ESC':   return -1

    @staticmethod
    def input_screen(title: str, prompt_text: str, subtitle: str = "") -> str:
        ConsoleUI.clear()
        ConsoleUI.print_logo()
        print(f"\n  {ConsoleUI.CYAN}{ConsoleUI.BOLD}{'─'*58}{ConsoleUI.RESET}")
        print(f"  {ConsoleUI.BOLD}{title}{ConsoleUI.RESET}")
        if subtitle:
            print(f"  {ConsoleUI.DIM}{subtitle}{ConsoleUI.RESET}")
        print(f"  {ConsoleUI.CYAN}{'─'*58}{ConsoleUI.RESET}\n")
        try:
            return input(f"  {ConsoleUI.YELLOW}▶  {ConsoleUI.RESET}{prompt_text} : ").strip()
        except (EOFError, OSError):
            return ""

    @staticmethod
    def result_screen(lines: list, pause: bool = True) -> None:
        ConsoleUI.clear()
        print(ConsoleUI.CYAN + "\n  " + "═"*58 + ConsoleUI.RESET)
        for line in lines:
            print(line)
        print(ConsoleUI.CYAN + "\n  " + "═"*58 + ConsoleUI.RESET)
        if pause:
            try:
                input(f"\n  {ConsoleUI.DIM}Appuyez sur Entrée pour continuer…{ConsoleUI.RESET}")
            except (EOFError, OSError):
                pass

    @staticmethod
    def info(m: str)    -> None: print(f"  {ConsoleUI.CYAN}ℹ  {ConsoleUI.RESET}{m}")
    @staticmethod
    def success(m: str) -> None: print(f"  {ConsoleUI.GREEN}✔  {ConsoleUI.RESET}{m}")
    @staticmethod
    def warn(m: str)    -> None: print(f"  {ConsoleUI.YELLOW}⚠  {ConsoleUI.RESET}{m}")
    @staticmethod
    def error(m: str)   -> None: print(f"  {ConsoleUI.RED}✖  {ConsoleUI.RESET}{m}")
    @staticmethod
    def sep()           -> None: print(f"\n  {ConsoleUI.DIM}{'─'*54}{ConsoleUI.RESET}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE ANDROID — SimpleUI (print / input classiques)
# ══════════════════════════════════════════════════════════════════════════════

class SimpleUI:
    @staticmethod
    def clear() -> None:
        os.system('clear')

    @staticmethod
    def print_logo() -> None:
        print("🌙  CO-SAMA  SCAN DOWNLOADER  🌙")
        print("=" * 40)

    @staticmethod
    def navigate(options: list, title: str = "MENU", subtitle: str = "") -> int:
        while True:
            SimpleUI.clear()
            SimpleUI.print_logo()
            print(f"\n  {title}")
            if subtitle:
                print(f"  {subtitle}")
            print()
            for i, opt in enumerate(options, 1):
                print(f"  [{i}]  {opt}")
            print("  [0]  Retour\n")
            try:
                raw = input("  Choix : ").strip()
            except (EOFError, OSError):
                return -1
            if raw in ("0", ""):
                return -1
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return idx
            print("Choix invalide.")
            time.sleep(0.5)

    @staticmethod
    def input_screen(title: str, prompt_text: str, subtitle: str = "") -> str:
        SimpleUI.clear()
        SimpleUI.print_logo()
        print(f"\n  {title}")
        if subtitle:
            print(f"  {subtitle}")
        print()
        try:
            return input(f"  {prompt_text} : ").strip()
        except (EOFError, OSError):
            return ""

    @staticmethod
    def result_screen(lines: list, pause: bool = True) -> None:
        SimpleUI.clear()
        print("=" * 40)
        for line in lines:
            print(line)
        print("=" * 40)
        if pause:
            try:
                input("\n  Appuyez sur Entrée pour continuer…")
            except (EOFError, OSError):
                pass

    @staticmethod
    def info(m: str)    -> None: print(f"ℹ  {m}")
    @staticmethod
    def success(m: str) -> None: print(f"✅ {m}")
    @staticmethod
    def warn(m: str)    -> None: print(f"⚠️  {m}")
    @staticmethod
    def error(m: str)   -> None: print(f"❌ {m}")
    @staticmethod
    def sep()           -> None: print("─" * 40)


# ── Façade UI ─────────────────────────────────────────────────────────────────
UI = SimpleUI if IS_ANDROID else ConsoleUI

# ══════════════════════════════════════════════════════════════════════════════
#  EXCEPTIONS
# ══════════════════════════════════════════════════════════════════════════════

class CoSamaError(Exception):           pass
class DomainNotFoundError(CoSamaError): pass
class ServerNotFoundError(CoSamaError): pass
class DiskSpaceError(CoSamaError):      pass

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

CONFIG_PATH = Path.home() / ".co_sama_config.json"
DEFAULT_CONFIG = {
    "max_concurrent_downloads": 5,
    "max_retries": 3,
    "retry_delay_base": 1.0,
    "request_timeout": 10,
    "inter_chapter_delay": 0.5,
    "cbz_export": False,
    "delete_after_cbz": False,
    "download_path": None,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


CONFIG = load_config()

# ══════════════════════════════════════════════════════════════════════════════
#  DATACLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MangaVersion:
    label:    str
    server:   str
    url_name: str


@dataclass
class DownloadSession:
    manga_name:    str
    manga_folder:  Path
    base_url:      str
    start_chapter: int
    cbz_export:    bool = False
    stats: dict = field(default_factory=lambda: {
        "chapters_ok": 0,
        "pages_downloaded": 0,
        "pages_skipped": 0,
        "bytes_downloaded": 0,
    })

# ══════════════════════════════════════════════════════════════════════════════
#  UTILITAIRES SYSTÈME
# ══════════════════════════════════════════════════════════════════════════════

def get_free_space_gb() -> float:
    try:
        if platform.system() == "Windows":
            _, _, free = shutil.disk_usage("C:\\")
            return free / 1024**3
        if IS_ANDROID:
            for path in [
                os.path.expanduser("~/storage/downloads"),
                os.path.expanduser("~"),
                "/storage/emulated/0",
            ]:
                if os.path.exists(path):
                    _, _, free = shutil.disk_usage(path)
                    return free / 1024**3
        st = os.statvfs("/")
        return (st.f_frsize * st.f_bavail) / 1024**3
    except Exception:
        return 999.0


def check_disk_space(min_gb: float = 0.1) -> None:
    free = get_free_space_gb()
    if free < min_gb:
        raise DiskSpaceError(
            f"Espace insuffisant : {free:.2f} GB libres, {min_gb} GB requis."
        )


def get_download_path() -> Path:
    if CONFIG.get("download_path"):
        return Path(CONFIG["download_path"])
    s = platform.system()
    if s == "Windows":
        return Path.cwd()
    if IS_ANDROID:
        p = Path(os.path.expanduser("~/storage/downloads"))
        if p.exists():
            return p
        return Path("/storage/emulated/0/Download/Scan")
    return Path.home() / "Downloads" / "Manga"


def set_title(title: str) -> None:
    if IS_ANDROID:
        return
    if platform.system() == "Windows":
        os.system(f"title {title}")
    else:
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION HTTP
# ══════════════════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _make_session() -> aiohttp.ClientSession:
    timeout   = aiohttp.ClientTimeout(total=CONFIG["request_timeout"])
    connector = aiohttp.TCPConnector(limit=CONFIG["max_concurrent_downloads"] * 2)
    return aiohttp.ClientSession(headers=HEADERS, timeout=timeout, connector=connector)

# ══════════════════════════════════════════════════════════════════════════════
#  RETRY
# ══════════════════════════════════════════════════════════════════════════════

def async_retry(max_retries: int = 3, base_delay: float = 1.0):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(base_delay * (2 ** attempt))
        return wrapper
    return decorator

# ══════════════════════════════════════════════════════════════════════════════
#  DOMAINE ACTIF
# ══════════════════════════════════════════════════════════════════════════════

async def get_active_domain(session: aiohttp.ClientSession) -> str:
    UI.info("Recherche du serveur actif…")
    patterns = [
        r'<a\s+class="btn-primary"\s+href="(https?://anime-sama\.[a-z]+)"',
        r'href="(https?://anime-sama\.(?!pw)[a-z]+)"',
    ]
    try:
        async with session.get("https://anime-sama.pw/") as resp:
            resp.raise_for_status()
            html = await resp.text()
    except Exception as e:
        raise DomainNotFoundError(f"Impossible de contacter le serveur principal : {e}")

    for pattern in patterns:
        m = re.search(pattern, html)
        if not m:
            continue
        candidate = m.group(1)
        try:
            async with session.head(candidate, allow_redirects=True) as r:
                final = str(r.url)
            if "anime-sama" in final and "anime-sama.pw" not in final:
                domain = final.split("/catalogue")[0].rstrip("/")
                UI.success("Serveur actif trouvé.")
                return f"{domain}/catalogue/"
        except Exception:
            continue

    raise DomainNotFoundError("Aucun serveur actif trouvé.")

# ══════════════════════════════════════════════════════════════════════════════
#  DÉTECTION DES SERVEURS CDN — parallèle
# ══════════════════════════════════════════════════════════════════════════════

async def _probe(session: aiohttp.ClientSession, url: str,
                 sem: asyncio.Semaphore) -> bool:
    async with sem:
        try:
            async with session.head(url, allow_redirects=True) as r:
                return r.status == 200
        except Exception:
            return False


async def find_working_servers(
    session: aiohttp.ClientSession,
    manga_name: str,
    domain: str,
    max_servers: int = 12,
) -> list:
    domain = domain.rstrip("/")
    variants = [
        ("Normal",  manga_name,                         quote(manga_name)),
        ("Normal",  manga_name.title(),                 quote(manga_name.title())),
        ("Couleur", f"{manga_name} Couleur",            quote(f"{manga_name} Couleur")),
        ("Couleur", f"{manga_name.title()} Couleur",    quote(f"{manga_name.title()} Couleur")),
    ]

    UI.info("Sondage des serveurs CDN…")
    sem   = asyncio.Semaphore(12)
    found = []
    seen_labels: set = set()

    for label, _, url_name in variants:
        if label in seen_labels:
            continue
        tasks = {
            asyncio.create_task(
                _probe(session, f"{domain}/s{n}/scans/{url_name}/1/1.jpg", sem)
            ): n
            for n in range(1, max_servers + 1)
        }
        results = await asyncio.gather(*tasks.keys(), return_exceptions=True)
        for task, ok in zip(tasks.keys(), results):
            if ok is True and label not in seen_labels:
                n = tasks[task]
                found.append(MangaVersion(label=label, server=f"s{n}", url_name=url_name))
                seen_labels.add(label)
                UI.success(f"  Version '{label}' → serveur s{n}")

    return found

# ══════════════════════════════════════════════════════════════════════════════
#  TÉLÉCHARGEMENT D'IMAGES
# ══════════════════════════════════════════════════════════════════════════════

@async_retry(max_retries=DEFAULT_CONFIG["max_retries"],
             base_delay=DEFAULT_CONFIG["retry_delay_base"])
async def download_image(session: aiohttp.ClientSession, url: str,
                         dest: Path, sem: asyncio.Semaphore) -> int:
    async with sem:
        async with session.get(url) as resp:
            if resp.status == 404:
                return 0
            resp.raise_for_status()
            data = await resp.read()
    check_disk_space(0.05)
    dest.write_bytes(data)
    return len(data)


async def image_exists(session: aiohttp.ClientSession, url: str,
                       sem: asyncio.Semaphore) -> bool:
    async with sem:
        try:
            async with session.head(url, allow_redirects=True) as r:
                return r.status == 200
        except Exception:
            return False

# ══════════════════════════════════════════════════════════════════════════════
#  CBZ
# ══════════════════════════════════════════════════════════════════════════════

def pack_cbz(chapter_folder: Path, cbz_path: Path,
             delete_source: bool = False) -> None:
    images = sorted(
        chapter_folder.glob("*.jpg"),
        key=lambda p: int(p.stem) if p.stem.isdigit() else 0,
    )
    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for img in images:
            zf.write(img, img.name)
    if delete_source and images:
        shutil.rmtree(chapter_folder)

# ══════════════════════════════════════════════════════════════════════════════
#  REPRISE LOCALE
# ══════════════════════════════════════════════════════════════════════════════

def find_last_downloaded_chapter(folder: Path) -> Optional[int]:
    if not folder.exists():
        return None
    chapters = []
    for item in folder.iterdir():
        if item.is_dir():
            m = re.match(r"Chapitre[_\s]?(\d+)", item.name, re.IGNORECASE)
            if m:
                chapters.append(int(m.group(1)))
    return max(chapters) if chapters else None


def count_local_pages(folder: Path, chapter: int) -> int:
    cf = folder / f"Chapitre_{chapter}"
    return len(list(cf.glob("*.jpg"))) if cf.exists() else 0

# ══════════════════════════════════════════════════════════════════════════════
#  TÉLÉCHARGEMENT D'UN CHAPITRE
# ══════════════════════════════════════════════════════════════════════════════

async def download_chapter(
    session: aiohttp.ClientSession,
    dl: DownloadSession,
    chapter: int,
) -> bool:
    chapter_folder = dl.manga_folder / f"Chapitre_{chapter}"
    chapter_folder.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(CONFIG["max_concurrent_downloads"])

    # ── Découverte des pages ──────────────────────────────────────────────────
    all_pages = []
    offset, batch = 1, 10
    while True:
        exists_list = await asyncio.gather(*[
            image_exists(session, f"{dl.base_url}/{chapter}/{p}.jpg", sem)
            for p in range(offset, offset + batch)
        ])
        valid = [offset + i for i, ok in enumerate(exists_list) if ok]
        all_pages.extend(valid)
        if len(valid) < batch:
            break
        offset += batch

    if not all_pages:
        return False

    total    = len(all_pages)
    existing = count_local_pages(dl.manga_folder, chapter)
    if existing:
        dl.stats["pages_skipped"] += existing
        if not IS_ANDROID:
            ConsoleUI.info(f"  {existing}/{total} pages déjà présentes, reprise…")

    pages_to_dl = [
        p for p in all_pages
        if not (chapter_folder / f"{p}.jpg").exists()
    ]

    # ── Barre de progression (PC uniquement) ──────────────────────────────────
    done_count = existing

    def _bar(done: int) -> None:
        if IS_ANDROID:
            return
        bar_len = 32
        filled  = int(bar_len * done / max(total, 1))
        bar     = "█" * filled + "░" * (bar_len - filled)
        pct     = int(100 * done / max(total, 1))
        sys.stdout.write(
            f"\r  {ConsoleUI.CYAN}[{bar}]{ConsoleUI.RESET} "
            f"{done}/{total}  ({pct}%)"
        )
        sys.stdout.flush()

    _bar(done_count)

    # ── Téléchargement parallèle ──────────────────────────────────────────────
    async def fetch(page: int) -> int:
        dest = chapter_folder / f"{page}.jpg"
        url  = f"{dl.base_url}/{chapter}/{page}.jpg"
        try:
            return await download_image(session, url, dest, sem)
        except Exception:
            return -1

    tasks = [asyncio.create_task(fetch(p)) for p in pages_to_dl]
    for coro in asyncio.as_completed(tasks):
        size = await coro
        done_count += 1
        if size > 0:
            dl.stats["pages_downloaded"] += 1
            dl.stats["bytes_downloaded"] += size
        _bar(done_count)

    if not IS_ANDROID:
        sys.stdout.write("\n")

    # ── CBZ ───────────────────────────────────────────────────────────────────
    if dl.cbz_export and total > 0:
        cbz_path = dl.manga_folder / f"Chapitre_{chapter}.cbz"
        pack_cbz(chapter_folder, cbz_path,
                 delete_source=CONFIG.get("delete_after_cbz", False))
        if not IS_ANDROID:
            ConsoleUI.info(f"  CBZ créé : {cbz_path.name}")

    return True

# ══════════════════════════════════════════════════════════════════════════════
#  INTERACTIONS UTILISATEUR
# ══════════════════════════════════════════════════════════════════════════════

def ask_start_chapter(manga_folder: Path) -> int:
    last = find_last_downloaded_chapter(manga_folder)

    if IS_ANDROID:
        if last:
            UI.info(f"Dernier chapitre détecté : {last}")
            choice = input(f"  Reprendre depuis le chapitre {last} ? (o/n) : ").strip().lower()
            if choice in ("o", "oui", "y", "yes", ""):
                return last
        raw = input("  Numéro du chapitre de départ [1] : ").strip()
        return int(raw) if raw.isdigit() else 1

    # PC
    if last:
        UI.info(f"Dernier chapitre détecté localement : Chapitre {last}")
        idx = ConsoleUI.navigate([
            f"▶  Reprendre depuis le Chapitre {last}",
            f"⏭  Continuer depuis le Chapitre {last + 1}",
            "🔢  Saisir un chapitre manuellement",
            "⏮  Tout retélécharger depuis le début",
        ], "POINT DE DÉPART")
        if idx == 0: return last
        if idx == 1: return last + 1
        if idx == 3: return 1
    else:
        UI.info("Aucun chapitre local trouvé.")
        idx = ConsoleUI.navigate([
            "🚀  Démarrer depuis le début (Chapitre 1)",
            "🔢  Saisir un chapitre de départ",
        ], "POINT DE DÉPART")
        if idx == 0: return 1

    while True:
        raw = ConsoleUI.input_screen(
            "CHAPITRE DE DÉPART", "Numéro du chapitre",
            "Entrez le numéro à partir duquel télécharger",
        )
        if raw.isdigit() and int(raw) >= 1:
            return int(raw)
        UI.warn("Numéro invalide, réessayez.")


def ask_cbz(current: bool) -> bool:
    if IS_ANDROID:
        raw = input(
            f"  Export .cbz ? (actuellement {'oui' if current else 'non'}) (o/n) : "
        ).strip().lower()
        return (raw in ("o", "oui", "y", "yes")) if raw else current

    label = "✅ Activé" if current else "⬜ Désactivé"
    idx = ConsoleUI.navigate([
        f"📦  Export .cbz : {label}  →  basculer",
        "▶  Continuer sans changer",
    ], "OPTIONS")
    return (not current) if idx == 0 else current


def choose_version(versions: list) -> MangaVersion:
    if len(versions) == 1:
        return versions[0]

    if IS_ANDROID:
        print("\nVersions disponibles :")
        for i, v in enumerate(versions, 1):
            print(f"  [{i}]  {v.label} (serveur {v.server})")
        while True:
            raw = input("  Choix : ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(versions):
                return versions[int(raw) - 1]
    else:
        labels = [f"🎨  {v.label}  (serveur {v.server})" for v in versions]
        idx = ConsoleUI.navigate(labels, "VERSIONS DISPONIBLES")
        return versions[max(idx, 0)]


def show_config_menu() -> None:
    if IS_ANDROID:
        print("\n  Config :", CONFIG)
        return
    rows = [f"  {ConsoleUI.DIM}{k} ={ConsoleUI.RESET} {ConsoleUI.BOLD}{v}{ConsoleUI.RESET}"
            for k, v in CONFIG.items()]
    ConsoleUI.result_screen(
        [f"  {ConsoleUI.CYAN}{ConsoleUI.BOLD}Configuration Co-Sama{ConsoleUI.RESET}",
         f"  {ConsoleUI.DIM}{'─'*50}{ConsoleUI.RESET}", *rows],
        pause=False,
    )
    edit = ConsoleUI.input_screen("MODIFIER", "Clé à modifier (Entrée = ignorer)").strip()
    if edit and edit in CONFIG:
        val  = ConsoleUI.input_screen(f"VALEUR — {edit}", "Nouvelle valeur").strip()
        orig = CONFIG[edit]
        try:
            if isinstance(orig, bool):   CONFIG[edit] = val.lower() in ("1","true","oui","yes")
            elif isinstance(orig, int):  CONFIG[edit] = int(val)
            elif isinstance(orig, float): CONFIG[edit] = float(val)
            else:                         CONFIG[edit] = val or None
            save_config(CONFIG)
            ConsoleUI.success("Config sauvegardée.")
        except ValueError:
            ConsoleUI.warn("Valeur invalide — ignorée.")

# ══════════════════════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE DE TÉLÉCHARGEMENT
# ══════════════════════════════════════════════════════════════════════════════

async def run_download(manga_name: str, start_chapter: int, cbz: bool) -> None:
    set_title(f"Co-Sama ✦ {manga_name}")

    manga_folder = get_download_path() / manga_name.replace(" ", "_")
    manga_folder.mkdir(parents=True, exist_ok=True)
    check_disk_space(1.0)

    async with _make_session() as session:

        active_catalogue = await get_active_domain(session)
        domain = active_catalogue.replace("/catalogue/", "").replace("/catalogue", "")

        UI.sep()
        versions = await find_working_servers(session, manga_name, domain)
        if not versions:
            raise ServerNotFoundError(
                f"Aucun serveur CDN ne répond pour « {manga_name} ».\n"
                "Vérifiez l'orthographe (majuscules, accents, espaces)."
            )

        chosen   = choose_version(versions)
        base_url = f"{domain}/{chosen.server}/scans/{chosen.url_name}"

        dl = DownloadSession(
            manga_name=manga_name,
            manga_folder=manga_folder,
            base_url=base_url,
            start_chapter=start_chapter,
            cbz_export=cbz,
        )

        UI.sep()
        if IS_ANDROID:
            print(f"📚 {manga_name}  |  {chosen.label}  |  {chosen.server}")
            print(f"📍 Départ : Chapitre {start_chapter}")
        else:
            print(
                f"  {ConsoleUI.BOLD}{ConsoleUI.CYAN}📚 {manga_name}{ConsoleUI.RESET}"
                f"   {ConsoleUI.DIM}Version :{ConsoleUI.RESET} {ConsoleUI.BOLD}{chosen.label}{ConsoleUI.RESET}"
                f"   {ConsoleUI.DIM}Serveur :{ConsoleUI.RESET} {ConsoleUI.BOLD}{chosen.server}{ConsoleUI.RESET}"
                f"   {ConsoleUI.DIM}Départ :{ConsoleUI.RESET} {ConsoleUI.BOLD}Chapitre {start_chapter}{ConsoleUI.RESET}"
            )
        UI.sep()

        # ── Boucle chapitres ──────────────────────────────────────────────────
        chapter             = start_chapter
        consecutive_missing = 0
        MAX_MISSING         = 3

        while consecutive_missing < MAX_MISSING:
            if IS_ANDROID:
                print(f"\n📖 Chapitre {chapter}…")
            else:
                print(f"\n  {ConsoleUI.BOLD}📖 Chapitre {chapter}{ConsoleUI.RESET}")

            found = await download_chapter(session, dl, chapter)

            if found:
                consecutive_missing = 0
                dl.stats["chapters_ok"] += 1
                UI.success(f"Chapitre {chapter} terminé.")
                await asyncio.sleep(CONFIG["inter_chapter_delay"])
            else:
                consecutive_missing += 1
                UI.warn(
                    f"Chapitre {chapter} introuvable "
                    f"({consecutive_missing}/{MAX_MISSING})"
                )
            chapter += 1

        # ── Résumé final ──────────────────────────────────────────────────────
        mb = dl.stats["bytes_downloaded"] / 1024**2
        UI.sep()
        if IS_ANDROID:
            print("🏁 Téléchargement terminé !")
            print(f"  Chapitres  : {dl.stats['chapters_ok']}")
            print(f"  Pages DL   : {dl.stats['pages_downloaded']}")
            print(f"  Ignorées   : {dl.stats['pages_skipped']}")
            print(f"  Transféré  : {mb:.1f} MB")
            print(f"  Dossier    : {manga_folder}")
        else:
            ConsoleUI.result_screen([
                f"  {ConsoleUI.GREEN}{ConsoleUI.BOLD}🏁 Téléchargement terminé !{ConsoleUI.RESET}",
                f"  {ConsoleUI.DIM}Chapitres téléchargés  :{ConsoleUI.RESET} {ConsoleUI.BOLD}{dl.stats['chapters_ok']}{ConsoleUI.RESET}",
                f"  {ConsoleUI.DIM}Pages téléchargées     :{ConsoleUI.RESET} {ConsoleUI.BOLD}{dl.stats['pages_downloaded']}{ConsoleUI.RESET}",
                f"  {ConsoleUI.DIM}Pages en cache (skip)  :{ConsoleUI.RESET} {ConsoleUI.BOLD}{dl.stats['pages_skipped']}{ConsoleUI.RESET}",
                f"  {ConsoleUI.DIM}Données transférées    :{ConsoleUI.RESET} {ConsoleUI.BOLD}{mb:.1f} MB{ConsoleUI.RESET}",
                f"  {ConsoleUI.DIM}Dossier                :{ConsoleUI.RESET} {str(manga_folder)}",
            ])

# ══════════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    import argparse
    p = argparse.ArgumentParser(
        description="Co-Sama v3 — Téléchargeur de scans manga"
    )
    p.add_argument("--manga",  "-m", type=str, help="Nom du manga")
    p.add_argument("--start",  "-s", type=int, help="Chapitre de départ")
    p.add_argument("--cbz",    "-z", action="store_true", help="Export .cbz")
    p.add_argument("--config", "-c", action="store_true", help="Modifier la config")
    return p.parse_args()


def main() -> None:
    set_title("Co-Sama v3")

    if not IS_ANDROID:
        ConsoleUI.enable_ansi()
        ConsoleUI.clear()
        ConsoleUI.print_logo()

    args = parse_args()

    if args.config:
        show_config_menu()
        return

    # ── Nom du manga ──────────────────────────────────────────────────────────
    if args.manga:
        manga_name = args.manga.strip().title()
    else:
        if IS_ANDROID:
            SimpleUI.clear()
            SimpleUI.print_logo()
            print()
            manga_name = input("  📚 Nom du manga : ").strip().title()
        else:
            manga_name = ""
            while True:
                idx = ConsoleUI.navigate(
                    ["📥  Télécharger un manga",
                     "⚙️   Configuration",
                     "❌  Quitter"],
                    "MENU PRINCIPAL",
                )
                if idx in (2, -1):
                    ConsoleUI.result_screen([
                        f"  {ConsoleUI.CYAN}👋  Merci d'avoir utilisé Co-Sama !{ConsoleUI.RESET}",
                        "  🌙  À bientôt !",
                    ], pause=False)
                    time.sleep(1)
                    sys.exit(0)
                if idx == 1:
                    show_config_menu()
                    ConsoleUI.clear()
                    ConsoleUI.print_logo()
                    continue
                raw = ConsoleUI.input_screen(
                    "TÉLÉCHARGER UN MANGA", "Nom du manga",
                    "Respectez les majuscules et les accents",
                )
                if raw.strip():
                    manga_name = raw.strip().title()
                    break
                ConsoleUI.warn("Nom invalide.")

    if not manga_name:
        UI.error("Nom de manga invalide.")
        sys.exit(1)

    # ── Chapitre de départ ────────────────────────────────────────────────────
    if args.start:
        start_chapter = args.start
    else:
        manga_folder  = get_download_path() / manga_name.replace(" ", "_")
        start_chapter = ask_start_chapter(manga_folder)

    # ── Export CBZ ────────────────────────────────────────────────────────────
    cbz = args.cbz or ask_cbz(CONFIG.get("cbz_export", False))

    # ── Lancement ─────────────────────────────────────────────────────────────
    try:
        asyncio.run(run_download(manga_name, start_chapter, cbz))
    except DomainNotFoundError as e:
        UI.error(f"Domaine introuvable : {e}")
        time.sleep(5)
        sys.exit(1)
    except ServerNotFoundError as e:
        UI.error(f"Serveur introuvable : {e}")
        time.sleep(5)
        sys.exit(1)
    except DiskSpaceError as e:
        UI.error(f"Espace disque : {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        if IS_ANDROID:
            print("👋 À bientôt !")
        else:
            ConsoleUI.clear()
            ConsoleUI.print_logo()
            print(f"\n  {ConsoleUI.CYAN}👋  Merci d'avoir utilisé Co-Sama !{ConsoleUI.RESET}")
            print(f"  🌙  À bientôt !\n")
        sys.exit(0)
    except Exception:
        if not IS_ANDROID:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
