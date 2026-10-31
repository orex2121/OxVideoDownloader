"""OxVideoDownloader core: task model, yt-dlp download worker, ffmpeg convert worker."""

import glob
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request

from .i18n import T

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


class TaskInterrupt(Exception):
    pass


# ---------------------------------------------------------------- format maps
VIDEO_QUALITIES = [
    ("Best quality available", ""),
    ("2160p (4K)", "2160"),
    ("1440p (2K)", "1440"),
    ("1080p (Full HD)", "1080"),
    ("720p (HD)", "720"),
    ("480p", "480"),
    ("360p", "360"),
]
AUDIO_QUALITIES = [
    ("Best quality available", "best"),
    ("High (~256 kbps)", "high"),
    ("Medium (~128 kbps)", "medium"),
]
CONTAINERS = {
    "MP4 .mp4": ("mp4", "video"),
    "MKV .mkv": ("mkv", "video"),
    "WEBM .webm": ("webm", "video"),
    "MOV .mov": ("mov", "video"),
    "AVI .avi": ("avi", "video"),
    "MP3 .mp3": ("mp3", "audio"),
    "M4A .m4a": ("m4a", "audio"),
    "WAV .wav": ("wav", "audio"),
    "FLAC .flac": ("flac", "audio"),
}
VIDEO_CODECS = {
    "H.264": "libx264",
    "H.265 (HEVC)": "libx265",
    "VP9": "libvpx-vp9",
    "AV1": "libsvtav1",
    "Copy (no re-encode)": "copy",
}
AUDIO_DEFAULT = {
    "mp4": ("aac", ["-c:a", "aac", "-b:a", "{abr}"]),
    "mkv": ("aac", ["-c:a", "aac", "-b:a", "{abr}"]),
    "mov": ("aac", ["-c:a", "aac", "-b:a", "{abr}"]),
    "webm": ("opus", ["-c:a", "libopus", "-b:a", "{abr}"]),
    "avi": ("mp3", ["-c:a", "libmp3lame", "-b:a", "{abr}"]),
    "mp3": ("mp3", ["-c:a", "libmp3lame", "-b:a", "{abr}"]),
    "m4a": ("aac", ["-c:a", "aac", "-b:a", "{abr}"]),
    "wav": ("pcm", ["-c:a", "pcm_s16le"]),
    "flac": ("flac", ["-c:a", "flac"]),
}
AUDIO_CODECS = {
    "AAC": ["-c:a", "aac", "-b:a", "{abr}"],
    "MP3": ["-c:a", "libmp3lame", "-b:a", "{abr}"],
    "Opus": ["-c:a", "libopus", "-b:a", "{abr}"],
    "PCM (uncompressed)": ["-c:a", "pcm_s16le"],
    "FLAC": ["-c:a", "flac"],
    "Copy (no re-encode)": ["-c:a", "copy"],
}
CONTAINER_GROUP = {ext: group for ext, group in CONTAINERS.values()}

# Which codecs a given container can legally mux. Picking an unsupported pair
# makes ffmpeg either error out ("Nothing was written into output file") or,
# worse, write an unplayable stream (WAV + AAC).
CONTAINER_AUDIO_CODECS = {
    "mp4": ["AAC", "MP3", "Copy (no re-encode)"],
    "mkv": list(AUDIO_CODECS),
    "mov": ["AAC", "MP3", "Copy (no re-encode)"],
    "webm": ["Opus", "Copy (no re-encode)"],
    "avi": ["MP3", "AAC", "Copy (no re-encode)"],
    "mp3": ["MP3", "Copy (no re-encode)"],
    "m4a": ["AAC", "MP3", "Copy (no re-encode)"],
    "wav": ["PCM (uncompressed)", "MP3", "Copy (no re-encode)"],
    "flac": ["FLAC", "Copy (no re-encode)"],
}
CONTAINER_VIDEO_CODECS = {
    "mp4": ["H.264", "H.265 (HEVC)", "AV1", "Copy (no re-encode)"],
    "mkv": list(VIDEO_CODECS),
    "mov": ["H.264", "H.265 (HEVC)", "AV1", "Copy (no re-encode)"],
    "webm": ["VP9", "AV1", "Copy (no re-encode)"],
    "avi": ["H.264", "Copy (no re-encode)"],
}


