"""Cut the dark rounded tile out of the Gemini capture and build the app
icon set: assets/app.png (256), app48/24/16.png and multi-size app.ico."""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "icon_gemini_new.png")
A = os.path.join(ROOT, "assets")

im = Image.open(SRC).convert("RGB")
w, h = im.size
# The tile is dark graphite (luma ~23).  The chat panel is mid-gray
# (luma ~56) and the capture border is a thin neutral-black ring hugging
# the image edge, so mask on "dark" but ignore the outer 14 px frame.
lum = im.convert("L")
mask = lum.point(lambda v: 255 if v < 40 else 0)
ImageDraw.Draw(mask).rectangle([0, 0, w - 1, 13], fill=0)
ImageDraw.Draw(mask).rectangle([0, h - 14, w - 1, h - 1], fill=0)
ImageDraw.Draw(mask).rectangle([0, 0, 13, h - 1], fill=0)
ImageDraw.Draw(mask).rectangle([w - 14, 0, w - 1, h - 1], fill=0)
x0, y0, x1, y1 = mask.getbbox()
print("tile bbox:", x0, y0, x1, y1)
side = min(x1 - x0, y1 - y0)
cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
tile256 = im.crop((cx - side // 2, cy - side // 2, cx - side // 2 + side,
                   cy - side // 2 + side)).resize((256, 256), Image.LANCZOS)


def icon_at(sz):
    """Tile scaled to sz with exact (no-AA) rounded-corner alpha."""
    img = tile256.resize((sz, sz), Image.LANCZOS).convert("RGBA")
    rad = max(1, int(round(sz * 0.185)))
    corners = Image.new("L", (sz, sz), 0)
    ImageDraw.Draw(corners).rounded_rectangle([0, 0, sz - 1, sz - 1], rad,
                                              fill=255)
    img.putalpha(corners)
    return img


rgba = icon_at(256)
rgba.save(os.path.join(A, "app_source.png"))
rgba.save(os.path.join(A, "app.png"))
for sz in (48, 24, 16):
    icon_at(sz).save(os.path.join(A, "app%d.png" % sz))
icons = [icon_at(s) for s in (16, 24, 32, 48, 64, 128, 256)]


def write_ico(path, imgs):
    """Classic ICO with 32bpp BMP (DIB) entries only — PNG-compressed ico
    entries (what PIL produces by default) are mishandled by the .NET
    Framework csc resource packer and by Explorer's icon extraction."""
    import struct

    def dib(img):
        w, h = img.size
        px = img.load()
        xor = b""
        for y in range(h - 1, -1, -1):          # bottom-up BGRA
            xor += b"".join(bytes((px[x, y][2], px[x, y][1], px[x, y][0],
                                   px[x, y][3])) for x in range(w))
        mstride = ((w + 31) // 32) * 4
        and_ = b""
        for y in range(h - 1, -1, -1):          # AND mask: 0 = opaque
            row = bytearray(mstride)
            for x in range(w):
                if px[x, y][3] <= 127:
                    row[x >> 3] |= 0x80 >> (x & 7)
            and_ += bytes(row)
        hdr = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0,
                          len(xor) + len(and_), 0, 0, 0, 0)
        return hdr + xor + and_

    blobs = [dib(i) for i in imgs]
    n = len(imgs)
    dirsz = 6 + 16 * n
    out = struct.pack("<HHH", 0, 1, n)
    off = dirsz
    for img, blob in zip(imgs, blobs):
        w, h = img.size
        out += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32,
                           len(blob), off)
        off += len(blob)
    open(path, "wb").write(out + b"".join(blobs))


write_ico(os.path.join(A, "app.ico"), icons)
print("icon set written")

# self-check like the smoke suite: transparent corners, full-bleed edges
for p in ("app16.png", "app48.png", "app.png"):
    im2 = Image.open(os.path.join(A, p)).convert("RGBA")
    ww, hh = im2.size
    corners_a = [im2.getpixel((0, 0))[3], im2.getpixel((ww - 1, 0))[3],
                 im2.getpixel((0, hh - 1))[3], im2.getpixel((ww - 1, hh - 1))[3]]
    b = im2.split()[-1].point(lambda v: 255 if v > 32 else 0).getbbox()
    print(p, "corners:", corners_a, "bbox:", b,
          "full-bleed:", b[0] == 0 and b[1] == 0 and b[2] >= ww - 1 and b[3] >= hh - 1)
