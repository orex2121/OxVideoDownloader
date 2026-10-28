"""Generate flat UI icons for OxVideoDownloader (run once: python make_icons.py)."""

import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
S = 4  # supersampling factor


def canvas(w, h):
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def save(img, name, w, h):
    img = img.resize((w, h), Image.LANCZOS)
    img.save(os.path.join(OUT, name))
    print("assets/" + name)


def rr(d, box, rad, fill, outline=None, width=1):
    d.rounded_rectangle([c * S for c in box], rad * S, fill=fill,
                        outline=outline, width=width * S)


def film(name):
    """Blue mosaic grid icon (video)."""
    img, d = canvas(16, 16)
    rr(d, (1, 1, 15, 15), 2, (61, 111, 184, 255))
    cells = [(3, 3), (9, 3), (3, 9), (9, 9)]
    for x, y in cells:
        rr(d, (x, y, x + 4, y + 4), 1, (190, 214, 240, 255))
    save(img, name, 16, 16)


def folder(name, color):
    """Classic folder shape."""
    img, d = canvas(16, 14)
    rr(d, (0, 2, 7, 5), 1, color)            # tab
    rr(d, (0, 3, 15, 13), 2, color)          # body
    rr(d, (1, 5, 14, 12), 1,
       tuple(max(0, c - 35) if i < 3 else 255
             for i, c in enumerate(color)))   # darker lower half
    save(img, name, 16, 14)


def chevron(name):
    """Gray double chevron pointing down."""
    img, d = canvas(16, 16)
    lw = 2 * S
    for y in (5, 9):
        d.line([(4 * S, y * S), (8 * S, (y + 3) * S), (12 * S, y * S)],
               fill=(120, 120, 120, 255), width=lw, joint="curve")
    save(img, name, 16, 16)


def plus(name, color):
    img, d = canvas(16, 16)
    rr(d, (6.5, 1.5, 9.5, 14.5), 1.5, color)
    rr(d, (1.5, 6.5, 14.5, 9.5), 1.5, color)
    save(img, name, 16, 16)


def play(name):
    img, d = canvas(16, 16)
    d.polygon([(4 * S, 2.5 * S), (14 * S, 8 * S), (4 * S, 13.5 * S)],
              fill=(42, 114, 192, 255))
    save(img, name, 16, 16)


def pause(name, color=(110, 110, 110, 255)):
    img, d = canvas(16, 16)
    rr(d, (4, 3, 6.6, 13), 1.2, color)
    rr(d, (9.4, 3, 12, 13), 1.2, color)
    save(img, name, 16, 16)


def minus(name):
    img, d = canvas(16, 16)
    rr(d, (2, 6.5, 14, 9.5), 1.5, (110, 110, 110, 255))
    save(img, name, 16, 16)


def status(name, draw_fn, size=18):
    img, d = canvas(size, size)
    draw_fn(d, size)
    save(img, name, size, size)


# NOTE: d.line/rect/polygon/ellipse take raw canvas pixels, so every glyph
# coordinate must be scaled by S (rr() does that scaling itself).
def st_done(d, s):
    rr(d, (1, 1, s - 1, s - 1), 4, (26, 158, 26, 255))
    d.line([(s * 0.28 * S, s * 0.52 * S), (s * 0.44 * S, s * 0.68 * S),
            (s * 0.74 * S, s * 0.32 * S)],
           fill=(255, 255, 255, 255), width=2 * S, joint="curve")


def st_fail(d, s):
    rr(d, (1, 1, s - 1, s - 1), 4, (211, 47, 47, 255))
    d.line([(s * 0.32 * S, s * 0.32 * S), (s * 0.68 * S, s * 0.68 * S)],
           fill=(255, 255, 255, 255), width=2 * S)
    d.line([(s * 0.68 * S, s * 0.32 * S), (s * 0.32 * S, s * 0.68 * S)],
           fill=(255, 255, 255, 255), width=2 * S)


def st_run(d, s):
    rr(d, (1, 1, s - 1, s - 1), 4, (10, 108, 220, 255))
    d.polygon([(s * 0.36 * S, s * 0.28 * S), (s * 0.72 * S, s * 0.5 * S),
               (s * 0.36 * S, s * 0.72 * S)], fill=(255, 255, 255, 255))


def st_pause(d, s):
    rr(d, (1, 1, s - 1, s - 1), 4, (246, 196, 69, 255))
    d.rectangle([(s * 0.33 * S, s * 0.30 * S), (s * 0.44 * S, s * 0.70 * S)],
                fill=(255, 255, 255, 255))
    d.rectangle([(s * 0.56 * S, s * 0.30 * S), (s * 0.67 * S, s * 0.70 * S)],
                fill=(255, 255, 255, 255))


def st_wait(d, s):
    rr(d, (1, 1, s - 1, s - 1), 4, (160, 160, 160, 255))
    d.ellipse([(s * 0.34 * S, s * 0.34 * S), (s * 0.66 * S, s * 0.66 * S)],
              fill=(255, 255, 255, 255))


def app_icon(size=32):
    """Fallback app icon (drawn). NOTE: the shipped app icon is currently
    the Obsidian Copper bull cut from assets/app_source.png; re-running
    this function replaces it with this simpler vector design.
    """
    W = 1024
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d0 = 1024 // 1024  # scale kept at 1: the canvas is already large

    def vgrad(top, bot):
        g = Image.new("RGB", (1, W))
        for y in range(W):
            t = y / (W - 1)
            g.putpixel((0, y),
                       tuple(round(a + (b - a) * t) for a, b in zip(top, bot)))
        return g.resize((W, W))

    # tile
    grad = vgrad((36, 40, 47), (10, 11, 14))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([90, 90, 934, 934], 170, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([97, 97, 927, 927], 163,
                        outline=(217, 119, 54, 150), width=8 * d0)
    # copper arrow + tray
    cop = vgrad((244, 182, 110), (190, 92, 38))
    arrow = Image.new("L", (W, W), 0)
    ImageDraw.Draw(arrow).polygon(
        [(470, 268), (554, 268), (554, 512), (640, 512),
         (512, 700), (384, 512), (470, 512)], fill=255)
    img.paste(cop, (0, 0), arrow)
    tray = Image.new("L", (W, W), 0)
    dt = ImageDraw.Draw(tray)
    Wl = 56
    dt.line([(330, 552), (330, 740), (694, 740), (694, 552)], fill=255,
            width=Wl)
    for x, y in [(330, 552), (694, 552)]:
        dt.ellipse([x - Wl // 2, y - Wl // 2, x + Wl // 2, y + Wl // 2],
                   fill=255)
    img.paste(cop, (0, 0), tray)

    img = img.resize((size, size), Image.LANCZOS)
    name = "app.png" if size == 256 else f"app{size}.png"
    img.save(os.path.join(OUT, name))
    print("assets/" + name)


def main():
    os.makedirs(OUT, exist_ok=True)
    BLUE = (61, 111, 184, 255)
    YELLOW = (246, 196, 69, 255)
    film("film.png")
    folder("folder.png", YELLOW)
    folder("folder_blue.png", BLUE)
    chevron("chevron.png")
    plus("plus_green.png", (26, 158, 26, 255))
    plus("plus_blue.png", (42, 114, 192, 255))
    play("play.png")
    pause("pause.png")
    minus("minus.png")
    status("st_done.png", st_done)
    status("st_fail.png", st_fail)
    status("st_run.png", st_run)
    status("st_pause.png", st_pause)
    status("st_wait.png", st_wait)
    app_icon(256)
    app_icon(48)
    app_icon(24)
    app_icon(16)


if __name__ == "__main__":
    main()