def codecs_for(container_label):
    """Codec labels that are valid inside the chosen container."""
    ext, group = CONTAINERS[container_label]
    if group == "video":
        return CONTAINER_VIDEO_CODECS.get(ext, list(VIDEO_CODECS))
    return CONTAINER_AUDIO_CODECS.get(ext, list(AUDIO_CODECS))


def video_fmt(height):
    if not height:
        return "bv*+ba/b"
    return f"bv*[height<={height}]+ba/b[height<={height}]"


def audio_fmt(level):
    if level == "high":
        return "bestaudio[abr>=200]/bestaudio/best"
    if level == "medium":
        return "bestaudio[abr<=160]/bestaudio/best"
    return "bestaudio/best"


# --------------------------------------------------------------------- helpers
def human_size(nbytes):
    if not nbytes:
        return ""
    n = float(nbytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def human_time(seconds):
    if seconds is None:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return (f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")


# FFmpeg is not shipped inside the repository; on first run it is fetched
# from one of these official static-build archives.
FFMPEG_URLS = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-gpl.zip",
)


def download_ffmpeg(dest_dir, progress=None, cancel=None):
    """Download a static FFmpeg build and unpack ffmpeg.exe/ffprobe.exe.

    progress(done, total, phase) is called as bytes arrive: phase is
    "download" while fetching the zip archive and "extract" while the two
    binaries are pulled out of it.  cancel is an optional threading.Event:
    once it is set the transfer aborts, partial files are cleaned up and
    the call returns False.  Tries each FFMPEG_URLS entry in order and
    returns True only when both binaries end up in dest_dir.
    """
    import zipfile

    class _Cancelled(Exception):
        pass

    def _chk():
        if cancel is not None and cancel.is_set():
            raise _Cancelled()

    try:
        from curl_cffi import requests as cffi
    except Exception:
        cffi = None
    for url in FFMPEG_URLS:
        tmp = os.path.join(dest_dir, "ffmpeg_setup_tmp.zip")
        try:
            _chk()
            os.makedirs(dest_dir, exist_ok=True)
            done, total = 0, 0
            if cffi:
                # curl_cffi ships its own CA bundle; plain urllib inherits
                # the system store, which frequently fails to validate here
                r = cffi.get(url, stream=True, timeout=(15, 60),
                             impersonate="chrome", allow_redirects=True)
                try:
                    if r.status_code != 200:
                        raise OSError("HTTP %s" % r.status_code)
                    total = int(r.headers.get("content-length") or 0)
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(65536):
                            _chk()
                            f.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress(done, total, "download")
                finally:
                    r.close()
            else:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    total = int(r.headers.get("Content-Length") or 0)
                    with open(tmp, "wb") as f:
                        while True:
                            _chk()
                            chunk = r.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress(done, total, "download")
            _chk()
            if progress:
                progress(0, 0, "extract")
            with zipfile.ZipFile(tmp) as z:
                for name in z.namelist():
                    base = name.replace("\\", "/").rsplit("/", 1)[-1]
                    if base in ("ffmpeg.exe", "ffprobe.exe"):
                        with z.open(name) as src, open(
                                os.path.join(dest_dir, base), "wb") as dst:
                            while True:
                                _chk()
                                chunk = src.read(1 << 20)
                                if not chunk:
                                    break
                                dst.write(chunk)
            os.remove(tmp)
            if (os.path.isfile(os.path.join(dest_dir, "ffmpeg.exe"))
                    and os.path.isfile(os.path.join(dest_dir, "ffprobe.exe"))):
                return True
        except _Cancelled:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return False


def ffprobe_duration(ffprobe, path):
    if not ffprobe or not path:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", path],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads(out.stdout or "{}")
        return float(data["format"]["duration"])
    except Exception:
        return None


# ------------------------------------------------------------------ task model
class Task:
    _seq = 0

    def __init__(self, kind, source, folder):
        Task._seq += 1
        self.id = Task._seq
        self.kind = kind            # 'download' | 'convert'
        self.source = source        # URL or input file
        self.folder = folder
        self.title = ""
        self.status = "Queued"      # Queued/Downloading/Paused/Processing/
                                    # Done/Failed/Canceled/Stopping
        self.pct = None             # float 0..100
        self.downloaded = None      # bytes downloaded (downloads)
        self.total_bytes = None     # expected total (downloads / file size)
        self.speed = ""
        self.eta = ""
        self.duration_text = ""
        self.size_text = ""
        self.note = ""
        self.thumb_path = None
        self.final_path = None
        self.item = ""              # playlist counter
        self.interrupt = None       # None | 'pause' | 'cancel'
        self.thread = None
        self.proc = None            # ffmpeg subprocess (convert)
        self.dl_opts = {}           # download settings snapshot
        self.cv_opts = {}           # convert settings snapshot
        self.restart = False        # re-download even if the file exists
        self.retry_note = ""        # auto-restart countdown shown in the UI
        self.thumb_dir = None       # thumbnail cache dir (set by run_download)
        self.dropped = False        # row removed while the worker was stopping

    def size_display(self):
        if self.final_path and os.path.exists(self.final_path):
            return human_size(os.path.getsize(self.final_path))
        if self.total_bytes:
            done = human_size(self.downloaded or 0)
            tot = human_size(self.total_bytes)
            return f"{done} / {tot}" if done else tot
        return ""

    def status_display(self):
        if self.status == "Downloading" and self.pct is not None:
            return f"Downloading {self.pct:.1f}%"
        if self.status == "Processing" and self.pct is not None:
            return f"Processing {self.pct:.1f}%"
        return self.status


# ---------------------------------------------------------------- download job
def run_download(t, cfg, thumb_dir):
    """Worker body for a download task. Mutates task fields; UI polls them."""
    o = t.dl_opts
    t.interrupt = None
    t.thumb_dir = thumb_dir
    opts = {
        "outtmpl": os.path.join(t.folder, "%(title)s [%(id)s].%(ext)s"),
        "format": o.get("fmt", "bv*+ba/b"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": not o.get("playlist", False),
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": o.get("segments", 4),
        "windowsfilenames": True,
        "merge_output_format": "mp4",
    }
    if t.restart:
        opts["overwrites"] = True
        t.restart = False
        t.final_path = None
    if o.get("mp3"):
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
             "preferredquality": "0"}]
    if cfg.get("ffmpeg"):
        opts["ffmpeg_location"] = cfg["ffmpeg"]
    if cfg.get("cookies_browser"):
        opts["cookiesfrombrowser"] = (cfg["cookies_browser"],)
    hook = _make_hook(t, thumb_dir)
    opts["progress_hooks"] = [hook]
    delay = max(0, int(cfg.get("retry_delay", 10)))
    attempt = 0
    while True:
        t.retry_note = ""
        try:
            os.makedirs(t.folder, exist_ok=True)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([t.source])
            _locate_output(t)
            ensure_thumbnail(t, cfg, thumb_dir)
            cv = t.dl_opts.get("cv") or {}
            if cv.get("container") and t.final_path and t.interrupt is None:
                _post_convert(t, cfg)
                return
            _finish(t)
            return
        except TaskInterrupt:
            _stopped(t)
            return
        except yt_dlp.utils.DownloadError as e:
            err = (str(e).splitlines() or ["download failed"])[0][:160]
        except Exception as e:
            if t.interrupt in ("pause", "cancel"):
                _stopped(t)
                return
            err = (str(e) or type(e).__name__)[:160]
        # Download failed (error / dropped connection). Wait `delay`
        # seconds and try again; yt-dlp resumes the partial .part file.
        if delay and t.interrupt is None and attempt < 8:
            attempt += 1
            t.status = "Queued"
            t.retry_note = T("Retrying in %(n)d s (attempt %(a)d)") % {
                "n": delay, "a": attempt}
            if not _sleep_interruptible(t, delay):
                _stopped(t)
                return
            continue
        t.status = "Failed"
        t.note = err
        t.retry_note = ""
        _stopped_cleanup(t)
        return


