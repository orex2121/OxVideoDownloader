"""Color palettes. Each theme is a dict of the same named colors."""

THEMES = {
    "Light": dict(
        bg="#f4f4f4", page="#ffffff", fg="#333333", accent="#0a6cdc",
        head="#f7f7f7", headfg="#777777", bar="#ebebeb", sep="#dddddd",
        sub="#888888", thumb="#eeeeee", field="#ffffff",
        green="#1a9e1a", red="#d11111", alpha=1.0),
    "Dark": dict(
        bg="#1b1b1c", page="#252526", fg="#e6e6e6", accent="#3d9bff",
        head="#2d2d30", headfg="#a9a9a9", bar="#1b1b1c", sep="#3c3c3c",
        sub="#9a9a9a", thumb="#333333", field="#2d2d30",
        green="#4ec96a", red="#ff6b6b", alpha=1.0),
    "Darkula": dict(
        bg="#313335", page="#2b2b2b", fg="#bbbbbb", accent="#6897bb",
        head="#3c3f41", headfg="#969896", bar="#2b2b2b", sep="#4d4d4d",
        sub="#8a8a8a", thumb="#3c3f41", field="#232323",
        green="#6aa84f", red="#ff6d67", alpha=1.0),
    "Midnight Ocean": dict(
        bg="#0b1220", page="#111a2e", fg="#dbe7f5", accent="#4c8dff",
        head="#16223a", headfg="#8fa6c4", bar="#0b1220", sep="#23344a",
        sub="#7e93ad", thumb="#1a2740", field="#16223a",
        green="#2fd27d", red="#ff7a7a", alpha=1.0),
    "Synthwave": dict(
        bg="#1a1025", page="#241638", fg="#f0e6ff", accent="#ff2e97",
        head="#2c1c46", headfg="#c8a6e8", bar="#1a1025", sep="#46306b",
        sub="#b18cd9", thumb="#2c1c46", field="#2c1c46",
        green="#05d9e8", red="#ff4d6d", alpha=1.0),
    "Dracula": dict(
        bg="#282a36", page="#21222c", fg="#f8f8f2", accent="#bd93f9",
        head="#2d2e3b", headfg="#a8a4b8", bar="#282a36", sep="#44475a",
        sub="#9a95ab", thumb="#343746", field="#282a36",
        green="#50fa7b", red="#ff5555", alpha=1.0),
    "Solarized Dark": dict(
        bg="#002b36", page="#073642", fg="#93a1a1", accent="#268bd2",
        head="#0a4050", headfg="#839496", bar="#002b36", sep="#2b4a55",
        sub="#6c8284", thumb="#0a4050", field="#002b36",
        green="#859900", red="#dc322f", alpha=1.0),
    "Emerald Night": dict(
        bg="#0e1f18", page="#12291f", fg="#d8f3e3", accent="#2fbf71",
        head="#173327", headfg="#8fbfa4", bar="#0e1f18", sep="#274a38",
        sub="#7fae94", thumb="#1b3a2c", field="#173327",
        green="#3ddc84", red="#ff6b6b", alpha=1.0),
    # "obsidian graphite + burnt copper accent": premium dark (Linear-style)
    "Obsidian Copper": dict(
        bg="#0b0c0e", page="#15171c", fg="#f2f4f8", accent="#d97736",
        head="#08090b", headfg="#b4bac6", bar="#101216", sep="#242830",
        sub="#9098a6", thumb="#0e1014", field="#1d2026",
        green="#34c77b", red="#e55353", alpha=1.0),
    # "frosted glass": light bluish tints + real window transparency
    "Glass": dict(
        bg="#cfdcec", page="#e3ecf7", fg="#22405e", accent="#2f7fd1",
        head="#d9e4f0", headfg="#4a6480", bar="#c6d5e8", sep="#b3c6dc",
        sub="#5c7893", thumb="#d3e0ee", field="#f2f7fd",
        green="#1d8a4e", red="#c22a2a", alpha=0.94),
}


def shade(hexcol, factor):
    """Lighten (0..1) or darken (-1..0) a #rrggbb color."""
    try:
        h = hexcol.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return hexcol

    def adj(v):
        if factor >= 0:
            return int(v + (255 - v) * factor)
        return int(v * (1.0 + factor))

    return "#%02x%02x%02x" % (min(adj(r), 255), min(adj(g), 255),
                              min(adj(b), 255))
