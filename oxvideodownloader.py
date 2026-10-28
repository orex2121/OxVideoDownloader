"""OxVideoDownloader entry point."""

import sys

import oxvd  # noqa: F401  (import runs the bundled Tcl/Tk bootstrap)


def main():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        from tkinter import messagebox, Tk
        r = Tk()
        r.withdraw()
        messagebox.showerror(
            "OxVideoDownloader",
            "yt-dlp is not installed.\nRun OxVideoDownloader.bat once to set "
            "it up, or execute: pip install -r requirements.txt")
        r.destroy()
        sys.exit(1)
    from oxvd.ui import App
    App().run()


if __name__ == "__main__":
    main()