def _post_convert(t, cfg):
    """Auto re-encode a finished download into the container/codec picked
    on the Download tab; the converted file replaces final_path."""
    o = t.dl_opts.get("cv") or {}
    ffmpeg = cfg.get("ffmpeg")
    src = t.final_path
    container = o.get("container")
    if not ffmpeg or not src or not container or             os.path.splitext(src)[1].lower() == "." + container:
        _finish(t)
        return
    out = os.path.join(os.path.dirname(src),
                       os.path.splitext(os.path.basename(src))[0]
                       + "." + container)
    abr = cfg.get("abr", "192k")
    cmd = [ffmpeg, "-y", "-nostdin", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", "-i", src]
    group = CONTAINER_GROUP.get(container, "video")
    if group == "video":
        vcodec = VIDEO_CODECS.get(o.get("vcodec", "H.264"), "libx264")
        cmd += ["-c:v", vcodec]
        if vcodec in ("libx264", "libx265"):
            cmd += ["-preset", "medium",
                    "-crf", "24" if vcodec == "libx265" else "20"]
        if vcodec == "copy":
            cmd += ["-c:a", "copy"]
        else:
            aa = AUDIO_DEFAULT.get(
                container, ("aac", ["-c:a", "aac", "-b:a", "{abr}"]))[1]
            cmd += [a.replace("{abr}", abr) for a in aa]
    else:
        aa = AUDIO_CODECS.get(o.get("acodec", "AAC"), AUDIO_CODECS["AAC"])
        cmd += [a.replace("{abr}", abr) for a in aa] + ["-vn"]
    cmd += [out]  # muxer inferred from the extension
    t.status = "Processing"
    t.note = ""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        t.proc = proc
        for line in proc.stdout:
            if t.interrupt in ("pause", "cancel"):
                proc.terminate()
                break
            if os.path.exists(out):
                t.total_bytes = None
                t.downloaded = os.path.getsize(out)
        proc.wait()
        t.proc = None
        if t.interrupt in ("pause", "cancel"):
            _drop(out)
            _stopped(t)
        elif proc.returncode == 0 and os.path.exists(out):
            try:
                os.remove(src)
            except OSError:
                pass
            t.final_path = out
            _finish(t)
        else:
            err = (proc.stderr.read() or "").strip().splitlines()
            _drop(out)
            t.status = "Failed"
            t.note = ("convert: " + (err[-1] if err else "ffmpeg failed"))[:160]
    except Exception as e:
        t.proc = None
        _drop(out)
        t.status = "Failed"
        t.note = str(e)[:160]


def _sleep_interruptible(t, seconds):
    """Sleep up to `seconds` in 1s ticks; False if the task was interrupted."""
    for _ in range(seconds):
        if t.interrupt in ("pause", "cancel"):
            return False
        time.sleep(1)
    return t.interrupt not in ("pause", "cancel")


THUMB_EXTS = ("jpg", "webp", "png")


def _image_head_ok(head):
    """Recognise the few container formats a thumbnail cache may hold."""
    return (head[:3] == b"\xff\xd8\xff"                       # JPEG
            or head[:8] == b"\x89PNG\r\n\x1a\n"               # PNG
            or head[:6] in (b"GIF87a", b"GIF89a")             # GIF
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))  # WEBP


