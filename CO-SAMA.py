"""
╔══════════════════════════════════════════════════════════════╗
║           v2.0 — Téléchargeur de Scans Manga          ║
║   asyncio · aiohttp · ConsoleUI (PC) · SimpleUI (Android)    ║
╚══════════════════════════════════════════════════════════════╝
"""
# pylint: disable=too-many-lines

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-INSTALL DES DÉPENDANCES (doit précéder les imports tiers)
# ══════════════════════════════════════════════════════════════════════════════
import importlib
import importlib.util
import subprocess
import sys


def _ensure(package: str, import_as: str | None = None) -> None:
    """Installe *package* via pip s'il n'est pas encore importable."""
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
#  IMPORTS STANDARD
# ══════════════════════════════════════════════════════════════════════════════
# pylint: disable=wrong-import-position
import argparse
import asyncio
import json
import os
import platform
import re
import shutil
import time
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

try:
    import ctypes
except ImportError:
    ctypes = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]

try:
    import tty
    import termios
    import select as _select
except ImportError:
    tty = termios = _select = None  # type: ignore[assignment]

import aiohttp  # pylint: disable=import-error
# pylint: enable=wrong-import-position

# ══════════════════════════════════════════════════════════════════════════════
#  DÉTECTION PLATEFORME
# ══════════════════════════════════════════════════════════════════════════════


def _is_termux() -> bool:
    """Retourne True si le programme tourne dans Termux (Android)."""
    return os.name != "nt" and (
        "ANDROID_STORAGE" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
    )


IS_ANDROID: bool = _is_termux()

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTE GLOBALE
# ══════════════════════════════════════════════════════════════════════════════

MAX_CONSECUTIVE_MISSING: int = 3  # chapitres absents avant arrêt automatique

# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE PC — ConsoleUI (flèches, logo ASCII, menus interactifs)
# ══════════════════════════════════════════════════════════════════════════════


