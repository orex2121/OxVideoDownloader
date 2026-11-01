"""OxVideoDownloader GUI: Download / Convert / Tasks tabs."""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import core
from . import i18n
from .i18n import T, set_lang, plural, LANGS
from .themes import THEMES, shade


def _titlebar_dark(win, dark):
    """Dark/light the native Windows title bar of a Tk window.

    Tk only paints the client area, so the caption stayed white in dark
    themes.  DWM attribute 20 (Win10 2004+/Win11) with a fallback to the
    undocumented 19 (older Win10) flips it; SWP_FRAMECHANGED forces the
    caption to repaint immediately instead of on the next focus change.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes
        win.update_idletasks()
        # winfo_id() is the inner client window; the real top-level frame
        # (caption + buttons) is its parent in the Windows port of Tcl/Tk
        inner = win.winfo_id()
        hwnd = ctypes.windll.user32.GetParent(inner) or inner
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.wintypes.HWND(hwnd), ctypes.c_uint(attr),
                    ctypes.byref(val), ctypes.sizeof(val)) == 0:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0, 0x0027)
                return
    except Exception:
        pass  # cosmetic only: a missing DWM never breaks the app


def _is_dark(hexcol):
    """Luma test so every dark THEMES palette (not just Obsidian Copper)
    also gets a dark title bar automatically."""
    try:
        h = hexcol.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return (0.299 * r + 0.587 * g + 0.114 * b) < 128
    except (ValueError, IndexError):
        return False

APP_NAME = "OxVideoDownloader"
APP_VERSION = "0.2.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, "config.json")
TASKS_FILE = os.path.join(ROOT, "tasks.json")
THUMB_DIR = os.path.join(ROOT, ".thumbnails")
THUMB_INDEX = os.path.join(THUMB_DIR, "index.json")


def default_download_folder():
    """Return the current Windows user's Videos folder, including a
    OneDrive/Explorer redirection when Windows has one configured."""
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            value, _ = winreg.QueryValueEx(key, "My Video")
            winreg.CloseKey(key)
            if value:
                return os.path.normpath(os.path.expandvars(value))
        except OSError:
            pass
    return os.path.normpath(os.path.join(os.path.expanduser("~"), "Videos"))


def _other_windows_profile(path):
    """Detect a path copied from another C:\\Users\\<name> profile."""
    if os.name != "nt":
        return False
    profile = os.path.normcase(os.path.abspath(
        os.environ.get("USERPROFILE") or os.path.expanduser("~")))
    users = os.path.normcase(os.path.dirname(profile))
    candidate = os.path.normcase(os.path.abspath(path))
    try:
        under_users = os.path.commonpath((candidate, users)) == users
        under_current = os.path.commonpath((candidate, profile)) == profile
    except ValueError:
        return False
    return under_users and not under_current


def ensure_download_folder(path, fallback=None):
    """Return a writable save folder and never reuse another user's path.

    Portable releases can accidentally contain config/tasks from the build
    machine.  Probe candidate folders now so a download cannot fail later
    with Access Denied for C:\\Users\\<builder>.
    """
    requested = os.path.normpath(os.path.expandvars(
        os.path.expanduser(str(path or "")))) if path else ""
    default = os.path.normpath(fallback or default_download_folder())
    profile = os.path.normpath(
        os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    candidates = (requested, default, default_download_folder(),
                  os.path.join(profile, "Documents"), profile)
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.abspath(candidate)
        key = os.path.normcase(candidate)
        if key in seen or _other_windows_profile(candidate):
            continue
        seen.add(key)
        try:
            os.makedirs(candidate, exist_ok=True)
            # Plain open() probe, NOT tempfile.NamedTemporaryFile: for a
            # drive root like C:\ its random-name generator spins forever
            # (CPython bug, seen on 3.12 embeddable) and the whole UI
            # freezes the moment the user picks C:\ in the folder dialog.
            probe = os.path.join(candidate, ".oxvd-write-test.tmp")
            with open(probe, "wb"):
                pass
            try:
                os.remove(probe)
            except OSError:
                pass
            return os.path.normpath(candidate)
        except OSError:
            continue
    return default


def norm_url(url):
    """Key for the URL -> video-id thumbnail index: ignore scheme, www,
    fragment and trailing slash so the same video entered slightly
    differently still matches. The query must be KEPT: on YouTube the video
    id lives in ?v=, dropping it would map every watch URL to one key."""
    u = url.strip().lower().split("#")[0].rstrip("/")
    if "://" in u:
        scheme, rest = u.split("://", 1)
        if rest.startswith("www."):
            rest = rest[4:]
        u = rest
    return u

BLUE = FG = BG = WHITE = HEAD = HEADFG = BAR = SEP = SUB = THUMB = ""
RED = GREEN = PRESSED = FIELD = "#000000"

# Popular hosters this app can download from (yt-dlp extractors).
# Clicking an entry opens the hoster's site; icons live in assets/hosters.
HOSTERS = [
    ("youtube.com", "YouTube"),
    ("rutube.ru", "Rutube"),
    ("vk.com", "VK Video"),
    ("ok.ru", "OK.ru"),
    ("tiktok.com", "TikTok"),
    ("dailymotion.com", "Dailymotion"),
    ("vimeo.com", "Vimeo"),
    ("twitch.tv", "Twitch"),
    ("x.com", "X (Twitter)"),
    ("instagram.com", "Instagram"),
    ("facebook.com", "Facebook"),
    ("reddit.com", "Reddit"),
]


def set_theme(name):
    """Fill the module-level color constants from a THEMES palette."""
    global BLUE, FG, BG, WHITE, HEAD, HEADFG, BAR, SEP, SUB, THUMB
    global RED, GREEN, PRESSED, FIELD
    th = THEMES.get(name) or THEMES["Light"]
    BLUE, FG, BG = th["accent"], th["fg"], th["bg"]
    WHITE, HEAD, HEADFG = th["page"], th["head"], th["headfg"]
    BAR, SEP, SUB = th["bar"], th["sep"], th["sub"]
    THUMB, FIELD = th["thumb"], th["field"]
    RED, GREEN = th["red"], th["green"]
    PRESSED = shade(WHITE, -0.16)
    return th

ICON_DIR = os.path.join(ROOT, "assets")

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class App:
    def __init__(self):
        self.cfg = self._load_config()
        set_lang(self.cfg.get("lang", "en"))
        self._theme = set_theme(self.cfg.get("theme", "Obsidian Copper"))
        configured_folder = self.cfg.get("download_folder")
        self.folder = ensure_download_folder(configured_folder)
        # Convert-tab output folder is kept separate from the download
        # folder so each tab remembers its own last-used path.
        self._cv_folder = ensure_download_folder(
            self.cfg.get("convert_folder") or self.folder)
        self.cookies_browser = self.cfg.get("cookies_browser") or None
        self.history = self.cfg.get("history", [])[:10]
        if configured_folder != self.folder:
            self.cfg["download_folder"] = self.folder
            self._save_config()
        # prefer the ffmpeg/ffprobe bundled inside the app folder (portable),
        # fall back to whatever is on PATH
        def _tool(name):
            local = os.path.join(ROOT, "ffmpeg", name)
            return local if os.path.isfile(local) else shutil.which(name)

        self.ffmpeg = _tool("ffmpeg.exe") if os.name == "nt" else _tool("ffmpeg")
        self.ffprobe = _tool("ffprobe.exe") if os.name == "nt" else _tool("ffprobe")
        self.tasks = []
        self._lock = threading.Lock()
        os.makedirs(THUMB_DIR, exist_ok=True)
        self._thumb_index = self._load_thumb_index()

        # Windows taskbar buttons are grouped per-process by AppUserModelID:
        # without our own id the window inherits pythonw.exe's icon (the Tk
        # feather), which the titlebar iconphoto cannot override.
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32 \
                    .SetCurrentProcessExplicitAppUserModelID(
                        "OxVideo.Downloader.App")
            except Exception:
                pass

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self._titlebar(self.root)
        self._apply_geometry(self.cfg.get("geometry", "931x539"))
        if self.cfg.get("maximized"):
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass
        self.root.configure(bg=WHITE)
        self._env = {"ffmpeg": self.ffmpeg, "ffprobe": self.ffprobe,
                     "cookies_browser": self.cookies_browser,
                     "retry_delay": int(self.cfg.get("retry_delay", 10))}

        self._icons = {}
        self._icon_overlays = []
        photos = []
        for ico in ("app16.png", "app24.png", "app48.png", "app.png"):
            ico = os.path.join(ICON_DIR, ico)
            if os.path.exists(ico):
                try:
                    photos.append(tk.PhotoImage(file=ico))
                except Exception:
                    pass
        if photos:
            self.root.iconphoto(True, *photos)
        self._set_win32_icon()
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self._style_ttk()
        alpha = self._theme.get("alpha", 1.0)
        if alpha < 1.0:
            try:
                self.root.attributes("-alpha", alpha)
            except tk.TclError:
                pass

        self._build_chrome()
        self.pages = {
            "Tasks": self._build_tasks_tab(),
            "Download": self._build_download_tab(),
            "Convert": self._build_convert_tab(),
        }
        self.show_tab("Tasks")
        self._style_buttons(self.root)
        self._load_tasks()
        self._ensure_ffmpeg()
        self._saved_sig = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._place_icons)
        self._tick()

    def _set_win32_icon(self):
        """Give the toplevel its WM_SETICON handle from assets/app.ico.
        Tk's iconphoto reaches the titlebar, but the taskbar button keeps
        the process default (Tk's feather) until the real icon handle is
        attached to the window itself."""
        if os.name != "nt":
            return
        ico = os.path.join(ICON_DIR, "app.ico")
        if not os.path.isfile(ico):
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.LoadImageW.restype = ctypes.c_void_p
            user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                          ctypes.c_uint, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_uint]
            IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
            hicon = user32.LoadImageW(None, ico, IMAGE_ICON, 0, 0,
                                      LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if not hicon:
                return
            user32.UpdateWindow(self.root.winfo_id())
            hwnd = user32.GetParent(self.root.winfo_id()) \
                or self.root.winfo_id()
            WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
        except Exception:
            pass

    def _style_ttk(self):
        """Style every ttk widget class with the active palette, so dialogs
        built from ttk widgets (Advanced...) match the dark/light theme."""
        style = ttk.Style()
        style.configure("TCombobox", padding=4)
        style.configure("Icon.TCombobox", padding=(24, 4))
        style.configure("TCombobox", fieldbackground=FIELD,
                        background=WHITE, foreground=FG, arrowcolor=FG)
        style.map("TCombobox", fieldbackground=[("readonly", WHITE)],
                  foreground=[("readonly", FG)])
        style.configure("TFrame", background=WHITE)
        style.configure("TLabel", background=WHITE, foreground=FG)
        style.configure("TCheckbutton", background=WHITE, foreground=FG,
                        focuscolor=WHITE)
        style.map("TCheckbutton", background=[("active", WHITE)])
        style.configure("TButton", background=WHITE, foreground=FG,
                        bordercolor=SEP, focuscolor=WHITE,
                        lightcolor=WHITE, darkcolor=WHITE)
        style.map("TButton", background=[("active", PRESSED)],
                  foreground=[("active", FG)])
        style.configure("TEntry", fieldbackground=FIELD, foreground=FG,
                        bordercolor=SEP, lightcolor=WHITE, darkcolor=WHITE,
                        insertcolor=FG)
        style.configure("TSpinbox", fieldbackground=FIELD, foreground=FG,
                        bordercolor=SEP, arrowcolor=FG,
                        lightcolor=WHITE, darkcolor=WHITE)

    def _themed_menu(self, parent):
        """A tk.Menu painted with the active palette (context menus,
        popups and cascades all follow the dark/light theme)."""
        return tk.Menu(parent, tearoff=0, bg=WHITE, fg=FG,
                       activebackground=PRESSED, activeforeground=FG)

    # --------------------------------------------------------------- icons
    def _gear_photo(self):
        """Menu gear: the white-on-black mask PNG turned into an RGBA photo
        in the theme green — the same color as the Paste URL button."""
        key = "gear:" + GREEN
        if key in self._icons:
            return self._icons[key]
        path = os.path.join(ICON_DIR, "gear_mask.png")
        photo = None
        if HAS_PIL and os.path.exists(path):
            try:
                mask = Image.open(path).convert("L").resize(
                    (20, 20), Image.LANCZOS)
                r, g, b = (int(GREEN[i:i + 2], 16) for i in (1, 3, 5))
                img = Image.new("RGBA", mask.size, (r, g, b, 0))
                m, o = mask.load(), img.load()
                for y in range(mask.height):
                    for x in range(mask.width):
                        o[x, y] = (r, g, b, m[x, y])
                photo = ImageTk.PhotoImage(img)
            except Exception:
                photo = None
        self._icons[key] = photo
        return photo

    def _img(self, name):
        if name not in self._icons:
            path = os.path.join(ICON_DIR, name)
            try:
                self._icons[name] = tk.PhotoImage(file=path)
            except Exception:
                self._icons[name] = None
        return self._icons[name]

    def _combo_icon(self, combo, name):
        combo.configure(style="Icon.TCombobox")
        self._icon_overlays.append((combo, name))

    def _place_icons(self):
        self.root.update_idletasks()
        for combo, name in self._icon_overlays:
            img = self._img(name)
            if img is None:
                continue
            x = combo.winfo_x() + 4
            y = combo.winfo_y() + (combo.winfo_height() - 16) // 2
            lbl = tk.Label(combo.master, image=img, bd=0, bg=WHITE)
            lbl._oxvd_icon = id(combo)
            lbl.place(x=x, y=y)
            lbl.lift(combo)

    # ------------------------------------------------------------- config
    @staticmethod
    def _load_config():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        return cfg

    def _save_config(self):
        self.cfg.update({"download_folder": self.folder,
                         "cookies_browser": self.cookies_browser,
                         "history": self.history})
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
        except Exception:
            pass

    def _remember(self, url):
        url = url.strip()
        if url and url not in self.history:
            self.history.insert(0, url)
            self.history = self.history[:10]
            self._save_config()

    # --------------------------------------------------------- task journal
    def _save_tasks(self):
        """Persist the Tasks list across restarts. A task that was still
        running at save time is written as Paused: its partial download stays
        on disk (never cleaned on exit) and can be resumed with Start."""
        with self._lock:
            tasks = list(self.tasks)
        rows = [{"id": t.id, "kind": t.kind, "source": t.source,
                 "folder": t.folder, "title": t.title,
                 "status": "Paused" if t.status in
                 ("Downloading", "Processing", "Stopping") else t.status,
                 "pct": t.pct, "downloaded": t.downloaded,
                 "total_bytes": t.total_bytes,
                 "duration_text": t.duration_text, "note": t.note,
                 "thumb_path": t.thumb_path, "final_path": t.final_path,
                 "item": t.item, "dl_opts": t.dl_opts,
                 "cv_opts": t.cv_opts} for t in tasks]
        try:
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=1, ensure_ascii=False)
        except OSError:
            pass

    def _load_tasks(self):
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            return
        if not isinstance(rows, list) or not rows:
            return
        core.Task._seq = max([int(r.get("id") or 0) for r in rows])
        for r in rows:
            if r.get("kind") not in ("download", "convert") \
                    or not r.get("source"):
                continue
            saved_folder = str(r.get("folder") or self.folder)
            task_folder = ensure_download_folder(saved_folder, self.folder)
            folder_repaired = os.path.normcase(os.path.abspath(saved_folder)) \
                != os.path.normcase(os.path.abspath(task_folder))
            t = core.Task(r["kind"], str(r["source"]), task_folder)
            try:
                t.id = int(r["id"])
            except (KeyError, TypeError, ValueError):
                pass
            t.title = r.get("title") or ""
            t.note = "" if folder_repaired else (r.get("note") or "")
            t.item = r.get("item") or ""
            t.duration_text = r.get("duration_text") or ""
            t.thumb_path = r.get("thumb_path")
            t.final_path = r.get("final_path")
            if folder_repaired and t.final_path \
                    and not os.path.isfile(t.final_path):
                t.final_path = None
            if r.get("status") in ("Queued", "Paused", "Done", "Failed",
                                   "Canceled"):
                t.status = "Paused" if folder_repaired \
                    and r["status"] == "Failed" else r["status"]
            t.pct = r.get("pct")
            t.downloaded = r.get("downloaded")
            t.total_bytes = r.get("total_bytes")
            t.dl_opts = r.get("dl_opts") or {}
            t.cv_opts = r.get("cv_opts") or {}
            with self._lock:
                self.tasks.append(t)
            self._make_row(t)

    def _on_close(self):
        self._remember_window()
        self._save_tasks()
        c = getattr(self, "_ff_cancel", None)
        if c is not None:
            c.set()  # stop the startup ffmpeg download immediately
        ff = getattr(self, "_ff_dlg", None)
        if ff is not None and ff.winfo_exists():
            try:
                self._ff_bar.stop()  # cancel its animation before teardown
                ff.destroy()
            except tk.TclError:
                pass
        self.root.destroy()

    def _apply_geometry(self, geo):
        """Restore a saved "WxH+X+Y". Keep the size, but drop the position
        if a monitor change would leave the window off-screen."""
        size = geo.split("+")[0]
        rest = geo[len(size):]
        if rest:
            try:
                x, y = (int(v) for v in rest.lstrip("+").split("+"))
            except ValueError:
                rest = ""
            else:
                vw = self.root.winfo_vrootwidth()
                vh = self.root.winfo_vrootheight()
                if not (-400 < x < vw - 100 and -400 < y < vh - 100):
                    rest = ""
        self.root.geometry(size + rest)

    def _remember_window(self):
        try:
            self.cfg["maximized"] = self.root.state() == "zoomed"
            self.cfg["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        self._save_config()

    # -------------------------------------------------------------- chrome
    def _build_chrome(self):
        strip = tk.Frame(self.root, bg=BG, height=44)
        strip.pack(fill="x")
        strip.pack_propagate(False)
        self.tab_btns = {}
        self.tab_lines = {}
        self.tab_frames = {}
        for i, name in enumerate(("Tasks", "Download", "Convert")):
            f = tk.Frame(strip, bg=BG)
            f.place(x=12 + i * 130, y=0, relheight=1)
            b = tk.Button(f, text=T(name), bd=0, bg=BG, fg=FG,
                          activebackground=PRESSED,
                          font=("Segoe UI", 11), cursor="hand2",
                          command=lambda n=name: self.show_tab(n))
            b.pack(side="top", ipadx=20, ipady=8)
            line = tk.Frame(f, bg=BLUE, height=3)
            line.pack(side="top", fill="x")
            self.tab_btns[name] = (f, b, line)
        # Settings gear.  The Unicode "⚙" glyph renders as a tiny broken
        # star in most fonts, so we tint the Gemini-drawn gear mask PNG to
        # the theme fg and fall back to the glyph only if that asset is
        # missing (or Pillow is unavailable).
        gear = self._gear_photo()
        if gear is not None:
            self.hamburger = tk.Menubutton(
                strip, image=gear, bd=0, bg=BG,
                activebackground=PRESSED, direction="below")
        else:
            self.hamburger = tk.Menubutton(
                strip, text="⚙", bd=0, bg=BG, fg=FG,
                activebackground=PRESSED, font=("Segoe UI Symbol", 15),
                direction="below")
        menu = self._themed_menu(self.hamburger)
        menu.add_command(label=T("Change download folder..."),
                         command=self.change_folder)
        menu.add_command(label=T("Open download folder"),
                         command=self.open_folder)
        menu.add_command(label=T("Settings"), command=self.open_settings)
        menu.add_separator()
        menu.add_cascade(label=T("Video Hosters"), menu=self._hosters_menu())
        self.hamburger["menu"] = menu
        self.hamburger_menu = menu
        self.hamburger.place(relx=1.0, x=-30, y=8)

        bar = tk.Frame(self.root, bg=BAR, height=26)
        bar.pack(side="bottom", fill="x")
        self.lbl_status = tk.Label(bar, text=T("Ready"), bg=BAR, fg=FG,
                                   font=("Segoe UI", 9))
        self.lbl_status.pack(side="left", padx=8)
        self.lbl_count = tk.Label(bar, text=f"0 {plural('task', 0)}", bg=BAR, fg=FG,
                                  font=("Segoe UI", 9))
        self.lbl_count.pack(side="right", padx=8)
        self.page_host = tk.Frame(self.root, bg=WHITE)
        self.page_host.pack(fill="both", expand=True)

    def show_tab(self, name):
        for n, (f, b, line) in self.tab_btns.items():
            if n == name:
                f.configure(bg=WHITE)
                b.configure(bg=WHITE)
                line.configure(bg=BLUE)
            else:
                f.configure(bg=BG)
                b.configure(bg=BG)
                line.configure(bg=BG)
        for n, page in self.pages.items():
            if n == name:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()

    # --------------------------------------------------------- Download tab
    def _build_download_tab(self):
        p = tk.Frame(self.page_host, bg=WHITE)
        LW, CW, GAP = 170, 700, 12          # labels / fields / pair gap
        HALF = (CW - GAP) // 2
        X0 = LW + 24                        # shared left edge of all fields
        FW = X0 + CW + 6
        form = tk.Frame(p, bg=WHITE)
        form.place(relx=0.5, rely=0.44, anchor="center", width=FW, height=364)

        def dot(y):
            tk.Label(form, text="\u25cf", fg=BLUE, bg=WHITE,
                     font=("Segoe UI", 9)).place(x=2, y=y + 5)

        def label(y, text):
            tk.Label(form, text=text, bg=WHITE, fg=FG, anchor="w",
                     font=("Segoe UI", 10, "bold")).place(x=24, y=y,
                                                          width=LW - 28, height=30)

        L, R = X0, X0 + HALF + GAP          # left / right slot of a pair

        def aux(y, text, cmd):
            tk.Button(form, text=text, bd=1, relief="solid", bg=WHITE,
                      fg=FG, activebackground=PRESSED,
                      font=("Segoe UI", 9, "bold"), cursor="hand2",
                      command=cmd).place(x=R, y=y, width=HALF, height=30)

        dot(0)
        label(0, T("URL:"))
        self.d_url = ttk.Combobox(form, values=self.history,
                                  font=("Segoe UI", 10))
        self.d_url.place(x=L, y=0, width=HALF, height=30)
        if self.history:
            self.d_url.set(self.history[0])
        aux(0, T("Paste URL"), self.paste_into_url)

        dot(46)
        label(46, T("Download what:"))
        self.d_what = ttk.Combobox(form, values=[T("Download video"),
                                                 T("Download audio")],
                                   state="readonly")
        self.d_what.current(0)
        self.d_what.place(x=L, y=46, width=HALF, height=30)
        self.d_quality = ttk.Combobox(form, state="readonly")
        self.d_quality.place(x=R, y=46, width=HALF, height=30)
        self.d_what.bind("<<ComboboxSelected>>",
                         lambda e: self._fill_quality())
        self._fill_quality()
        self._combo_icon(self.d_what, "film.png")
        self.d_playlist = tk.BooleanVar(value=False)
        tk.Checkbutton(form, text=T("Download playlist"),
                       variable=self.d_playlist, bg=WHITE, fg=FG,
                       activebackground=PRESSED, selectcolor=FIELD,
                       font=("Segoe UI", 9)).place(x=L, y=82, height=22)

        dot(116)
        label(116, T("Save to folder:"))
        self.d_folder = ttk.Combobox(form, values=[self.folder],
                                     font=("Segoe UI", 10))
        self.d_folder.set(self.folder)
        self.d_folder.place(x=L, y=116, width=HALF, height=30)
        self._combo_icon(self.d_folder, "folder.png")
        aux(116, T("Browse..."), lambda: self.browse(self.d_folder))
        # Remember the typed path right away — not only when a download
        # is started — so the same folder is back on the next launch.
        for ev in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self.d_folder.bind(ev, lambda e: self._save_d_folder())

        by = 164
        tk.Button(form, text=T("Download Now"), fg="white", bg=BLUE,
                  activebackground=shade(BLUE, -0.30),
                  activeforeground="white", bd=0, cursor="hand2",
                  font=("Segoe UI", 11, "bold"),
                  command=lambda: self.add_download(start=True)).place(
            x=L, y=by, width=HALF, height=44)
        tk.Button(form, text=T("Download Later"), fg="white", bg=GREEN,
                  activebackground=shade(GREEN, -0.30),
                  activeforeground="white", bd=0, cursor="hand2",
                  font=("Segoe UI", 11, "bold"),
                  command=lambda: self.add_download(start=False)).place(
            x=R, y=by, width=HALF, height=44)

        self.d_more = tk.BooleanVar(value=False)
        more_box = tk.Frame(form, bg=WHITE, cursor="hand2")
        chevron = self._img("chevron.png")
        if chevron:
            tk.Label(more_box, image=chevron, bd=0, bg=WHITE,
                     cursor="hand2").pack(side="left", padx=(0, 6))
        more_lbl = tk.Label(more_box, text=T("More Options"), bg=WHITE,
                            fg=FG, font=("Segoe UI", 10, "bold"),
                            cursor="hand2")
        more_lbl.pack(side="left")
        more_box.place(x=L, y=226, height=24)
        more_box.bind("<Button-1>", lambda e: self._toggle_more())
        more_lbl.bind("<Button-1>", lambda e: self._toggle_more())
        self._pressable([more_box] + more_box.winfo_children())

        self.d_moreframe = tk.Frame(form, bg=WHITE)
        tk.Label(self.d_moreframe, text=T("Sign-in cookies:"), bg=WHITE,
                 fg=FG, font=("Segoe UI", 9)).place(x=L, y=4, width=HALF,
                                                    anchor="w")
        self.d_cookies = ttk.Combobox(
            self.d_moreframe, state="readonly",
            values=["none", "chrome", "edge", "firefox", "brave"])
        self.d_cookies.set(self.cookies_browser or "none")
        self.d_cookies.place(x=L, y=26, width=HALF, height=28)
        tk.Label(self.d_moreframe, text=T("Concurrent segments:"), bg=WHITE,
                 fg=FG, font=("Segoe UI", 9)).place(x=R, y=4, width=HALF,
                                                    anchor="w")
        self.d_segments = tk.Spinbox(self.d_moreframe, from_=1, to=16,
                                     bg=FIELD, fg=FG, highlightthickness=1,
                                     highlightbackground=SEP,
                                     font=("Segoe UI", 10))
        self.d_segments.delete(0, "end")
        self.d_segments.insert(0, "4")
        self.d_segments.place(x=X0 + CW - 70, y=26, width=70, height=28)

        # row 2: auto re-encode the download after it finishes. The choice is
        # remembered across restarts and saved the moment it is toggled.
        self.d_cv_on = tk.BooleanVar(value=bool(self.cfg.get("dl_convert",
                                                             False)))

        def _cv_toggle():
            self.cfg["dl_convert"] = self.d_cv_on.get()
            self._save_config()

        tk.Checkbutton(self.d_moreframe, text=T("Convert to format:"),
                       variable=self.d_cv_on, command=_cv_toggle,
                       bg=WHITE, fg=FG,
                       activebackground=PRESSED, selectcolor=FIELD,
                       font=("Segoe UI", 10, "bold")).place(
            x=L, y=58, width=170, height=28)
        self.d_cv_cont = ttk.Combobox(self.d_moreframe, state="readonly",
                                      values=list(core.CONTAINERS))
        self.d_cv_cont.set(self.cfg.get("dl_container", "MP4 .mp4"))
        self.d_cv_cont.place(x=L + 175, y=58, width=HALF - 175, height=28)
        self.d_cv_codec = ttk.Combobox(self.d_moreframe, state="readonly")
        self.d_cv_codec.place(x=R, y=58, width=HALF, height=28)
        def _cv_choice(_e=None):
            self.cfg["dl_container"] = self.d_cv_cont.get()
            self.cfg["dl_codec"] = self.d_cv_codec.get()
            self._save_config()

        self.d_cv_cont.bind("<<ComboboxSelected>>",
                            lambda e: (self._fill_cv_codec(), _cv_choice()))
        self.d_cv_codec.bind("<<ComboboxSelected>>", _cv_choice)
        self._fill_cv_codec()

        def show_more(event=None):
            self.d_moreframe.place(x=0, y=262, width=FW, height=94)
        self._show_more_cb = show_more
        return p

    def _hosters_menu(self):
        """Cascade listing the popular hosters this app downloads from.
        Each entry carries the hoster's own logo and opens its web site."""
        m = self._themed_menu(self.hamburger)
        self._hoster_imgs = []
        for dom, name in HOSTERS:
            img = None
            for pfx in ("hosters/icons16", "hosters"):
                p = os.path.join(ICON_DIR, pfx, dom + ".png")
                if os.path.exists(p):
                    try:
                        img = tk.PhotoImage(file=p)
                        self._hoster_imgs.append(img)
                    except Exception:
                        img = None
                    break
            m.add_command(label=name, image=img, compound="left",
                          command=lambda d=dom: webbrowser.open(
                              "https://www." + d))
        return m

    def _fill_quality(self):
        if self.d_what.current() == 0:
            self.d_quality["values"] = [T(q[0]) for q in core.VIDEO_QUALITIES]
            self.d_quality.current(0)
        else:
            self.d_quality["values"] = [T(q[0]) for q in core.AUDIO_QUALITIES]
            self.d_quality.current(0)

    def _fill_cv_codec(self):
        vals = core.codecs_for(self.d_cv_cont.get())
        self.d_cv_codec["values"] = vals
        cur = self.d_cv_codec.get() or self.cfg.get("dl_codec", "")
        self.d_cv_codec.set(cur if cur in vals else vals[0])

    def _toggle_more(self):
        if self.d_more.get():
            self.d_moreframe.place_forget()
            self.d_more.set(False)
        else:
            self._show_more_cb()
            self.d_more.set(True)

    def _toggle_more_c(self):
        if self.c_more.get():
            self.c_moreframe.place_forget()
            self.c_more.set(False)
        else:
            self._show_more_c_cb()
            self.c_more.set(True)

    def paste_into_url(self):
        try:
            self.d_url.set(self.root.clipboard_get().strip())
        except Exception:
            pass

    def browse(self, combo):
        folder = filedialog.askdirectory(initialdir=combo.get() or self.folder,
                                         title=T("Save to folder"))
        if folder:
            combo.set(os.path.normpath(folder))
            # .set() fires no virtual events, so persist the choice here.
            # warn=True: an explicit dialog pick that turns out unwritable
            # (e.g. C:\) must explain itself instead of silently reverting.
            if combo is self.d_folder:
                self._save_d_folder(warn=True)
            else:
                self._c_folder_edited(warn=True)

    def _save_d_folder(self, warn=False):
        """The Download-tab path IS the app download folder: persist it
        as soon as the user picks or types it, so the next launch shows
        the same path."""
        path = self.d_folder.get().strip()
        if not path:
            self.d_folder.set(self.folder)
            return
        new = ensure_download_folder(path, self.folder)
        if warn and os.path.normcase(new) != os.path.normcase(path):
            messagebox.showwarning(
                APP_NAME, T("This folder cannot be written to: Windows "
                            "protects the root of the C: drive. Pick or "
                            "create a normal folder (for example C:\\Video)."))
        self.folder = new
        self.d_folder.set(self.folder)
        self._save_config()

    def _sync_c_folder(self):
        """Show the folder the converted file will really land in: with
        'Same as input folder' ticked that is the source file's folder."""
        if not hasattr(self, "c_folder"):
            return
        src = self.c_src.get().strip()
        if self.c_same.get() and src and os.path.isfile(src):
            self.c_folder.set(os.path.dirname(os.path.normpath(src)))
        else:
            self.c_folder.set(self._cv_folder)

    def _c_folder_edited(self, warn=False):
        if self.c_same.get():
            # While the checkbox is on the field mirrors the source
            # folder; a manual edit there is meaningless — revert it.
            self._sync_c_folder()
            return
        path = self.c_folder.get().strip()
        if not path:
            self.c_folder.set(self._cv_folder)
            return
        new = ensure_download_folder(path, self.folder)
        if warn and os.path.normcase(new) != os.path.normcase(path):
            messagebox.showwarning(
                APP_NAME, T("This folder cannot be written to: Windows "
                            "protects the root of the C: drive. Pick or "
                            "create a normal folder (for example C:\\Video)."))
        self._cv_folder = new
        self.c_folder.set(self._cv_folder)
        self.cfg["convert_folder"] = self._cv_folder
        self._save_config()

    def _center_over_root(self, win, dw=None, dh=None):
        """Place a dialog centered over the main window and keep it
        above the app (transient).  The WM default centers on the
        primary monitor, which on multi-monitor setups lands on the
        wrong screen."""
        win.transient(self.root)
        win.update_idletasks()
        dw = dw or win.winfo_reqwidth()
        dh = dh or win.winfo_reqheight()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        win.geometry("+%d+%d" % (max(0, rx + (rw - dw) // 2),
                                 max(0, ry + (rh - dh) // 2)))
        win.lift()

    # --------------------------------------------------------- Convert tab
    def _build_convert_tab(self):
        p = tk.Frame(self.page_host, bg=WHITE)
        LW, CW, GAP = 170, 700, 12
        HALF = (CW - GAP) // 2
        X0 = LW + 24
        FW = X0 + CW + 6
        form = tk.Frame(p, bg=WHITE)
        form.place(relx=0.5, rely=0.44, anchor="center", width=FW, height=364)

        def dot(y):
            tk.Label(form, text="\u25cf", fg=BLUE, bg=WHITE,
                     font=("Segoe UI", 9)).place(x=2, y=y + 5)

        def label(y, text):
            tk.Label(form, text=text, bg=WHITE, fg=FG, anchor="w",
                     font=("Segoe UI", 10, "bold")).place(x=24, y=y,
                                                          width=LW - 28, height=30)

        L, R = X0, X0 + HALF + GAP

        def aux(y, text, cmd):
            tk.Button(form, text=text, bd=1, relief="solid", bg=WHITE,
                      fg=FG, activebackground=PRESSED,
                      font=("Segoe UI", 9, "bold"), cursor="hand2",
                      command=cmd).place(x=R, y=y, width=HALF, height=30)

        dot(0)
        label(0, T("Source file:"))
        self.c_src = tk.Entry(form, font=("Segoe UI", 10), bg=FIELD, fg=FG,
                              highlightthickness=1, highlightbackground=SEP)
        self.c_src.place(x=L, y=0, width=HALF, height=30)
        self.c_src.bind("<KeyRelease>", lambda e: self._sync_c_folder())
        aux(0, T("Browse..."), self.browse_source)

        dot(46)
        label(46, T("Convert to format:"))
        self.c_container = ttk.Combobox(form, values=list(core.CONTAINERS),
                                        state="readonly")
        self.c_container.set("MP4 .mp4")
        self.c_container.place(x=L, y=46, width=HALF, height=30)
        self._combo_icon(self.c_container, "film.png")
        self.c_codec = ttk.Combobox(form, state="readonly")
        self.c_codec.place(x=R, y=46, width=HALF, height=30)
        self.c_container.bind("<<ComboboxSelected>>",
                              lambda e: self._fill_codec())
        self._fill_codec()

        self.c_same = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text=T("Same as input folder"),
                       variable=self.c_same, command=self._sync_c_folder,
                       bg=WHITE, fg=FG,
                       activebackground=PRESSED, selectcolor=FIELD,
                       font=("Segoe UI", 9)).place(x=L, y=82, height=22)

        dot(116)
        label(116, T("Save to folder:"))
        self.c_folder = ttk.Combobox(form, values=[self._cv_folder,
                                                   self.folder],
                                     font=("Segoe UI", 10))
        self.c_folder.place(x=L, y=116, width=HALF, height=30)
        self._combo_icon(self.c_folder, "folder.png")
        aux(116, T("Browse..."), lambda: self.browse(self.c_folder))
        for ev in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self.c_folder.bind(ev, lambda e: self._c_folder_edited())
        self._sync_c_folder()

        by = 164
        tk.Button(form, text=T("Convert Now"), fg="white", bg=BLUE,
                  activebackground=shade(BLUE, -0.30),
                  activeforeground="white", bd=0, cursor="hand2",
                  font=("Segoe UI", 11, "bold"),
                  command=lambda: self.add_convert(start=True)).place(
            x=L, y=by, width=HALF, height=44)
        tk.Button(form, text=T("Convert Later"), fg="white", bg=GREEN,
                  activebackground=shade(GREEN, -0.30),
                  activeforeground="white", bd=0, cursor="hand2",
                  font=("Segoe UI", 11, "bold"),
                  command=lambda: self.add_convert(start=False)).place(
            x=R, y=by, width=HALF, height=44)

        self.c_more = tk.BooleanVar(value=False)
        more_box = tk.Frame(form, bg=WHITE, cursor="hand2")
        chevron = self._img("chevron.png")
        if chevron:
            tk.Label(more_box, image=chevron, bd=0, bg=WHITE,
                     cursor="hand2").pack(side="left", padx=(0, 6))
        more_lbl = tk.Label(more_box, text=T("More Options"), bg=WHITE,
                            fg=FG, font=("Segoe UI", 10, "bold"),
                            cursor="hand2")
        more_lbl.pack(side="left")
        more_box.place(x=L, y=226, height=24)
        more_box.bind("<Button-1>", lambda e: self._toggle_more_c())
        more_lbl.bind("<Button-1>", lambda e: self._toggle_more_c())
        self._pressable([more_box] + more_box.winfo_children())

        self.c_moreframe = tk.Frame(form, bg=WHITE)
        tk.Button(self.c_moreframe, text=T("Advanced..."), bd=1,
                  relief="solid", bg=WHITE, fg=FG,
                  activebackground=PRESSED, cursor="hand2",
                  font=("Segoe UI", 9, "bold"),
                  command=self.advanced_dialog).place(x=L, y=14,
                                                      width=HALF, height=30)

        def show_more(event=None):
            self.c_moreframe.place(x=0, y=262, width=FW, height=58)
        self._show_more_c_cb = show_more
        return p

    def _fill_codec(self):
        vals = core.codecs_for(self.c_container.get())
        cur = self.c_codec.get()
        self.c_codec["values"] = vals
        self.c_codec.set(cur if cur in vals else vals[0])

    def _titlebar(self, win):
        """Match the native title bar to the active theme (dark themes
        kept the default white caption otherwise).  Called for root and
        every Toplevel; deferred copy covers windows not yet mapped."""
        dark = _is_dark(self._theme.get("bg", "#ffffff"))
        _titlebar_dark(win, dark)
        try:
            win.after_idle(lambda: _titlebar_dark(win, dark))
        except tk.TclError:
            pass

    # ------------------------------------------------------------ ffmpeg setup
    def _ensure_ffmpeg(self):
        """ffmpeg/ffprobe are not shipped inside the repository, so at
        startup check for them in the portable ffmpeg folder specifically
        and if absent download them on the fly while a small dialog shows
        the progress so the user knows what is happening.  A system ffmpeg
        on PATH is deliberately NOT accepted here: it is often an old or
        crippled build that breaks our conversion commands, so the app
        prefers to own its copy; PATH remains only the fallback when the
        download fails."""
        ext = ".exe" if os.name == "nt" else ""
        local = [os.path.join(ROOT, "ffmpeg", n + ext)
                 for n in ("ffmpeg", "ffprobe")]
        if all(os.path.isfile(p) for p in local):
            return
        dlg = tk.Toplevel(self.root)
        self._ff_dlg = dlg
        self._titlebar(dlg)
        dlg.title(T("FFmpeg setup"))
        dlg.configure(bg=WHITE)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        W, H = 400, 150
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        dlg.geometry(f"{W}x{H}+{rx + (self.root.winfo_width() - W) // 2}"
                     f"+{ry + (self.root.winfo_height() - H) // 2}")
        tk.Label(dlg, text=T("FFmpeg is required to merge and convert "
                             "videos."), bg=WHITE, fg=FG,
                 font=("Segoe UI", 10, "bold")).place(x=16, y=12)
        tk.Label(dlg, text=T("First run: downloading FFmpeg..."), bg=WHITE,
                 fg=SUB, font=("Segoe UI", 9)).place(x=16, y=38)
        self._ff_bar = ttk.Progressbar(dlg, length=W - 32, mode="determinate",
                                       maximum=1000)
        self._ff_bar.place(x=16, y=66)
        self._ff_detail = tk.Label(dlg, text="", bg=WHITE, fg=FG, anchor="w",
                                   font=("Segoe UI", 9))
        self._ff_detail.place(x=16, y=94, width=W - 32)
        cancel_btn = ttk.Button(dlg, text=T("Cancel"))
        cancel_btn.place(x=W - 96, y=H - 42, width=80)
        # no grab_set(): the main window must stay usable (and closable)
        # while the download runs; the dialog is only a progress notice.
        self._ff_cancel = threading.Event()

        def stop_download():
            """Abort the transfer and close the progress notice."""
            self._ff_cancel.set()
            try:
                self._ff_bar.stop()
            except tk.TclError:
                pass
            dlg.destroy()
            self.lbl_status.configure(text=T("Ready"))

        cancel_btn.configure(command=stop_download)
        # closing the dialog stops the download instead of hiding it,
        # otherwise the user has no way to get rid of a stalled transfer
        dlg.protocol("WM_DELETE_WINDOW", stop_download)

        q = queue.Queue()
        t0 = time.time()

        def worker():
            ok = core.download_ffmpeg(
                os.path.join(ROOT, "ffmpeg"),
                progress=lambda done, total, phase: q.put(
                    (done, total, phase)),
                cancel=self._ff_cancel)
            q.put(("done", 1 if ok else 0, 0))

        def pump():
            if not dlg.winfo_exists():
                return
            try:
                ev = None
                while True:
                    ev = q.get_nowait()
            except queue.Empty:
                pass
            if ev:
                done, total, phase = ev
                if done == "done":
                    self._ffmpeg_ready(bool(total), dlg)
                    return
                if phase == "extract":
                    self._ff_bar.configure(mode="indeterminate")
                    self._ff_bar.start(15)
                    self._ff_detail.configure(text=T("Extracting..."))
                elif total:
                    self._ff_bar.configure(mode="determinate", maximum=total,
                                           value=done)
                    secs = max(time.time() - t0, 0.001)
                    self._ff_detail.configure(
                        text=f"{core.human_size(done)} / "
                             f"{core.human_size(total)}"
                             f"  ·  {core.human_size(done / secs)}/s")
            dlg.after(150, pump)

        threading.Thread(target=worker, daemon=True).start()
        dlg.after(150, pump)

    def _ffmpeg_ready(self, ok, dlg):
        """Finish the startup download: point the app at the fresh
        binaries (or report the failure) and close the progress dialog."""
        try:
            self._ff_bar.stop()
        except tk.TclError:
            pass
        if dlg.winfo_exists():
            dlg.destroy()
        if ok:
            self.ffmpeg = os.path.join(ROOT, "ffmpeg", "ffmpeg.exe")
            self.ffprobe = os.path.join(ROOT, "ffmpeg", "ffprobe.exe")
            self._env["ffmpeg"] = self.ffmpeg
            self._env["ffprobe"] = self.ffprobe
            self.lbl_status.configure(text=T("FFmpeg installed"))
        else:
            self.lbl_status.configure(text=T("Ready"))
            if not getattr(self, "_ff_cancel", None) or not self._ff_cancel.is_set():
                messagebox.showerror(
                    T("FFmpeg setup"),
                    T("Could not download FFmpeg. Check your internet "
                      "connection and restart the app."))

    def advanced_dialog(self):
        dlg = tk.Toplevel(self.root)
        self._titlebar(dlg)
        dlg.title(T("Advanced conversion options"))
        dlg.configure(bg=WHITE)
        dlg.resizable(False, False)
        self._center_over_root(dlg)
        g = ttk.Frame(dlg, padding=12)
        g.pack(fill="both", expand=True)
        ttk.Label(g, text=T("Audio bitrate:")).grid(row=0, column=0, sticky="w")
        abr = ttk.Combobox(g, state="readonly", width=10,
                           values=["128k", "192k", "256k", "320k"])
        abr.set(self.cfg.get("abr", "192k"))
        abr.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(g, text=T("CPU preset:")).grid(row=1, column=0, sticky="w")
        preset = ttk.Combobox(g, state="readonly", width=10,
                              values=["veryfast", "faster", "fast", "medium",
                                      "slow"])
        preset.set(self.cfg.get("preset", "medium"))
        preset.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(g, text=T("CRF (quality):")).grid(row=2, column=0, sticky="w")
        crf = tk.Spinbox(g, from_=14, to=35, width=4, bg=FIELD, fg=FG)
        crf.delete(0, "end")
        crf.insert(0, str(self.cfg.get("crf", 20)))
        crf.grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(g, text=T("Extra ffmpeg args:")).grid(row=3, column=0,
                                                     sticky="w")
        extra = ttk.Entry(g, width=30)
        extra.insert(0, self.cfg.get("extra", ""))
        extra.grid(row=3, column=1, sticky="w", padx=6)
        # "?" right of the field: cheat-sheet of useful ffmpeg arguments.
        ttk.Button(g, text="?", width=3, command=lambda: self._ffmpeg_help(
            dlg)).grid(row=3, column=2, sticky="w")
        ttk.Button(g, text=T("OK"), command=lambda: self._save_advanced(
            dlg, abr.get(), preset.get(), crf.get(), extra.get())).grid(
            row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))

    # Cheat-sheet contents per language: (section, [(args, description)])
    # Extra args are appended by core right before the output file, so the
    # sheet documents options in exactly that position.
    FFMPEG_HELP = {
        "ru": (
            "Сюда добавляются аргументы ffmpeg — они вставляются в команду "
            "перед файлом вывода. Строку можно выделить и скопировать (Ctrl+C).",
            [
                ("Без перекодирования (быстро, без потерь)", [
                    ("-c copy", "смена контейнера (remux), например MKV → MP4"),
                    ("-c:v copy", "видео как есть, перекодировать только аудио"),
                    ("-c:a copy", "аудио как есть, перекодировать только видео"),
                ]),
                ("Видео: кодек и качество", [
                    ("-c:v libx264", "кодировать видео в H.264 (универсально)"),
                    ("-c:v libx265", "H.265/HEVC — примерно вдвое меньше файл, "
                     "но дольше кодировать"),
                    ("-c:v libvpx-vp9", "VP9 — лучший выбор для WEBM"),
                    ("-crf 18", "качество 0–51, меньше = лучше; 18 ≈ «без "
                     "потерь для глаза», 23 — по умолчанию"),
                    ("-preset slow", "скорость x264/x265: ultrafast … veryslow, "
                     "медленнее = сильнее сжатие"),
                    ("-b:v 4M", "постоянный битрейт видео (ABR), вместо crf"),
                ]),
                ("Аудио", [
                    ("-c:a aac -b:a 192k", "аудио AAC 192 кбит/с"),
                    ("-c:a libmp3lame -b:a 320k", "аудио MP3 320 кбит/с"),
                    ("-ar 48000", "частота дискретизации аудио"),
                    ("-an", "полностью убрать аудио"),
                ]),
                ("Размер, кадры, обрезка", [
                    ("-vf scale=1920:1080", "изменить разрешение "
                     "(1280:720, 3840:2160, …)"),
                    ("-r 60", "частота кадров"),
                    ("-ss 00:01:30 -to 00:02:45", "вырезать фрагмент "
                     "между временем начала и конца"),
                    ("-t 60", "брать только N секунд от начала"),
                ]),
                ("Прочее", [
                    ("-sn", "отключить дорожки субтитров"),
                    ("-map 0:v:0 -map 0:a:0", "взять первую видеодорожку и "
                     "первую аудиодорожку"),
                    ("-movflags +faststart", "MP4 для просмотра по сети: "
                     "заголовок в начало файла"),
                    ("-metadata title=\"Имя\"", "записать заголовок в файл"),
                ]),
            ]),
        "en": (
            "These are extra ffmpeg arguments — they are inserted into the "
            "command right before the output file. Select a line and press "
            "Ctrl+C to copy it.",
            [
                ("Without re-encoding (fast, lossless)", [
                    ("-c copy", "change container (remux), e.g. MKV → MP4"),
                    ("-c:v copy", "keep video, re-encode only audio"),
                    ("-c:a copy", "keep audio, re-encode only video"),
                ]),
                ("Video: codec & quality", [
                    ("-c:v libx264", "encode video to H.264 (most compatible)"),
                    ("-c:v libx265", "H.265/HEVC — about half the size, "
                     "but slower to encode"),
                    ("-c:v libvpx-vp9", "VP9 — best choice for WEBM"),
                    ("-crf 18", "quality 0–51, lower = better; 18 ≈ visually "
                     "lossless, 23 is the default"),
                    ("-preset slow", "x264/x265 speed: ultrafast … veryslow, "
                     "slower = better compression"),
                    ("-b:v 4M", "constant video bitrate (ABR) instead of crf"),
                ]),
                ("Audio", [
                    ("-c:a aac -b:a 192k", "AAC audio at 192 kbit/s"),
                    ("-c:a libmp3lame -b:a 320k", "MP3 audio at 320 kbit/s"),
                    ("-ar 48000", "audio sample rate"),
                    ("-an", "remove audio entirely"),
                ]),
                ("Size, frame rate, trimming", [
                    ("-vf scale=1920:1080", "change resolution "
                     "(1280:720, 3840:2160, …)"),
                    ("-r 60", "frame rate"),
                    ("-ss 00:01:30 -to 00:02:45", "cut the fragment between "
                     "two timestamps"),
                    ("-t 60", "keep only N seconds from the start"),
                ]),
                ("Other", [
                    ("-sn", "drop subtitle tracks"),
                    ("-map 0:v:0 -map 0:a:0", "take the first video and the "
                     "first audio track"),
                    ("-movflags +faststart", "MP4 for web streaming: move the "
                     "index to the file start"),
                    ("-metadata title=\"Name\"", "write a title into the file"),
                ]),
            ]),
    }

    def _ffmpeg_help(self, master):
        """Non-modal cheat-sheet of extra ffmpeg arguments.  Transient to
        the Advanced dialog so it floats above the app, but there is no
        grab_set(): the user can drag it aside and keep filling the form."""
        win = getattr(self, "_ffmpeg_help_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        intro, groups = self.FFMPEG_HELP["ru" if i18n.LANG == "ru" else "en"]
        dlg = tk.Toplevel(self.root)
        self._ffmpeg_help_win = dlg
        self._titlebar(dlg)
        dlg.title(T("ffmpeg arguments help"))
        dlg.configure(bg=WHITE)
        body = tk.Frame(dlg, bg=WHITE)
        body.pack(fill="both", expand=True, padx=10, pady=(8, 10))
        txt = tk.Text(body, width=62, height=26, bd=1, relief="solid",
                      bg=FIELD, fg=FG, insertbackground=FG,
                      font=("Consolas", 9), wrap="none",
                      selectbackground=BLUE, selectforeground=WHITE)
        sb = ttk.Scrollbar(body, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.tag_configure("arg", font=("Consolas", 10, "bold"),
                          foreground=BLUE)
        txt.tag_configure("sec", font=("Segoe UI", 10, "bold"),
                          foreground=FG)
        txt.tag_configure("note", font=("Segoe UI", 9), foreground=SUB)
        txt.insert("end", intro + "\n\n", "note")
        for sec, rows in groups:
            txt.insert("end", sec + "\n", "sec")
            for args, desc in rows:
                txt.insert("end", args + "\n", "arg")
                txt.insert("end", "   " + desc + "\n", "note")
            txt.insert("end", "\n")
        # Read-only but selectable: block plain typing, keep Ctrl+C / arrows.
        def _ro(e):
            if e.state & 0x0004:  # Ctrl held → allow copy & navigation
                return
            return "break"
        txt.bind("<Key>", _ro)
        for seq in ("<Control-v>", "<Control-V>", "<Control-x>", "<Control-X>",
                    "<Control-BackSpace>"):
            txt.bind(seq, lambda e: "break")
        # Same monitor as the app, to the right of the Advanced dialog
        # (or its left if the screen edge is close); native caption gives
        # the close cross; the window stays movable and above the app.
        dlg.transient(master)
        dlg.update_idletasks()
        w, h = 640, 470
        mx = master.winfo_rootx() + master.winfo_width() + 12
        my = master.winfo_rooty()
        if mx + w > dlg.winfo_screenwidth() - 8:
            mx = max(8, master.winfo_rootx() - w - 12)
        my = max(8, min(my, dlg.winfo_screenheight() - h - 40))
        dlg.geometry(f"{w}x{h}+{mx}+{my}")
        dlg.lift()
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

    def _save_advanced(self, dlg, abr, preset, crf, extra):
        self.cfg.update({"abr": abr, "preset": preset, "crf": crf,
                         "extra": extra})
        self._save_config()
        dlg.destroy()

    def _set_src(self, value):
        self.c_src.delete(0, "end")
        self.c_src.insert(0, value)
        self._sync_c_folder()

    def browse_source(self):
        f = filedialog.askopenfilename(
            title=T("Source file"),
            filetypes=[(T("Video/Audio"), "*.mp4 *.mkv *.webm *.mov *.avi "
                        "*.mp3 *.m4a *.wav *.flac"),
                       (T("All files"), "*.*")])
        if f:
            self._set_src(os.path.normpath(f))

    # ------------------------------------------------------------ Tasks tab
    def _build_tasks_tab(self):
        p = tk.Frame(self.page_host, bg=WHITE)
        bar = tk.Frame(p, bg=WHITE, pady=6)
        bar.pack(fill="x", padx=6)
        for ico, text, color, cmd, dd in (
                ("plus_green.png", T("Paste URL"), GREEN, self.tb_paste,
                 True),
                ("plus_blue.png", T("Add Files"), BLUE, self.tb_add_files,
                 True),
                ("play.png", T("Start All"), BLUE, self.start_all, False),
                ("pause.png", T("Pause All"), FG, self.pause_all, False),
                ("minus.png", T("Remove"), FG, self.remove_selected, False),
                ("minus.png", T("Remove Completed"), FG,
                 self.remove_completed, False)):
            item = tk.Frame(bar, bg=WHITE, cursor="hand2")
            img = self._img(ico)
            if img:
                tk.Label(item, image=img, bd=0, bg=WHITE,
                         cursor="hand2").pack(side="left", padx=(4, 4))
            lbl = tk.Label(item, text=text, fg=color, bg=WHITE,
                           font=("Segoe UI", 10, "bold"), cursor="hand2")
            lbl.pack(side="left")
            if dd:
                tk.Label(item, text="▾", fg=color, bg=WHITE,
                         font=("Segoe UI", 9), cursor="hand2").pack(side="left",
                                                                    padx=(3, 0))
            item.bind("<Button-1>", lambda e, c=cmd: c())
            for child in item.winfo_children():
                child.bind("<Button-1>", lambda e, c=cmd: c())
            self._pressable([item] + item.winfo_children())
            item.pack(side="left", padx=6)
            tk.Frame(bar, bg=SEP, width=1).pack(side="left",
                                                      fill="y", pady=4)
        self.row_host = tk.Frame(p, bg=WHITE)
        self.row_host.pack(fill="both", expand=True, padx=8)
        cols = [T(c) for c in ("Thumbnail", "Source", "Destination",
                               "Duration", "Size", "Status")]
        # col_x[0] is the leading status-icon column; headers sit in col_x[1:].
        # Source shows a short "Link" and Destination an "Open" button, so the
        # columns can be narrow and everything fits the default 931 px window.
        widths = (28, 110, 90, 100, 70, 80, 170)
        self.col_x = [8]
        for w in widths:
            self.col_x.append(self.col_x[-1] + w + 12)
        head = tk.Frame(self.row_host, bg=HEAD, height=24)
        head.pack(fill="x")
        for i, c in enumerate(cols):
            tk.Label(head, text=c, fg=SUB, bg=HEAD,
                     font=("Segoe UI", 9)).place(x=self.col_x[i + 1], y=3)
        canvas = tk.Canvas(self.row_host, bg=WHITE, highlightthickness=0)
        vsb = ttk.Scrollbar(self.row_host, orient="vertical",
                            command=canvas.yview)
        self.list_frame = tk.Frame(canvas, bg=WHITE)
        win = canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True, pady=(2, 0))
        vsb.pack(side="right", fill="y")
        self.canvas = canvas
        self.vsb = vsb
        self.canvas_win = win
        self._sb_shown = True
        self.list_frame.bind("<Configure>", self._on_list_resize)
        canvas.bind("<Configure>", self._on_canvas_resize)
        self.row_widgets = {}
        return p

    def _on_list_resize(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_scrollbar()

    def _on_canvas_resize(self, event=None):
        if event is not None:
            self.canvas.itemconfigure(self.canvas_win, width=event.width)
        self._update_scrollbar()

    def _update_scrollbar(self):
        """Hide the scrollbar until the rows overflow the list area.  The
        scrollbar sits beside the canvas (never over the rows), so the ✕
        button stays fully visible even when the bar is shown."""
        region = self.canvas.bbox("all")
        need = bool(region) and region[3] - region[1] > \
            self.canvas.winfo_height() + 1
        if need != self._sb_shown:
            if need:
                self.vsb.pack(side="right", fill="y")
            else:
                self.vsb.pack_forget()
            self._sb_shown = need
            # canvas width changed with the bar -> resize the row window
            self.root.after_idle(
                lambda: self.canvas.itemconfigure(
                    self.canvas_win, width=self.canvas.winfo_width()))

    def _make_row(self, t):
        row = tk.Frame(self.list_frame, bg=WHITE, height=86)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)  # children use place(), so keep fixed height
        icon = tk.Label(row, bd=0, bg=WHITE)
        img = self._img(self.ICONS.get(t.status, "st_wait.png"))
        if img:
            icon.configure(image=img)
        icon.place(x=(self.col_x[0] + self.col_x[1]) // 2, y=43,
                   anchor="center")
        thumb = tk.Label(row, bg=THUMB, width=13, height=4,
                         highlightthickness=1, highlightbackground=SEP,
                         cursor="hand2")
        thumb.place(x=self.col_x[1], y=4)
        thumb.bind("<Button-1>", lambda e, tt=t: self.play_task(tt))
        # Source column: compact link that opens the video page
        src = tk.Label(row, text=T("Link") if t.kind == "download" else "",
                       fg=BLUE, bg=WHITE, font=("Segoe UI", 10, "underline"),
                       cursor="hand2")
        src.place(x=self.col_x[2], y=6)
        src.bind("<Button-1>",
                 lambda e, tt=t: self.open_task_link(tt))
        self._pressable([src])
        # Destination column: button opening Explorer with the file selected
        dst = tk.Label(row, text=T("Open"), fg=FG, bg=FIELD, bd=1,
                       relief="solid", font=("Segoe UI", 9, "bold"),
                       padx=12, pady=2, cursor="hand2")
        dst.place(x=self.col_x[3], y=4)
        dst.bind("<Button-1>",
                 lambda e, tt=t: self.open_task_file(tt))
        self._pressable([dst])
        dur = tk.Label(row, text="", fg=FG, bg=WHITE, font=("Segoe UI", 10))
        dur.place(x=self.col_x[4], y=6)
        size = tk.Label(row, text="", fg=FG, bg=WHITE, font=("Segoe UI", 10))
        size.place(x=self.col_x[5], y=6)
        status = tk.Label(row, text=T(t.status), fg=FG, bg=WHITE,
                          font=("Segoe UI", 10, "bold"))
        status.place(x=self.col_x[6], y=6)
        sub = tk.Label(row, text="", fg=SUB, bg=WHITE,
                       font=("Segoe UI", 9))
        sub.place(x=self.col_x[6], y=30)
        xbtn = tk.Label(row, text="✕", fg=FG, bg=WHITE,
                        font=("Segoe UI", 13), cursor="hand2")
        xbtn.place(relx=1.0, x=-8, y=6, anchor="ne")
        xbtn.bind("<Button-1>", lambda e, tt=t: self.remove_task(tt))
        self._pressable([xbtn])
        row.bind("<Double-1>", lambda e, tt=t: self.start_task(tt))
        w = {"row": row, "icon": icon, "thumb": thumb, "src": src, "dst": dst,
             "dur": dur, "size": size, "status": status, "sub": sub}
        self.row_widgets[t.id] = w
        for widget in list(w.values()) + [xbtn]:
            widget.bind("<Button-3>",
                        lambda e, tt=t: self._row_menu(tt, e))
        return w

    # ------------------------------------------------------- context menu
    def _row_menu(self, t, event):
        running = t.status in ("Downloading", "Processing", "Stopping")
        if t.status == "Done" and not (t.final_path
                                       and os.path.exists(t.final_path)):
            if t.kind == "download":
                core._locate_output(t)   # resolve file of pre-fix completions
        final = t.final_path if (t.final_path
                                 and os.path.exists(t.final_path)) else None
        on = "normal"
        off = "disabled"
        m = self._themed_menu(self.root)
        m.add_command(
            label=T("Start"),
            state=on if (not running and t.status != "Done") else off,
            command=lambda: self.start_task(t))
        m.add_command(
            label=T("Restart"), state=on if not running else off,
            command=lambda: self.restart_task(t))
        m.add_command(label=T("Pause"), state=on if running else off,
                      command=lambda: self.pause_task(t))
        m.add_command(label=T("Cancel"), state=on if running else off,
                      command=lambda: self.cancel_task(t))
        m.add_command(label=T("Remove"), command=lambda: self.remove_task(t))
        m.add_command(label=T("Properties..."),
                      command=lambda: self.task_properties(t))
        m.add_separator()
        m.add_command(label=T("Play"), state=on if final else off,
                      command=lambda: os.startfile(final))
        m.add_command(label=T("Open Folder"), command=lambda: self.open_task_folder(t))
        m.add_command(label=T("Copy File Name"), state=on if final else off,
                      command=lambda: self._clipboard(
                          os.path.basename(final)))
        m.add_command(label=T("Rename"), state=on if final else off,
                      command=lambda: self.rename_task(t))
        m.add_separator()
        m.add_command(label=T("Copy URL"),
                      command=lambda: self._clipboard(t.source))
        m.add_command(
            label=T("Open Web Page"),
            state=on if (t.kind == "download"
                         and t.source.startswith("http")) else off,
            command=lambda: webbrowser.open(t.source))
        self._ctx_menu = m
        m.tk_popup(event.x_root, event.y_root)

    def pause_task(self, t):
        if t.status in ("Downloading", "Processing"):
            t.interrupt = "pause"
            t.status = "Stopping"

    def cancel_task(self, t):
        if t.status in ("Downloading", "Processing"):
            t.interrupt = "cancel"
            t.status = "Stopping"
            if t.proc:
                t.proc.terminate()

    def restart_task(self, t):
        if t.status in ("Downloading", "Processing", "Stopping"):
            return
        t.restart = True
        t.status = "Queued"
        t.pct = None
        t.note = ""
        self.start_task(t)

    def _clipboard(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            pass

    def _task_out_dir(self, t):
        if t.final_path:
            return os.path.dirname(t.final_path)
        if t.kind == "convert" and t.cv_opts.get("same_folder"):
            return os.path.dirname(t.source)
        return t.folder

    def open_task_link(self, t):
        """Source column 'Link': open the video page in the browser."""
        if t.kind == "download" and t.source.startswith("http"):
            webbrowser.open(t.source)

    def open_task_file(self, t):
        """Destination column 'Open': Explorer with the file selected,
        falling back to the plain folder while the file is not there yet."""
        if not t.final_path and t.status == "Done" and t.kind == "download":
            core._locate_output(t)
        f = t.final_path
        if f and os.path.exists(f):
            try:
                subprocess.Popen(
                    ["explorer", "/select,", os.path.normpath(f)])
                return
            except OSError:
                pass
        self.open_task_folder(t)

    def open_task_folder(self, t):
        folder = self._task_out_dir(t)
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        except OSError:
            pass

    def _ask_new_name(self, old_name):
        """Rename prompt sized to the task: entry spans the whole window,
        which is twice as wide as the classic prompt."""
        dlg = tk.Toplevel(self.root)
        self._titlebar(dlg)
        dlg.title(T("Rename"))
        dlg.configure(bg=WHITE)
        dlg.resizable(False, False)
        W, H = 760, 150
        dlg.geometry(f"{W}x{H}")
        tk.Label(dlg, text=T("New file name:"), bg=WHITE, fg=FG,
                 font=("Segoe UI", 10, "bold")).place(x=16, y=14)
        ent = tk.Entry(dlg, font=("Segoe UI", 11), bg=FIELD, fg=FG,
                       highlightthickness=1, highlightbackground=SEP)
        ent.place(x=16, y=40, width=W - 32)
        ent.insert(0, old_name)
        ent.select_range(0, tk.END)
        ent.focus_set()
        box = tk.Frame(dlg, bg=WHITE)
        box.place(relx=1.0, x=-16, y=H - 56, anchor="se")
        res = {"v": None}

        def ok(event=None):
            res["v"] = ent.get()
            dlg.destroy()

        tk.Button(box, text=T("OK"), bd=1, relief="solid", bg=WHITE, fg=FG,
                  activebackground=PRESSED, font=("Segoe UI", 10, "bold"),
                  padx=24, pady=4, command=ok).pack(side="left", padx=(0, 8))
        tk.Button(box, text=T("Cancel"), bd=1, relief="solid", bg=WHITE,
                  fg=FG, activebackground=PRESSED, font=("Segoe UI", 10),
                  padx=24, pady=4,
                  command=dlg.destroy).pack(side="left")
        dlg.bind("<Return>", ok)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.transient(self.root)
        dlg.grab_set()
        self._style_buttons(dlg)
        self.root.wait_window(dlg)
        return res["v"]

    def rename_task(self, t):
        path = t.final_path
        if not path or not os.path.exists(path):
            return
        new = self._ask_new_name(os.path.basename(path))
        if not new:
            return
        new = "".join(c for c in new if c not in '\\/:*?"<>|').strip()
        if not new:
            return
        if not os.path.splitext(new)[1]:
            new += os.path.splitext(path)[1]
        target = os.path.join(os.path.dirname(path), new)
        try:
            os.replace(path, target)
            t.final_path = target
            if t.kind == "convert":
                t.title = os.path.splitext(new)[0]
        except OSError as e:
            messagebox.showerror(APP_NAME, T("Rename failed:") + " " + str(e))

    def task_properties(self, t):
        dlg = tk.Toplevel(self.root)
        self._titlebar(dlg)
        dlg.title(T("Properties") + " - "
                  + (t.title or os.path.basename(t.source)))
        dlg.resizable(False, False)
        dlg.configure(bg=WHITE)
        final = t.final_path if (t.final_path
                                 and os.path.exists(t.final_path)) else None
        opts = t.dl_opts if t.kind == "download" else t.cv_opts
        if t.kind == "download":
            opt_text = (T("playlist") if opts.get("playlist")
                        else T("single item")) \
                + (", " + T("audio (mp3)") if opts.get("mp3") else "") \
                + f", {T('segments:')} {opts.get('segments', 4)}"
        else:
            codec = opts.get("vcodec") or opts.get("acodec") or ""
            opt_text = (f"{T('container:')} {opts.get('container', '')}"
                        f", {T('codec:')} {codec}, "
                        f"{T('bitrate:')} {opts.get('abr', '192k')}")
        rows = [
            (T("Type:"), T("Video download") if t.kind == "download"
             else T("File conversion")),
            (T("Status:"), self._status_text(t)),
            (T("Source:"), t.source),
            (T("Title:"), t.title or "-"),
            (T("Folder:"), self._task_out_dir(t)),
            (T("Output file:"), final or "-"),
            (T("Duration:"), t.duration_text or "-"),
            (T("Size:"), t.size_display() or "-"),
            (T("Options:"), opt_text),
        ]
        for i, (k, v) in enumerate(rows):
            tk.Label(dlg, text=k, bg=WHITE, fg=SUB,
                     font=("Segoe UI", 9, "bold")
                     ).grid(row=i, column=0, sticky="w", padx=(12, 6),
                            pady=3)
            tk.Label(dlg, text=v, bg=WHITE, fg=FG, font=("Segoe UI", 9),
                     wraplength=420, justify="left"
                     ).grid(row=i, column=1, sticky="w", padx=(0, 12), pady=3)
        tk.Button(dlg, text=T("Close"), bd=1, relief="solid", bg=WHITE,
                  font=("Segoe UI", 9), padx=16, pady=3,
                  command=dlg.destroy).grid(row=len(rows), column=1,
                                            sticky="e", padx=12, pady=(8, 12))

    # ------------------------------------------------------------- actions
    def _new_task(self, kind, source, folder):
        t = core.Task(kind, source, os.path.normpath(folder))
        if kind == "download":
            # this exact video was downloaded before: reuse its cached
            # thumbnail right away, without waiting for a new download
            vid = self._thumb_index.get(norm_url(source))
            if vid:
                t.thumb_path = vid
        with self._lock:
            self.tasks.append(t)
        self._make_row(t)
        self._save_tasks()
        return t

    def _load_thumb_index(self):
        try:
            with open(THUMB_INDEX, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _note_thumb(self, t):
        """Remember source URL -> video id so re-adding the URL instantly
        shows the cached preview again."""
        if t.kind != "download" or not t.thumb_path:
            return
        key = norm_url(t.source)
        if self._thumb_index.get(key) != t.thumb_path:
            self._thumb_index[key] = t.thumb_path
            try:
                os.makedirs(THUMB_DIR, exist_ok=True)
                with open(THUMB_INDEX, "w", encoding="utf-8") as f:
                    json.dump(self._thumb_index, f, ensure_ascii=False)
            except OSError:
                pass

    def add_download(self, start):
        url = self.d_url.get().strip()
        if not url:
            messagebox.showinfo(APP_NAME, T("Enter a URL first."))
            return
        self._remember(url)
        folder = ensure_download_folder(
            self.d_folder.get() or self.folder, self.folder)
        self.d_folder.set(folder)
        self.folder = folder
        t = self._new_task("download", url, folder)
        q = self.d_quality.current()
        if self.d_what.current() == 0:
            fmt = core.video_fmt(core.VIDEO_QUALITIES[q][1])
            mp3 = False
        else:
            fmt = core.audio_fmt(core.AUDIO_QUALITIES[q][1])
            mp3 = True
        t.dl_opts = {"fmt": fmt, "playlist": self.d_playlist.get(),
                     "mp3": mp3,
                     "segments": int(self.d_segments.get() or 4)}
        if self.d_cv_on.get():
            ext, group = core.CONTAINERS[self.d_cv_cont.get()]
            key = "vcodec" if group == "video" else "acodec"
            t.dl_opts["cv"] = {"container": ext, key: self.d_cv_codec.get()}
        self.cfg.update({"dl_container": self.d_cv_cont.get(),
                         "dl_codec": self.d_cv_codec.get()})
        cb = self.d_cookies.get()
        self.cookies_browser = None if cb == "none" else cb
        self._env["cookies_browser"] = self.cookies_browser
        self._save_config()
        if start:
            self.start_task(t)
        self.show_tab("Tasks")

    def add_convert(self, start):
        src = self.c_src.get().strip()
        if not src or not os.path.exists(src):
            messagebox.showinfo(APP_NAME, T("Choose an existing source file."))
            return
        src_dir = os.path.dirname(os.path.normpath(src))
        folder = src_dir if self.c_same.get() else \
            self.c_folder.get() or self._cv_folder
        folder = ensure_download_folder(folder, self.folder)
        self.c_folder.set(folder)
        if not self.c_same.get():
            self._cv_folder = folder
            self.cfg["convert_folder"] = folder
            self._save_config()
        t = self._new_task("convert", src, folder)
        group = core.CONTAINERS[self.c_container.get()][1]
        t.cv_opts = {"container": core.CONTAINERS[self.c_container.get()][0],
                     "same_folder": self.c_same.get(),
                     "abr": self.cfg.get("abr", "192k"),
                     "preset": self.cfg.get("preset", "medium"),
                     "crf": self.cfg.get("crf", 20),
                     "extra": self.cfg.get("extra", "")}
        if group == "video":
            t.cv_opts["vcodec"] = self.c_codec.get()
        else:
            t.cv_opts["acodec"] = self.c_codec.get()
        if start:
            self.start_task(t)
        self.show_tab("Tasks")

    def start_task(self, t):
        if t.status in ("Downloading", "Processing", "Stopping", "Done"):
            return
        t.interrupt = None
        t.note = ""
        t.status = "Downloading" if t.kind == "download" else "Processing"
        target = core.run_download if t.kind == "download" \
            else core.run_convert
        args = (t, self._env, THUMB_DIR) if t.kind == "download" else (t, self._env)
        t.thread = threading.Thread(target=target, args=args, daemon=True)
        t.thread.start()

    def start_all(self):
        for t in list(self.tasks):
            if t.status in ("Queued", "Paused", "Canceled", "Failed"):
                self.start_task(t)

    def pause_all(self):
        for t in list(self.tasks):
            if t.status in ("Downloading", "Processing"):
                t.interrupt = "pause"
                t.status = "Stopping"

    def tb_paste(self):
        try:
            url = self.root.clipboard_get().strip()
        except Exception:
            return
        if url:
            self.d_url.set(url)
            self.add_download(start=True)

    def tb_add_files(self):
        files = filedialog.askopenfilenames(
            title=T("Add files to convert"),
            filetypes=[(T("Video/Audio"), "*.mp4 *.mkv *.webm *.mov *.avi "
                        "*.mp3 *.m4a *.wav *.flac"),
                       (T("All files"), "*.*")])
        for f in files:
            self._set_src(f)
            self.add_convert(start=False)

    def play_task(self, t):
        """Open the finished video in the system player (double-click on
        the thumbnail, same as the context-menu Play item)."""
        final = t.final_path
        if not (final and os.path.exists(final)) and t.status == "Done":
            core._locate_output(t)
            final = t.final_path
        if final and os.path.exists(final):
            os.startfile(final)

    def remove_task(self, t):
        if t.status in ("Downloading", "Processing"):
            t.interrupt = "cancel"
            t.status = "Stopping"
            if t.proc:
                t.proc.terminate()
            return
        w = self.row_widgets.pop(t.id, None)
        if w:
            for child in w["row"].winfo_children():
                child.destroy()
            w["row"].destroy()
        with self._lock:
            if t in self.tasks:
                self.tasks.remove(t)
        # ✕ means "I don't want this video" — but only a canceled download
        # discards its partial files; pause/error/app-exit keep them.
        if t.kind == "download" and t.status == "Canceled":
            core.cleanup_partial(t)
        elif t.kind == "download" and t.status == "Stopping":
            t.dropped = True  # the worker cleans up once its process ends
        self._save_tasks()

    def _remove_finished(self):
        for t in list(self.tasks):
            if t.status in ("Done", "Failed", "Canceled"):
                self.remove_task(t)

    remove_selected = _remove_finished  # toolbar "Remove" clears finished

    def remove_completed(self):
        for t in list(self.tasks):
            if t.status == "Done":
                self.remove_task(t)

    def change_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder,
                                         title=T("Download folder"))
        if folder:
            self.folder = ensure_download_folder(folder)
            self.d_folder.set(self.folder)
            self._save_config()

    def open_folder(self):
        self.folder = ensure_download_folder(self.folder)
        os.startfile(self.folder)

    # ------------------------------------------------------------- refresh
    # Queued (waiting to (re)download) and Paused share the yellow
    # pause-bars marker, per spec.
    ICONS = {"Queued": "st_pause.png", "Downloading": "st_run.png",
             "Processing": "st_run.png", "Paused": "st_pause.png",
             "Stopping": "st_pause.png", "Done": "st_done.png",
             "Failed": "st_fail.png", "Canceled": "st_fail.png"}

    def _tick(self):
        try:
            self._tick_body()
        finally:
            # a transient error (e.g. a file vanishing under _locate_output)
            # must never stop the whole UI refresh loop
            self.root.after(400, self._tick)

    def _tick_body(self):
        with self._lock:
            tasks = list(self.tasks)
        sig = [(t.id, t.status) for t in tasks]
        if sig != self._saved_sig:
            self._saved_sig = sig
            self._save_tasks()
        active = 0
        for t in tasks:
            w = self.row_widgets.get(t.id)
            if not w:
                continue
            if t.status in ("Downloading", "Processing", "Stopping"):
                active += 1
            if t.thumb_path:
                self._note_thumb(t)
            if (t.status == "Done" and t.kind == "download"
                    and t.thumb_path and t.final_path
                    and not core.thumb_cached(THUMB_DIR, t.thumb_path)
                    and not getattr(t, "_thumb_repair", False)):
                t._thumb_repair = True
                threading.Thread(
                    target=core.ensure_thumbnail,
                    args=(t, self._env, THUMB_DIR), daemon=True).start()
            if (t.status == "Done" and t.kind == "download"
                    and not t.final_path and not getattr(t, "_loc", False)):
                t._loc = True
                core._locate_output(t)   # fill final_path for the size column
            if w.get("icon_status") != t.status:
                img = self._img(self.ICONS.get(t.status, "st_wait.png"))
                if img:
                    w["icon"].configure(image=img)
                    w["icon_status"] = t.status
            w["status"].configure(
                text=self._status_text(t),
                fg=RED if t.status in ("Failed", "Canceled") else
                (GREEN if t.status == "Done" else FG))
            sub = ""
            if t.speed or t.eta:
                sub = f"{t.speed}   {T('ETA')} {t.eta}"
            if t.item:
                sub = f"{t.item}   {sub}"
            if t.status in ("Failed", "Canceled") and t.note:
                sub = t.note
            elif t.status in ("Queued", "Downloading") and \
                    getattr(t, "retry_note", ""):
                sub = t.retry_note
            w["sub"].configure(text=sub)
            w["dur"].configure(text=t.duration_text)
            w["size"].configure(text=t.size_display())
            # src/dst are static now ("Link" / "Open"); Explorer reveal uses
            # t.final_path resolved on click
            if t.thumb_path and HAS_PIL:
                cand = None
                for ext in ("jpg", "webp", "png"):
                    c = os.path.join(THUMB_DIR, f"{t.thumb_path}.{ext}")
                    if os.path.exists(c):
                        cand = c
                        break
                if cand and not getattr(w["thumb"], "_img", None):
                    try:
                        img = Image.open(cand)
                        img.thumbnail((104, 64))
                        photo = ImageTk.PhotoImage(img)
                        w["thumb"].configure(image=photo, width=0, height=0)
                        w["thumb"]._img = photo
                    except Exception:
                        # corrupt cache entry (e.g. a 0-byte file from a
                        # failed fetch): drop it so the next download
                        # sees it as missing and re-fetches a good image
                        try:
                            os.remove(cand)
                        except OSError:
                            pass
        n = len(tasks)
        self.lbl_count.configure(text=f"{n} {plural('task', n)}")
        self.lbl_status.configure(
            text=(T("Ready") if not active else
                  T("in_progress_fmt") %
                  {"n": active, "w": plural("task", active)}))

    # ------------------------------------------------------ press feedback
    def _pressable(self, widgets, base=None):
        """Darken the given widgets while the mouse button is held."""
        base = base or WHITE
        dark = shade(base, -0.22)

        def paint(color):
            def handler(event):
                for c in widgets:
                    try:
                        c.configure(bg=color)
                    except tk.TclError:
                        pass
            return handler

        for c in widgets:
            # add="+": without it this REPLACES the action binding bound
            # earlier to the same <Button-1> sequence (button darkens but
            # never runs its command).
            c.bind("<ButtonPress-1>", paint(dark), add="+")
            c.bind("<ButtonRelease-1>", paint(base), add="+")

    def _style_buttons(self, w):
        """Make every tk.Button/Menubutton visibly darken while pressed."""
        if isinstance(w, (tk.Button, tk.Menubutton)):
            w.configure(activebackground=shade(PRESSED, -0.10),
                        activeforeground=w.cget("fg"))
        for c in w.winfo_children():
            self._style_buttons(c)

    def _status_text(self, t):
        base = T(t.status)
        if t.pct is not None and t.status in ("Downloading", "Processing"):
            return f"{base} {t.pct:.1f}%"
        return base

    # ------------------------------------------------------------ settings
    def open_settings(self):
        win = getattr(self, "_settings_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        dlg = tk.Toplevel(self.root)
        self._settings_win = dlg
        self._titlebar(dlg)
        dlg.title(T("Settings"))
        dlg.configure(bg=WHITE)
        dlg.resizable(False, False)
        W = 620
        dlg.geometry(f"{W}x560")
        self._center_over_root(dlg, W, 560)

        def title(i, s):
            tk.Label(dlg, text=s, bg=WHITE, fg=BLUE,
                     font=("Segoe UI", 12, "bold")
                     ).place(x=24, y=i, anchor="w")

        def line(i):
            tk.Frame(dlg, bg=SEP, height=1).place(x=24, y=i, width=W - 48)

        tk.Label(dlg, text=T("Settings"), bg=WHITE, fg=FG,
                 font=("Segoe UI", 16, "bold")).place(x=24, y=18, anchor="w")
        line(48)

        # Language
        tk.Label(dlg, text=T("Language:"), bg=WHITE, fg=FG,
                 font=("Segoe UI", 10, "bold")
                 ).place(x=24, y=70, anchor="w")
        codes = [c for c, _ in LANGS]
        names = [n for _, n in LANGS]
        lang_box = ttk.Combobox(dlg, values=names, state="readonly",
                                width=18)
        try:
            lang_box.current(codes.index(self.cfg.get("lang", "en")))
        except ValueError:
            lang_box.current(0)
        lang_box.place(x=24, y=100, anchor="w")

        # Theme
        tk.Label(dlg, text=T("Theme:"), bg=WHITE, fg=FG,
                 font=("Segoe UI", 10, "bold")
                 ).place(x=24, y=150, anchor="w")
        tk_names = [T(k) for k in THEMES]
        theme_box = ttk.Combobox(dlg, values=tk_names, state="readonly",
                                 width=18)
        try:
            theme_box.current(list(THEMES).index(
                self.cfg.get("theme", "Obsidian Copper")))
        except ValueError:
            theme_box.current(0)
        theme_box.place(x=24, y=180, anchor="w")

        # Autostart
        auto = tk.BooleanVar(value=bool(self.cfg.get("autostart", False)))
        tk.Checkbutton(dlg, text=T("Launch with Windows"), variable=auto,
                       bg=WHITE, fg=FG, activebackground=PRESSED,
                       selectcolor=FIELD,
                       font=("Segoe UI", 10)).place(x=24, y=225, anchor="w")

        # Auto-restart interval
        tk.Label(dlg, text=T("Automatically restart a download after an "
                             "error or a connection drop, after a delay of"),
                 bg=WHITE, fg=FG, font=("Segoe UI", 10), wraplength=W - 120,
                 justify="left").place(x=24, y=270, anchor="w")
        delay = tk.Spinbox(dlg, from_=0, to=600, width=5, bg=FIELD, fg=FG,
                           highlightthickness=1, highlightbackground=SEP,
                           font=("Segoe UI", 10))
        delay.delete(0, "end")
        delay.insert(0, str(int(self.cfg.get("retry_delay", 10))))
        delay.place(x=24, y=305, anchor="w")
        tk.Label(dlg, text=T("seconds (0 = disabled)"), bg=WHITE, fg=SUB,
                 font=("Segoe UI", 9)).place(x=90, y=307, anchor="w")

        tk.Label(dlg, text=T("Language and theme are applied after the app "
                             "restarts."), bg=WHITE, fg=SUB,
                 font=("Segoe UI", 9), wraplength=W - 60,
                 justify="left").place(x=24, y=350, anchor="w")
        line(385)

        def save():
            lang = codes[lang_box.current()]
            theme = list(THEMES)[theme_box.current()]
            try:
                seconds = max(0, min(600, int(delay.get())))
            except ValueError:
                seconds = 10
            self.cfg.update({"lang": lang, "theme": theme,
                             "retry_delay": seconds,
                             "autostart": bool(auto.get())})
            try:
                self._set_autostart(bool(auto.get()))
            except OSError:
                pass
            self._save_config()
            if lang != old_lang or theme != old_theme:
                dlg.destroy()
                self._restart()
            else:
                self._env["retry_delay"] = seconds
                dlg.destroy()

        old_lang = self.cfg.get("lang", "en")
        old_theme = self.cfg.get("theme", "Obsidian Copper")
        box = tk.Frame(dlg, bg=WHITE)
        box.place(relx=1.0, x=-24, y=430, anchor="e")
        tk.Button(box, text=T("Save"), bd=1, relief="solid", bg=WHITE, fg=FG,
                  activebackground=PRESSED, font=("Segoe UI", 10, "bold"),
                  padx=24, pady=5, command=save).pack(side="left",
                                                      padx=(0, 10))
        tk.Button(box, text=T("Cancel"), bd=1, relief="solid", bg=WHITE,
                  fg=FG, activebackground=PRESSED, font=("Segoe UI", 10),
                  padx=24, pady=5, command=dlg.destroy).pack(side="left")
        dlg.transient(self.root)
        self._style_buttons(dlg)

    @staticmethod
    def _set_autostart(enable):
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        try:
            if enable:
                cmd = (f'"{sys.executable}" '
                       f'"{os.path.join(ROOT, "oxvideodownloader.py")}"')
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)

    def _restart(self):
        """Relaunch the app so a new language/theme takes effect."""
        self.cfg["maximized"] = (self.root.state() == "zoomed")
        self.cfg["geometry"] = self.root.geometry()
        self._save_config()
        try:
            subprocess.Popen([sys.executable,
                              os.path.join(ROOT, "oxvideodownloader.py")],
                             cwd=ROOT)
        except OSError:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