def _image_bytes_ok(data):
    return bool(data) and len(data) >= 100 and _image_head_ok(data[:12])


def thumb_cached(thumb_dir, vid):
    """True only if a *usable* preview image for this video id is on disk.

    An existence check is not enough: a failed fetch that left a 0-byte
    or truncated file behind would otherwise count as cached forever and
    the row would stay without a preview."""
    for e in THUMB_EXTS:
        try:
            with open(os.path.join(thumb_dir, f"{vid}.{e}"), "rb") as f:
                head = f.read(12)
        except OSError:
            continue
        if _image_head_ok(head):
            return True
    return False


def _grab_thumbnail(url, dest):
    """Fetch a thumbnail, write it only after verifying it really is an
    image.  Returns True on success; never leaves a corrupt file behind."""
    data = None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
    except Exception:
        data = None
    if not _image_bytes_ok(data):
        # some CDNs answer urllib's bare request with an empty body;
        # retry impersonating a real browser
        try:
            from curl_cffi import requests as _cffi
            r = _cffi.get(url, impersonate="chrome", timeout=15)
            if r.status_code == 200:
                data = r.content
        except Exception:
            pass
    if not _image_bytes_ok(data):
        try:
            os.remove(dest)
        except OSError:
            pass
        return False
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
    except OSError:
        return False
    return True