class ConsoleUI:
    """Interface terminal avec couleurs ANSI, navigation clavier et logo ASCII."""

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
        """Active les codes ANSI sur les consoles Windows."""
        if os.name == 'nt' and ctypes:
            try:
                ctypes.windll.kernel32.SetConsoleMode(
                    ctypes.windll.kernel32.GetStdHandle(-11), 7
                )
            except OSError:
                pass

    @staticmethod
    def clear() -> None:
        """Efface l'écran du terminal."""
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def display_len(text: str) -> int:
        """Retourne la largeur visible en colonnes de *text* (gère les glyphes larges)."""
        count, i = 0, 0
        while i < len(text):
            code_point = ord(text[i])
            if code_point in (0xFE0E, 0xFE0F, 0x200D, 0x20E3):
                i += 1
                continue
            if 0x0300 <= code_point <= 0x036F:
                i += 1
                continue
            if 0x1F3FB <= code_point <= 0x1F3FF:
                i += 1
                continue
            is_wide = (
                0x1F000 <= code_point <= 0x1FFFF
                or 0x2600 <= code_point <= 0x27BF
                or 0x2B00 <= code_point <= 0x2BFF
                or 0xFE30 <= code_point <= 0xFE4F
                or 0x2E80 <= code_point <= 0x2EFF
                or 0x3000 <= code_point <= 0x9FFF
                or 0xF900 <= code_point <= 0xFAFF
                or 0xAC00 <= code_point <= 0xD7AF
            )
            if is_wide:
                count += 2
                j = i + 1
                while j < len(text):
                    ncp = ord(text[j])
                    if (ncp in (0x200D, 0xFE0E, 0xFE0F, 0x20E3)
                            or 0x1F3FB <= ncp <= 0x1F3FF
                            or 0x1F000 <= ncp <= 0x1FFFF
                            or 0x2600 <= ncp <= 0x27BF):
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
        """Affiche le logo ASCII en couleur CYAN."""
        print(ConsoleUI.CYAN + ConsoleUI.ASCII_LOGO + ConsoleUI.RESET)

    # ── Helpers internes de show_menu ─────────────────────────────────────────

    @staticmethod
    def _truncate_option(text: str, max_width: int) -> str:
        """Tronque *text* à *max_width* colonnes visibles en ajoutant '…'."""
        if ConsoleUI.display_len(text) <= max_width:
            return text
        acc, width = [], 0
        for char in text:
            char_w = 2 if ConsoleUI.display_len(char) == 2 else 1
            if width + char_w > max_width - 1:
                break
            acc.append(char)
            width += char_w
        return "".join(acc) + "…"

    @staticmethod
    def _render_scroll_hint(direction: str, count: int, box_w: int) -> None:
        """Affiche un indicateur de défilement dans le cadre du menu."""
        icon  = "▲" if direction == "up" else "▼"
        label = "haut" if direction == "up" else "bas"
        txt   = f"{icon}  {count} élément(s) plus {label}"
        pad   = " " * max(0, box_w - 2 - ConsoleUI.display_len(txt))
        print(f"  ║  {ConsoleUI.CYAN}{txt}{ConsoleUI.RESET}{pad}║")

    @staticmethod
    def _render_menu_item(
        text: str,
        is_selected: bool,
        inner: int,
    ) -> None:
        """Affiche une ligne d'option dans le cadre du menu."""
        prefix = "▶  " if is_selected else "   "
        vtext  = prefix + text
        pad_r  = " " * max(0, inner - ConsoleUI.display_len(vtext))
        if is_selected:
            print(
                f"  ║  {ConsoleUI.CYAN}{ConsoleUI.BOLD}{vtext}"
                f"{ConsoleUI.RESET}{pad_r}  ║"
            )
        else:
            print(f"  ║  {vtext}{pad_r}  ║")

    @staticmethod
    def _render_menu_title(h_line: str, box_w: int, title: str) -> None:
        """Affiche le cadre titre du menu (bordure haute + titre centré)."""
        tlen   = ConsoleUI.display_len(title)
        tpad_l = max(0, (box_w - tlen) // 2)
        tpad_r = max(0, box_w - tlen - tpad_l)
        print(f"  ╔{h_line}╗")
        print(
            f"  ║{' ' * tpad_l}{ConsoleUI.BOLD}{ConsoleUI.CYAN}{title}"
            f"{ConsoleUI.RESET}{' ' * tpad_r}║"
        )
        print(f"  ╠{h_line}╣")

    @staticmethod
    def _render_menu_footer(h_line: str, box_w: int) -> None:
        """Affiche le pied de cadre avec les touches de navigation."""
        nav     = "↑ ↓  Naviguer   ↵  Valider   Échap  Retour"
        nav_pad = " " * max(0, box_w - 2 - ConsoleUI.display_len(nav))
        print(f"  ╠{h_line}╣")
        print(f"  ║  {ConsoleUI.YELLOW}{nav}{ConsoleUI.RESET}{nav_pad}║")
        print(f"  ╚{h_line}╝")

    @staticmethod
    def show_menu(
        options: list,
        title: str = "MENU",
        selected_index: int = 0,
        subtitle: str = "",
    ) -> None:
        """Affiche un menu plein écran navigable avec cadre Unicode."""
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
        h_line  = "═" * box_w

        ConsoleUI._render_menu_title(h_line, box_w, title)

        if top > 0:
            ConsoleUI._render_scroll_hint("up", top, box_w)
        else:
            print(f"  ║{' ' * box_w}║")

        inner    = box_w - 4
        max_text = inner - 3
        for pos in range(top, top + visible):
            raw = ConsoleUI._truncate_option(options[pos], max_text)
            ConsoleUI._render_menu_item(raw, pos == selected_index, inner)

        remaining = len(options) - top - visible
        if remaining > 0:
            ConsoleUI._render_scroll_hint("down", remaining, box_w)
        else:
            print(f"  ║{' ' * box_w}║")

        ConsoleUI._render_menu_footer(h_line, box_w)

    # ── Helpers de lecture clavier ────────────────────────────────────────────

    @staticmethod
    def _get_key_windows() -> Optional[str]:
        """Lit une touche sur Windows via msvcrt."""
        if not (msvcrt and msvcrt.kbhit()):
            return None
        key = msvcrt.getch()
        if key == b'\xe0':
            arrow = msvcrt.getch()
            return 'UP' if arrow == b'H' else ('DOWN' if arrow == b'P' else None)
        return {b'\r': 'ENTER', b'\x1b': 'ESC'}.get(key)

    @staticmethod
    def _get_key_unix() -> Optional[str]:
        """Lit une touche sur UNIX/Linux via termios."""
        if not (tty and termios and _select):
            return None
        fd = sys.stdin.fileno()
        try:
            old_attrs = termios.tcgetattr(fd)
        except termios.error:
            return None
        result: Optional[str] = None
        try:
            tty.setraw(fd)
            if _select.select([sys.stdin], [], [], 0.05)[0]:
                char = sys.stdin.read(1)
                if char == '\x1b':
                    if _select.select([sys.stdin], [], [], 0.05)[0]:
                        seq = sys.stdin.read(2)
                        result = 'UP' if seq == '[A' else (
                            'DOWN' if seq == '[B' else None
                        )
                    else:
                        result = 'ESC'
                elif char in ('\r', '\n'):
                    result = 'ENTER'
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        return result

    @staticmethod
    def get_key() -> Optional[str]:
        """Retourne la prochaine touche pressée sous forme de chaîne, ou None."""
        if os.name == 'nt':
            return ConsoleUI._get_key_windows()
        return ConsoleUI._get_key_unix()

    @staticmethod
    def navigate(
        options: list,
        title: str = "MENU",
        subtitle: str = "",
    ) -> int:
        """Affiche *options* et retourne l'index choisi (-1 si Échap)."""
        if not options:
            return -1
        selected = 0
        while True:
            ConsoleUI.show_menu(options, title, selected, subtitle)
            key: Optional[str] = None
            while not key:
                key = ConsoleUI.get_key()
                time.sleep(0.03)
            if key == 'UP':
                selected = (selected - 1) % len(options)
            elif key == 'DOWN':
                selected = (selected + 1) % len(options)
            elif key == 'ENTER':
                return selected
            elif key == 'ESC':
                return -1

    @staticmethod
    def input_screen(
        title: str,
        prompt_text: str,
        subtitle: str = "",
    ) -> str:
        """Efface l'écran, affiche un prompt et retourne la saisie."""
        ConsoleUI.clear()
        ConsoleUI.print_logo()
        print(f"\n  {ConsoleUI.CYAN}{ConsoleUI.BOLD}{'─' * 58}{ConsoleUI.RESET}")
        print(f"  {ConsoleUI.BOLD}{title}{ConsoleUI.RESET}")
        if subtitle:
            print(f"  {ConsoleUI.DIM}{subtitle}{ConsoleUI.RESET}")
        print(f"  {ConsoleUI.CYAN}{'─' * 58}{ConsoleUI.RESET}\n")
        try:
            return input(
                f"  {ConsoleUI.YELLOW}▶  {ConsoleUI.RESET}{prompt_text} : "
            ).strip()
        except (EOFError, OSError):
            return ""

    @staticmethod
    def result_screen(lines: list, pause: bool = True) -> None:
        """Affiche un écran de résultat avec pause optionnelle."""
        ConsoleUI.clear()
        print(ConsoleUI.CYAN + "\n  " + "═" * 58 + ConsoleUI.RESET)
        for line in lines:
            print(line)
        print(ConsoleUI.CYAN + "\n  " + "═" * 58 + ConsoleUI.RESET)
        if pause:
            try:
                input(
                    f"\n  {ConsoleUI.DIM}Appuyez sur Entrée pour continuer…"
                    f"{ConsoleUI.RESET}"
                )
            except (EOFError, OSError):
                pass

    @staticmethod
    def info(msg: str) -> None:
        """Affiche un message informatif."""
        print(f"  {ConsoleUI.CYAN}ℹ  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def success(msg: str) -> None:
        """Affiche un message de succès."""
        print(f"  {ConsoleUI.GREEN}✔  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def warn(msg: str) -> None:
        """Affiche un avertissement."""
        print(f"  {ConsoleUI.YELLOW}⚠  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def error(msg: str) -> None:
        """Affiche un message d'erreur."""
        print(f"  {ConsoleUI.RED}✖  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def sep() -> None:
        """Affiche un séparateur horizontal."""
        print(f"\n  {ConsoleUI.DIM}{'─' * 54}{ConsoleUI.RESET}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE ANDROID — SimpleUI (print / input classiques)
# ══════════════════════════════════════════════════════════════════════════════


class SimpleUI:
    """Interface texte minimaliste pour Android/Termux."""

    @staticmethod
    def clear() -> None:
        """Efface l'écran."""
        os.system('clear')

    @staticmethod
    def print_logo() -> None:
        """Affiche un logo compact en texte brut."""
        print("🌙  CO-SAMA  SCAN DOWNLOADER  🌙")
        print("=" * 40)

    @staticmethod
    def navigate(
        options: list,
        title: str = "MENU",
        subtitle: str = "",
    ) -> int:
        """Affiche un menu numéroté et retourne l'index choisi (-1 = retour)."""
        while True:
            SimpleUI.clear()
            SimpleUI.print_logo()
            print(f"\n  {title}")
            if subtitle:
                print(f"  {subtitle}")
            print()
            for idx, opt in enumerate(options, 1):
                print(f"  [{idx}]  {opt}")
            print("  [0]  Retour\n")
            try:
                raw = input("  Choix : ").strip()
            except (EOFError, OSError):
                return -1
            if raw in ("0", ""):
                return -1
            if raw.isdigit():
                choice = int(raw) - 1
                if 0 <= choice < len(options):
                    return choice
            print("Choix invalide.")
            time.sleep(0.5)

    @staticmethod
    def input_screen(
        title: str,
        prompt_text: str,
        subtitle: str = "",
    ) -> str:
        """Affiche un prompt et retourne la saisie de l'utilisateur."""
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
        """Affiche un écran de résultat avec pause optionnelle."""
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
    def info(msg: str) -> None:
        """Affiche un message informatif."""
        print(f"ℹ  {msg}")

    @staticmethod
    def success(msg: str) -> None:
        """Affiche un message de succès."""
        print(f"✅ {msg}")

    @staticmethod
    def warn(msg: str) -> None:
        """Affiche un avertissement."""
        print(f"⚠️  {msg}")

    @staticmethod
    def error(msg: str) -> None:
        """Affiche un message d'erreur."""
        print(f"❌ {msg}")

    @staticmethod
    def sep() -> None:
        """Affiche un séparateur horizontal."""
        print("─" * 40)


# ── Façade UI ─────────────────────────────────────────────────────────────────
UI = SimpleUI if IS_ANDROID else ConsoleUI

# ══════════════════════════════════════════════════════════════════════════════
#  EXCEPTIONS
# ══════════════════════════════════════════════════════════════════════════════


class CoSamaError(Exception):
    """Exception de base pour Co-Sama."""


class DomainNotFoundError(CoSamaError):
    """Levée quand le domaine actif anime-sama est introuvable."""


class ServerNotFoundError(CoSamaError):
    """Levée quand aucun serveur CDN ne répond pour le manga demandé."""


class DiskSpaceError(CoSamaError):
    """Levée quand l'espace disque disponible est insuffisant."""


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

CONFIG_PATH = Path.home() / ".co_sama_config.json"
DEFAULT_CONFIG: dict = {
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
    """Charge la configuration depuis le disque, retombe sur les défauts si erreur."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as fh:
                return {**DEFAULT_CONFIG, **json.load(fh)}
        except (OSError, json.JSONDecodeError):
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    """Persiste *cfg* sur le disque. Ignore silencieusement les erreurs d'écriture."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except OSError:
        pass


CONFIG = load_config()

# ── Domaine actif (cache global rempli au lancement) ──────────────────────────
_CACHED_DOMAIN: Optional[str] = None

# ── Lien BD Viewer (lecteur CBZ Android recommandé) ──────────────────────────
BD_VIEWER_URL = (
    "https://play.google.com/store/apps/details?id=org.kill.geek.bdviewer"
)

# ── Descriptions et conseils pour chaque clé de config ───────────────────────
CONFIG_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "max_concurrent_downloads": (
        "Téléchargements simultanés",
        "Nombre d'images téléchargées en parallèle (conseillé : 3–8)",
    ),
    "max_retries": (
        "Tentatives max par image",
        "Nombre de ré-essais en cas d'échec réseau (défaut : 3)",
    ),
    "retry_delay_base": (
        "Délai de retry (secondes)",
        "Délai de base exponentiel entre deux tentatives (défaut : 1.0)",
    ),
    "request_timeout": (
        "Timeout requête (secondes)",
        "Durée max d'attente par requête HTTP (défaut : 10)",
    ),
    "inter_chapter_delay": (
        "Pause entre chapitres (secondes)",
        "Temps d'attente entre deux chapitres consécutifs (défaut : 0.5)",
    ),
    "cbz_export": (
        "Export .cbz automatique",
        "Compresse chaque chapitre en archive .cbz après DL (true/false)",
    ),
    "delete_after_cbz": (
        "Supprimer dossier après export CBZ",
        "Efface les images sources une fois le .cbz créé (true/false)",
    ),
    "download_path": (
        "Dossier de téléchargement",
        "Chemin absolu personnalisé — vide = dossier par défaut",
    ),
}

# ══════════════════════════════════════════════════════════════════════════════
#  DATACLASSES
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class MangaVersion:
    """Représente une combinaison serveur/variante pour un manga."""

    label:    str
    server:   str
    url_name: str


@dataclass
class DownloadSession:
    """Contient tout l'état d'une session de téléchargement active."""

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
    """Retourne l'espace disque disponible en GB (999.0 en cas d'erreur)."""
    try:
        if platform.system() == "Windows":
            _, _, free = shutil.disk_usage("C:\\")
            return free / 1024 ** 3
        if IS_ANDROID:
            for path in [
                os.path.expanduser("~/storage/downloads"),
                os.path.expanduser("~"),
                "/storage/emulated/0",
            ]:
                if os.path.exists(path):
                    _, _, free = shutil.disk_usage(path)
                    return free / 1024 ** 3
        stat = os.statvfs("/")
        return (stat.f_frsize * stat.f_bavail) / 1024 ** 3
    except OSError:
        return 999.0


def check_disk_space(min_gb: float = 0.1) -> None:
    """Lève DiskSpaceError si l'espace libre est inférieur à *min_gb*."""
    free = get_free_space_gb()
    if free < min_gb:
        raise DiskSpaceError(
            f"Espace insuffisant : {free:.2f} GB libres, {min_gb} GB requis."
        )


def get_download_path() -> Path:
    """Retourne le dossier de téléchargement configuré ou celui par défaut."""
    if CONFIG.get("download_path"):
        return Path(CONFIG["download_path"])
    system = platform.system()
    if system == "Windows":
        return Path.cwd()
    if IS_ANDROID:
        android_dl = Path(os.path.expanduser("~/storage/downloads"))
        if android_dl.exists():
            return android_dl
        return Path("/storage/emulated/0/Download/Scan")
    return Path.home() / "Downloads" / "Manga"


def set_title(title: str) -> None:
    """Définit le titre de la fenêtre terminal (no-op sur Android)."""
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
    """Crée une ClientSession aiohttp configurée."""
    timeout   = aiohttp.ClientTimeout(total=CONFIG["request_timeout"])
    connector = aiohttp.TCPConnector(
        limit=CONFIG["max_concurrent_downloads"] * 2
    )
    return aiohttp.ClientSession(
        headers=HEADERS, timeout=timeout, connector=connector
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RETRY
# ══════════════════════════════════════════════════════════════════════════════


def async_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Décorateur : relance une coroutine avec back-off exponentiel."""
    def decorator(func):
        """Décorateur interne."""
        async def wrapper(*args, **kwargs):
            """Wrapper avec logique de retry."""
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(base_delay * (2 ** attempt))
            return None
        return wrapper
    return decorator


# ══════════════════════════════════════════════════════════════════════════════
#  DOMAINE ACTIF
# ══════════════════════════════════════════════════════════════════════════════


async def get_active_domain(session: aiohttp.ClientSession) -> str:
    """Résout et retourne l'URL de base du catalogue anime-sama actif."""
    UI.info("Recherche du serveur actif…")
    patterns = [
        r'<a\s+class="btn-primary"\s+href="(https?://anime-sama\.[a-z]+)"',
        r'href="(https?://anime-sama\.(?!pw)[a-z]+)"',
    ]
    try:
        async with session.get("https://anime-sama.pw/") as resp:
            resp.raise_for_status()
            html = await resp.text()
    except aiohttp.ClientError as exc:
        raise DomainNotFoundError(
            "Impossible de contacter le serveur principal."
        ) from exc

    for pattern in patterns:
        match = re.search(pattern, html)
        if not match:
            continue
        candidate = match.group(1)
        try:
            async with session.head(candidate, allow_redirects=True) as resp:
                final = str(resp.url)
            if "anime-sama" in final and "anime-sama.pw" not in final:
                domain = final.split("/catalogue", maxsplit=1)[0].rstrip("/")
                UI.success("Serveur actif trouvé.")
                return f"{domain}/catalogue/"
        except aiohttp.ClientError:
            continue

    raise DomainNotFoundError("Aucun serveur actif trouvé.")


async def startup_domain_check() -> Optional[str]:
    """Vérifie le domaine actif au lancement et met à jour _CACHED_DOMAIN."""
    # pylint: disable=global-statement
    global _CACHED_DOMAIN
    async with _make_session() as session:
        try:
            domain = await get_active_domain(session)
            _CACHED_DOMAIN = domain
            return domain
        except DomainNotFoundError:
            return None


# ══════════════════════════════════════════════════════════════════════════════
#  DÉTECTION DES SERVEURS CDN — parallèle
# ══════════════════════════════════════════════════════════════════════════════


async def _probe(
    session: aiohttp.ClientSession,
    url: str,
    sem: asyncio.Semaphore,
) -> bool:
    """Retourne True si *url* répond avec HTTP 200."""
    async with sem:
        try:
            async with session.head(url, allow_redirects=True) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False


async def find_working_servers(
    session: aiohttp.ClientSession,
    manga_name: str,
    domain: str,
    max_servers: int = 12,
) -> list:
    """Sonde les serveurs CDN en parallèle et retourne les MangaVersion trouvés."""
    domain = domain.rstrip("/")
    variants = [
        ("Normal",  manga_name,                quote(manga_name)),
        ("Normal",  manga_name.title(),         quote(manga_name.title())),
        ("Couleur", f"{manga_name} Couleur",    quote(f"{manga_name} Couleur")),
        (
            "Couleur",
            f"{manga_name.title()} Couleur",
            quote(f"{manga_name.title()} Couleur"),
        ),
    ]

    UI.info("Sondage des serveurs CDN…")
    sem: asyncio.Semaphore = asyncio.Semaphore(12)
    found: list            = []
    seen_labels: set       = set()

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
                server_n = tasks[task]
                found.append(
                    MangaVersion(
                        label=label,
                        server=f"s{server_n}",
                        url_name=url_name,
                    )
                )
                seen_labels.add(label)
                UI.success(f"  Version '{label}' → serveur s{server_n}")

    return found


# ══════════════════════════════════════════════════════════════════════════════
#  TÉLÉCHARGEMENT D'IMAGES
# ══════════════════════════════════════════════════════════════════════════════


@async_retry(
    max_retries=DEFAULT_CONFIG["max_retries"],
    base_delay=DEFAULT_CONFIG["retry_delay_base"],
)
async def download_image(
    session: aiohttp.ClientSession,
    url: str,
    dest: Path,
    sem: asyncio.Semaphore,
) -> int:
    """Télécharge *url* dans *dest* et retourne le nombre d'octets écrits."""
    async with sem:
        async with session.get(url) as resp:
            if resp.status == 404:
                return 0
            resp.raise_for_status()
            data = await resp.read()
    check_disk_space(0.05)
    dest.write_bytes(data)
    return len(data)


async def image_exists(
    session: aiohttp.ClientSession,
    url: str,
    sem: asyncio.Semaphore,
) -> bool:
    """Retourne True si *url* est accessible avec HTTP 200."""
    async with sem:
        try:
            async with session.head(url, allow_redirects=True) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False


# ══════════════════════════════════════════════════════════════════════════════
#  CBZ
# ══════════════════════════════════════════════════════════════════════════════


def pack_cbz(
    chapter_folder: Path,
    cbz_path: Path,
    delete_source: bool = False,
) -> None:
    """Compresse toutes les images JPEG de *chapter_folder* en archive CBZ."""
    images = sorted(
        chapter_folder.glob("*.jpg"),
        key=lambda p: int(p.stem) if p.stem.isdigit() else 0,
    )
    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for img in images:
            archive.write(img, img.name)
    if delete_source and images:
        shutil.rmtree(chapter_folder)


# ══════════════════════════════════════════════════════════════════════════════
#  REPRISE LOCALE
# ══════════════════════════════════════════════════════════════════════════════


def find_last_downloaded_chapter(folder: Path) -> Optional[int]:
    """Retourne le numéro du dernier chapitre trouvé dans *folder*, ou None."""
    if not folder.exists():
        return None
    chapters = []
    for item in folder.iterdir():
        if item.is_dir():
            match = re.match(
                r"Chapitre[_\s]?(\d+)", item.name, re.IGNORECASE
            )
            if match:
                chapters.append(int(match.group(1)))
    return max(chapters) if chapters else None


def count_local_pages(folder: Path, chapter: int) -> int:
    """Retourne le nombre de fichiers JPEG déjà téléchargés pour *chapter*."""
    chapter_dir = folder / f"Chapitre_{chapter}"
    return len(list(chapter_dir.glob("*.jpg"))) if chapter_dir.exists() else 0


# ══════════════════════════════════════════════════════════════════════════════
#  BARRE DE PROGRESSION (PC)
# ══════════════════════════════════════════════════════════════════════════════


def _draw_progress_bar(done: int, total: int) -> None:
    """Réécrit la ligne courante du terminal avec une barre de progression (PC)."""
    if IS_ANDROID:
        return
    bar_len = 32
    filled  = int(bar_len * done / max(total, 1))
    blocks  = "█" * filled + "░" * (bar_len - filled)
    pct     = int(100 * done / max(total, 1))
    sys.stdout.write(
        f"\r  {ConsoleUI.CYAN}[{blocks}]{ConsoleUI.RESET} "
        f"{done}/{total}  ({pct}%)"
    )
    sys.stdout.flush()


# ══════════════════════════════════════════════════════════════════════════════
#  DÉCOUVERTE DES PAGES
# ══════════════════════════════════════════════════════════════════════════════


async def _discover_pages(
    session: aiohttp.ClientSession,
    dl: DownloadSession,
    chapter: int,
    sem: asyncio.Semaphore,
) -> list:
    """Sonde les URLs de pages par lots et retourne la liste des numéros existants."""
    all_pages: list = []
    offset, batch   = 1, 10
    while True:
        exists_list = await asyncio.gather(*[
            image_exists(
                session,
                f"{dl.base_url}/{chapter}/{page}.jpg",
                sem,
            )
            for page in range(offset, offset + batch)
        ])
        valid = [offset + idx for idx, ok in enumerate(exists_list) if ok]
        all_pages.extend(valid)
        if len(valid) < batch:
            break
        offset += batch
    return all_pages


# ══════════════════════════════════════════════════════════════════════════════
#  TÉLÉCHARGEMENT D'UN CHAPITRE
# ══════════════════════════════════════════════════════════════════════════════


async def download_chapter(
    session: aiohttp.ClientSession,
    dl: DownloadSession,
    chapter: int,
) -> bool:
    """Télécharge toutes les pages de *chapter*. Retourne False si inexistant."""
    chapter_folder = dl.manga_folder / f"Chapitre_{chapter}"
    chapter_folder.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(CONFIG["max_concurrent_downloads"])

    all_pages = await _discover_pages(session, dl, chapter, sem)
    if not all_pages:
        return False

    total    = len(all_pages)
    existing = count_local_pages(dl.manga_folder, chapter)
    if existing:
        dl.stats["pages_skipped"] += existing
        if not IS_ANDROID:
            ConsoleUI.info(
                f"  {existing}/{total} pages déjà présentes, reprise…"
            )

    pages_to_dl = [
        p for p in all_pages
        if not (chapter_folder / f"{p}.jpg").exists()
    ]

    done_count = existing
    _draw_progress_bar(done_count, total)

    async def _fetch(page: int) -> int:
        dest = chapter_folder / f"{page}.jpg"
        url  = f"{dl.base_url}/{chapter}/{page}.jpg"
        try:
            return await download_image(session, url, dest, sem)
        except aiohttp.ClientError:
            return -1

    tasks = [asyncio.create_task(_fetch(p)) for p in pages_to_dl]
    for coro in asyncio.as_completed(tasks):
        size = await coro
        done_count += 1
        if size > 0:
            dl.stats["pages_downloaded"] += 1
            dl.stats["bytes_downloaded"] += size
        _draw_progress_bar(done_count, total)

    if not IS_ANDROID:
        sys.stdout.write("\n")

    if dl.cbz_export and total > 0:
        cbz_path = dl.manga_folder / f"Chapitre_{chapter}.cbz"
        pack_cbz(
            chapter_folder,
            cbz_path,
            delete_source=CONFIG.get("delete_after_cbz", False),
        )
        if not IS_ANDROID:
            ConsoleUI.info(f"  CBZ créé : {cbz_path.name}")

    return True


# ══════════════════════════════════════════════════════════════════════════════
#  INTERACTIONS UTILISATEUR — choix du chapitre de départ
# ══════════════════════════════════════════════════════════════════════════════


def _ask_start_chapter_android(last: Optional[int]) -> int:
    """Demande le chapitre de départ en mode Android."""
    if last:
        UI.info(f"Dernier chapitre détecté : {last}")
        choice = input(
            f"  Reprendre depuis le chapitre {last} ? (o/n) : "
        ).strip().lower()
        if choice in ("o", "oui", "y", "yes", ""):
            return last
    raw = input("  Numéro du chapitre de départ [1] : ").strip()
    return int(raw) if raw.isdigit() else 1


def _ask_start_chapter_pc(last: Optional[int]) -> int:
    """Demande le chapitre de départ via le menu PC."""
    if last:
        UI.info(f"Dernier chapitre détecté localement : Chapitre {last}")
        idx = ConsoleUI.navigate([
            f"▶  Reprendre depuis le Chapitre {last}",
            f"⏭  Continuer depuis le Chapitre {last + 1}",
            "🔢  Saisir un chapitre manuellement",
            "⏮  Tout retélécharger depuis le début",
        ], "POINT DE DÉPART")
        if idx == 0:
            return last
        if idx == 1:
            return last + 1
        if idx == 3:
            return 1
    else:
        UI.info("Aucun chapitre local trouvé.")
        idx = ConsoleUI.navigate([
            "🚀  Démarrer depuis le début (Chapitre 1)",
            "🔢  Saisir un chapitre de départ",
        ], "POINT DE DÉPART")
        if idx == 0:
            return 1

    while True:
        raw = ConsoleUI.input_screen(
            "CHAPITRE DE DÉPART",
            "Numéro du chapitre",
            "Entrez le numéro à partir duquel télécharger",
        )
        if raw.isdigit() and int(raw) >= 1:
            return int(raw)
        UI.warn("Numéro invalide, réessayez.")


def ask_start_chapter(manga_folder: Path) -> int:
    """Retourne le numéro du chapitre à partir duquel télécharger."""
    last = find_last_downloaded_chapter(manga_folder)
    if IS_ANDROID:
        return _ask_start_chapter_android(last)
    return _ask_start_chapter_pc(last)


def ask_cbz(current: bool) -> bool:
    """Demande si l'export .cbz est souhaité et retourne la valeur choisie."""
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
    """Retourne la MangaVersion choisie par l'utilisateur."""
    if len(versions) == 1:
        return versions[0]

    if IS_ANDROID:
        print("\nVersions disponibles :")
        for i, ver in enumerate(versions, 1):
            print(f"  [{i}]  {ver.label} (serveur {ver.server})")
        while True:
            raw = input("  Choix : ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(versions):
                return versions[int(raw) - 1]

    labels = [f"🎨  {ver.label}  (serveur {ver.server})" for ver in versions]
    idx = ConsoleUI.navigate(labels, "VERSIONS DISPONIBLES")
    return versions[max(idx, 0)]


# ══════════════════════════════════════════════════════════════════════════════
#  MENU CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════


def _fmt_config_val(value) -> str:
    """Formate une valeur de configuration pour l'affichage."""
    if value is None:
        return "(défaut)"
    if isinstance(value, bool):
        return "✅ oui" if value else "⬜ non"
    return str(value)


def _apply_config_value(key: str, raw_val: str) -> bool:
    """
    Parse et stocke *raw_val* pour *key* dans CONFIG.

    Retourne True si succès, False si la valeur est invalide.
    """
    orig = CONFIG[key]
    try:
        if isinstance(orig, bool):
            CONFIG[key] = raw_val.lower() in ("1", "true", "oui", "yes")
        elif isinstance(orig, int):
            CONFIG[key] = int(raw_val)
        elif isinstance(orig, float):
            CONFIG[key] = float(raw_val)
        else:
            CONFIG[key] = raw_val or None
        save_config(CONFIG)
        return True
    except ValueError:
        return False


def _show_config_android() -> None:
    """Menu de configuration pour Android/Termux."""
    keys = list(CONFIG_DESCRIPTIONS.keys())
    while True:
        SimpleUI.clear()
        SimpleUI.print_logo()
        print("\n  ⚙️  CONFIGURATION\n")
        for i, key in enumerate(keys, 1):
            desc, _ = CONFIG_DESCRIPTIONS[key]
            print(f"  [{i:2}]  {desc}")
            print(f"        Valeur : {_fmt_config_val(CONFIG.get(key))}")
        print("\n  [0]  ↩ Retour\n")

        raw = input("  Clé à modifier : ").strip()
        if raw in ("0", ""):
            return
        if not raw.isdigit():
            print("  Choix invalide.")
            time.sleep(0.5)
            continue

        choice = int(raw) - 1
        if not 0 <= choice < len(keys):
            continue

        key = keys[choice]
        desc, hint = CONFIG_DESCRIPTIONS[key]
        print(f"\n  {desc}")
        print(f"  Actuel : {_fmt_config_val(CONFIG.get(key))}")
        print(f"  Aide   : {hint}")
        if key in ("cbz_export", "delete_after_cbz"):
            print("\n  📖 Lecteur CBZ recommandé (Android) :")
            print("     BD Viewer (Play Store)")

        new_val = input("\n  Nouvelle valeur : ").strip()
        if new_val:
            if _apply_config_value(key, new_val):
                print(f"  ✅ '{key}' → {_fmt_config_val(CONFIG[key])}")
            else:
                print("  ⚠️  Valeur invalide — ignorée.")
            time.sleep(1)


def _show_config_pc() -> None:
    """Menu de configuration pour PC (navigation par flèches)."""
    keys = list(CONFIG_DESCRIPTIONS.keys())
    while True:
        options = [
            f"{CONFIG_DESCRIPTIONS[k][0]}   [{_fmt_config_val(CONFIG.get(k))}]"
            for k in keys
        ]
        options.append("↩  Retour au menu principal")

        idx = ConsoleUI.navigate(
            options,
            "⚙️  CONFIGURATION",
            subtitle="Sélectionnez un paramètre pour le modifier",
        )
        if idx in (-1, len(keys)):
            return

        key        = keys[idx]
        desc, hint = CONFIG_DESCRIPTIONS[key]
        cbz_tip    = ""
        if key in ("cbz_export", "delete_after_cbz"):
            cbz_tip = (
                f"\n  {ConsoleUI.CYAN}📖 Lecteur CBZ recommandé (Android) :"
                f"{ConsoleUI.RESET} BD Viewer (Play Store)"
            )

        new_val = ConsoleUI.input_screen(
            f"MODIFIER — {desc}",
            "Nouvelle valeur (Entrée = annuler)",
            f"Actuel : {_fmt_config_val(CONFIG[key])}  |  {hint}{cbz_tip}",
        ).strip()

        if not new_val:
            continue
        if _apply_config_value(key, new_val):
            ConsoleUI.success(
                f"'{key}' mis à jour → {_fmt_config_val(CONFIG[key])}"
            )
        else:
            ConsoleUI.warn("Valeur invalide — modification ignorée.")
        time.sleep(0.8)


def show_config_menu() -> None:
    """Point d'entrée du menu de configuration (dispatche selon la plateforme)."""
    if IS_ANDROID:
        _show_config_android()
    else:
        _show_config_pc()


# ══════════════════════════════════════════════════════════════════════════════
#  RÉSUMÉ DE SESSION & EN-TÊTE
# ══════════════════════════════════════════════════════════════════════════════


def _print_session_header(
    dl: DownloadSession,
    chosen: MangaVersion,
    start_chapter: int,
) -> None:
    """Affiche les infos de session (manga, version, serveur, chapitre de départ)."""
    if IS_ANDROID:
        print(f"📚 {dl.manga_name}  |  {chosen.label}  |  {chosen.server}")
        print(f"📍 Départ : Chapitre {start_chapter}")
        return
    print(
        f"  {ConsoleUI.BOLD}{ConsoleUI.CYAN}📚 {dl.manga_name}"
        f"{ConsoleUI.RESET}"
        f"   {ConsoleUI.DIM}Version :{ConsoleUI.RESET}"
        f" {ConsoleUI.BOLD}{chosen.label}{ConsoleUI.RESET}"
        f"   {ConsoleUI.DIM}Serveur :{ConsoleUI.RESET}"
        f" {ConsoleUI.BOLD}{chosen.server}{ConsoleUI.RESET}"
        f"   {ConsoleUI.DIM}Départ :{ConsoleUI.RESET}"
        f" {ConsoleUI.BOLD}Chapitre {start_chapter}{ConsoleUI.RESET}"
    )


def _print_download_summary(
    dl: DownloadSession,
    manga_folder: Path,
) -> None:
    """Affiche l'écran de résumé final du téléchargement."""
    mb = dl.stats["bytes_downloaded"] / 1024 ** 2
    UI.sep()
    if IS_ANDROID:
        print("🏁 Téléchargement terminé !")
        print(f"  Chapitres  : {dl.stats['chapters_ok']}")
        print(f"  Pages DL   : {dl.stats['pages_downloaded']}")
        print(f"  Ignorées   : {dl.stats['pages_skipped']}")
        print(f"  Transféré  : {mb:.1f} MB")
        print(f"  Dossier    : {manga_folder}")
        if dl.cbz_export:
            print()
            print("📖 Pour lire vos fichiers .cbz, essayez BD Viewer")
            print("   (disponible sur le Play Store — recherchez : BD Viewer)")
        return

    cbz_lines: list = []
    if dl.cbz_export:
        cbz_lines = [
            "",
            (
                f"  {ConsoleUI.DIM}📖 Lecteur CBZ recommandé (Android) :"
                f"{ConsoleUI.RESET}"
            ),
            (
                f"  {ConsoleUI.CYAN}BD Viewer{ConsoleUI.RESET}"
                f"{ConsoleUI.DIM} — disponible sur le Play Store{ConsoleUI.RESET}"
            ),
        ]
    ConsoleUI.result_screen([
        (
            f"  {ConsoleUI.GREEN}{ConsoleUI.BOLD}🏁 Téléchargement terminé !"
            f"{ConsoleUI.RESET}"
        ),
        (
            f"  {ConsoleUI.DIM}Chapitres téléchargés  :{ConsoleUI.RESET}"
            f" {ConsoleUI.BOLD}{dl.stats['chapters_ok']}{ConsoleUI.RESET}"
        ),
        (
            f"  {ConsoleUI.DIM}Pages téléchargées     :{ConsoleUI.RESET}"
            f" {ConsoleUI.BOLD}{dl.stats['pages_downloaded']}{ConsoleUI.RESET}"
        ),
        (
            f"  {ConsoleUI.DIM}Pages en cache (skip)  :{ConsoleUI.RESET}"
            f" {ConsoleUI.BOLD}{dl.stats['pages_skipped']}{ConsoleUI.RESET}"
        ),
        (
            f"  {ConsoleUI.DIM}Données transférées    :{ConsoleUI.RESET}"
            f" {ConsoleUI.BOLD}{mb:.1f} MB{ConsoleUI.RESET}"
        ),
        f"  {ConsoleUI.DIM}Dossier                :{ConsoleUI.RESET} {manga_folder}",
        *cbz_lines,
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  BOUCLE PRINCIPALE DE TÉLÉCHARGEMENT
# ══════════════════════════════════════════════════════════════════════════════


async def _run_chapter_loop(
    session: aiohttp.ClientSession,
    dl: DownloadSession,
) -> None:
    """Parcourt les chapitres jusqu'à MAX_CONSECUTIVE_MISSING absences."""
    chapter             = dl.start_chapter
    consecutive_missing = 0

    while consecutive_missing < MAX_CONSECUTIVE_MISSING:
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
                f"({consecutive_missing}/{MAX_CONSECUTIVE_MISSING})"
            )
        chapter += 1


async def run_download(
    manga_name: str,
    start_chapter: int,
    cbz: bool,
) -> None:
    """Routine de téléchargement asynchrone principale."""
    set_title(f"Co-Sama ✦ {manga_name}")

    manga_folder = get_download_path() / manga_name.replace(" ", "_")
    manga_folder.mkdir(parents=True, exist_ok=True)
    check_disk_space(1.0)

    async with _make_session() as session:
        if _CACHED_DOMAIN:
            active_catalogue = _CACHED_DOMAIN
            domain = (
                active_catalogue
                .replace("/catalogue/", "")
                .replace("/catalogue", "")
            )
            UI.info("Connexion au serveur (cache)…")
        else:
            active_catalogue = await get_active_domain(session)
            domain = (
                active_catalogue
                .replace("/catalogue/", "")
                .replace("/catalogue", "")
            )

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
        _print_session_header(dl, chosen, start_chapter)
        UI.sep()

        await _run_chapter_loop(session, dl)
        _print_download_summary(dl, manga_folder)


# ══════════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse et retourne les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Co-Sama v3 — Téléchargeur de scans manga"
    )
    parser.add_argument("--manga",  "-m", type=str, help="Nom du manga")
    parser.add_argument("--start",  "-s", type=int, help="Chapitre de départ")
    parser.add_argument("--cbz",    "-z", action="store_true",
                        help="Export .cbz")
    parser.add_argument("--config", "-c", action="store_true",
                        help="Modifier la config")
    return parser.parse_args()


def _startup_server_check() -> None:
    """Vérifie le serveur actif au lancement et met en cache le domaine."""
    if IS_ANDROID:
        SimpleUI.clear()
        SimpleUI.print_logo()
        print()
    UI.info("Vérification du serveur actif…")
    try:
        checked = asyncio.run(startup_domain_check())
        if checked:
            UI.success("Connexion au serveur établie.")
        else:
            UI.warn(
                "Impossible de joindre le serveur — vérifiez votre connexion."
            )
    except OSError:
        UI.warn("Vérification réseau échouée.")
    if not IS_ANDROID:
        time.sleep(0.6)


def _get_manga_name_pc() -> str:
    """Affiche le menu principal PC et retourne le nom du manga saisi."""
    while True:
        idx = ConsoleUI.navigate(
            [
                "📥  Télécharger un manga",
                "⚙️   Configuration",
                "❌  Quitter",
            ],
            "MENU PRINCIPAL",
        )
        if idx in (2, -1):
            ConsoleUI.result_screen(
                [
                    (
                        f"  {ConsoleUI.CYAN}👋  Merci d'avoir utilisé Co-Sama !"
                        f"{ConsoleUI.RESET}"
                    ),
                    "  🌙  À bientôt !",
                ],
                pause=False,
            )
            time.sleep(1)
            sys.exit(0)
        if idx == 1:
            show_config_menu()
            ConsoleUI.clear()
            ConsoleUI.print_logo()
            continue
        raw = ConsoleUI.input_screen(
            "TÉLÉCHARGER UN MANGA",
            "Nom du manga",
            "Respectez les majuscules et les accents",
        )
        if raw.strip():
            return raw.strip().title()
        ConsoleUI.warn("Nom invalide.")
    return ""  # jamais atteint


def _get_manga_name(args: argparse.Namespace) -> str:
    """Résout le nom du manga depuis les args CLI ou la saisie interactive."""
    if args.manga:
        return args.manga.strip().title()
    if IS_ANDROID:
        SimpleUI.clear()
        SimpleUI.print_logo()
        print()
        return input("  📚 Nom du manga : ").strip().title()
    return _get_manga_name_pc()


def _run_with_error_handling(
    manga_name: str,
    start_chapter: int,
    cbz: bool,
) -> None:
    """Lance le téléchargement et gère toutes les exceptions attendues."""
    try:
        asyncio.run(run_download(manga_name, start_chapter, cbz))
    except DomainNotFoundError as exc:
        UI.error(f"Domaine introuvable : {exc}")
        time.sleep(5)
        sys.exit(1)
    except ServerNotFoundError as exc:
        UI.error(f"Serveur introuvable : {exc}")
        time.sleep(5)
        sys.exit(1)
    except DiskSpaceError as exc:
        UI.error(f"Espace disque : {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        if IS_ANDROID:
            print("👋 À bientôt !")
        else:
            ConsoleUI.clear()
            ConsoleUI.print_logo()
            print(
                f"\n  {ConsoleUI.CYAN}👋  Merci d'avoir utilisé Co-Sama !"
                f"{ConsoleUI.RESET}"
            )
            print("  🌙  À bientôt !\n")
        sys.exit(0)
    except Exception:  # pylint: disable=broad-exception-caught
        if not IS_ANDROID:
            traceback.print_exc()
        sys.exit(1)


def main() -> None:
    """Point d'entrée de l'application."""
    set_title("Co-Sama v3")

    if not IS_ANDROID:
        ConsoleUI.enable_ansi()
        ConsoleUI.clear()
        ConsoleUI.print_logo()

    _startup_server_check()

    args = parse_args()

    if args.config:
        show_config_menu()
        return

    manga_name = _get_manga_name(args)
    if not manga_name:
        UI.error("Nom de manga invalide.")
        sys.exit(1)

    if args.start:
        start_chapter = args.start
    else:
        manga_folder  = get_download_path() / manga_name.replace(" ", "_")
        start_chapter = ask_start_chapter(manga_folder)

    cbz = args.cbz or ask_cbz(CONFIG.get("cbz_export", False))
    _run_with_error_handling(manga_name, start_chapter, cbz)


if __name__ == "__main__":
    main()