def ensure_thumbnail(t, cfg, thumb_dir):
    """Create a preview from the downloaded video when its CDN thumbnail
    could not be fetched.  This keeps previews working on networks where
    hosts such as i.ytimg.com are blocked or time out."""
    vid = t.thumb_path
    src = t.final_path
    ffmpeg = cfg.get("ffmpeg")
    if (not vid or not src or not ffmpeg or not thumb_dir
            or thumb_cached(thumb_dir, vid)
            or not os.path.isfile(src)):
        return False
    os.makedirs(thumb_dir, exist_ok=True)
    dest = os.path.join(thumb_dir, f"{vid}.jpg")
    tmp = os.path.join(thumb_dir, f"{vid}.tmp.jpg")
    cmd = [ffmpeg, "-y", "-nostdin", "-loglevel", "error",
           "-ss", "1", "-i", src, "-map", "0:v:0", "-frames:v", "1",
           "-vf", "scale=320:-2", "-q:v", "3", tmp]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0:
            with open(tmp, "rb") as f:
                valid = _image_head_ok(f.read(12))
            if valid:
                os.replace(tmp, dest)
                return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def _make_hook(t, thumb_dir):
    def hook(d):
        if t.interrupt == "pause":
            raise TaskInterrupt("pause")
        if t.interrupt == "cancel":
            raise TaskInterrupt("cancel")
        info = d.get("info_dict") or {}
        if info.get("title") and not t.title:
            t.title = info["title"]
        dur = info.get("duration")
        if dur and not t.duration_text:
            t.duration_text = human_time(dur)
            t.total_bytes = info.get("filesize") or info.get("filesize_approx")
        vid = info.get("id")
        # the real video id always wins over the one pre-set from the
        # thumbnail index (a stale or colliding index entry must never stick)
        if vid and t.thumb_path != vid:
            t.thumb_path = vid
        # (re)download of a video whose cached preview is missing: fetch it
        # again so the Tasks row gets its image even when the video id was
        # known before the download started.  One attempt per task run: the
        # hook fires on every progress chunk, a failing CDN must not be
        # hammered for the whole download.
        if vid and thumb_dir and not getattr(t, "_thumb_fetched", False):
            t._thumb_fetched = True
            if not thumb_cached(thumb_dir, vid):
                thumbs = info.get("thumbnails") or []
                best = None
                for th in thumbs:
                    if th.get("url") and (th.get("height") or 0) >= 120:
                        best = th
                if best is None and thumbs and thumbs[-1].get("url"):
                    best = thumbs[-1]
                if best:
                    ext = best.get("ext") or "jpg"
                    _grab_thumbnail(best["url"],
                                    os.path.join(thumb_dir, f"{vid}.{ext}"))
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") \
                or t.total_bytes
            got = d.get("downloaded_bytes") or 0
            if total:
                t.pct = got * 100.0 / total
                t.total_bytes = total
            t.downloaded = got
            spd = d.get("speed")
            t.speed = f"{spd / 1048576:.2f} MiB/s" if spd else ""
            t.eta = human_time(d.get("eta"))
            idx, cnt = info.get("playlist_index"), info.get("playlist_count")
            t.item = f"{idx}/{cnt}" if idx and cnt else ""
            t.status = "Downloading"
        elif d.get("status") == "finished":
            t.pct = 100.0
            t.status = "Processing"
    return hook


def _locate_output(t):
    """After a successful download, resolve the merged/postprocessed output
    path so UI actions (Play, Rename, Copy File Name) can use it."""
    vid = t.thumb_path
    if not vid:
        return
    pat = "*" + glob.escape(f"[{vid}].") + "*"
    try:
        best = None
        for f in glob.glob(os.path.join(t.folder, pat)):
            if f.lower().endswith((".part", ".ytdl", ".temp")):
                continue
            if best is None or os.path.getmtime(f) > os.path.getmtime(best):
                best = f
        if best:
            t.final_path = best
    except OSError:
        pass


def _finish(t):
    if t.interrupt == "pause":
        t.status = "Paused"
        return
    if t.interrupt == "cancel":
        t.status = "Canceled"
        return
    t.status = "Done"
    t.pct = 100.0
    t.speed = t.eta = ""


def _stopped(t):
    t.status = "Paused" if t.interrupt == "pause" else "Canceled"
    # The row was already removed (✕ pressed during "Stopping"): the user
    # means "throw this away", so finish the cleanup from the worker side.
    if t.status == "Canceled" and t.dropped:
        cleanup_partial(t)


def cleanup_partial(t):
    """Delete yt-dlp leftovers (.part/.ytdl/.temp) and the cached thumbnail
    of a canceled download. Only ever called when the user removes a canceled
    task; paused, failed and app-exit partials must stay for resume."""
    vid = t.thumb_path
    if not vid:
        return
    try:
        candidates = glob.glob(os.path.join(
            t.folder, "*" + glob.escape(f"[{vid}]") + "*"))
    except OSError:
        candidates = []
    marker = f"[{vid}].f"  # yt-dlp format fragments: title [id].f399.mp4
    for f in candidates:
        base = os.path.basename(f)
        i = base.find(marker)
        fragment = i >= 0 and base[i + len(marker):i + len(marker) + 1].isdigit()
        if fragment or base.lower().endswith((".part", ".ytdl", ".temp")):
            _drop(f)
    if t.thumb_dir and os.path.isdir(t.thumb_dir):
        for f in glob.glob(os.path.join(t.thumb_dir, glob.escape(vid) + ".*")):
            _drop(f)


def _stopped_cleanup(t):
    pass


# ----------------------------------------------------------------- convert job
def run_convert(t, cfg):
    o = t.cv_opts
    t.interrupt = None
    ffmpeg = cfg.get("ffmpeg")
    if not ffmpeg:
        t.status = "Failed"
        t.note = "ffmpeg not found on PATH"
        return
    src = t.source
    total = ffprobe_duration(cfg.get("ffprobe"), src)
    if total:
        t.duration_text = human_time(total)
    container = o["container"]
    same = o.get("same_folder", True)
    out_dir = os.path.dirname(src) if same else t.folder
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(out_dir, f"{base}.{container}")
    group = CONTAINER_GROUP.get(container, "video")
    cmd = [ffmpeg, "-y", "-nostdin", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", "-i", src]
    if group == "video":
        vcodec = VIDEO_CODECS.get(o.get("vcodec", "H.264"), "libx264")
        cmd += ["-c:v", vcodec]
        if vcodec == "libx264":
            cmd += ["-preset", o.get("preset", "medium"), "-crf",
                    str(o.get("crf", 20))]
        elif vcodec == "libx265":
            cmd += ["-preset", o.get("preset", "medium"), "-crf",
                    str(o.get("crf", 24))]
        acodec = AUDIO_DEFAULT.get(container, ("aac", ["-c:a", "aac"]))[1]
        cmd += [a.replace("{abr}", o.get("abr", "192k")) for a in acodec]
    else:
        aargs = AUDIO_CODECS.get(o.get("acodec", "AAC"), AUDIO_CODECS["AAC"])
        cmd += [a.replace("{abr}", o.get("abr", "192k")) for a in aargs]
        cmd += ["-vn"]
    extra = (o.get("extra") or "").split()
    if extra:
        cmd += extra
    cmd += [out]  # ffmpeg infers the muxer from the output extension
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        t.proc = proc
        t.status = "Processing"
        for line in proc.stdout:
            if t.interrupt == "cancel":
                proc.terminate()
                break
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    us = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                if total:
                    t.pct = min(99.0, us / (total * 1_000_000) * 100.0)
            if os.path.exists(out):
                t.total_bytes = None
                t.downloaded = os.path.getsize(out)
        proc.wait()
        if t.interrupt == "cancel":
            t.status = "Canceled"
            _drop(out)
        elif proc.returncode == 0 and os.path.exists(out):
            t.status = "Done"
            t.pct = 100.0
            t.final_path = out
            t.title = base
        else:
            err = (proc.stderr.read() or "").strip().splitlines()
            t.status = "Failed"
            t.note = (err[-1] if err else "ffmpeg failed")[:160]
            _drop(out)
    except Exception as e:
        t.status = "Failed"
        t.note = str(e)[:160]
        _drop(out)
    finally:
        t.proc = None


def _drop(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
