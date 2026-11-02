"""Build the GitHub profile: images and README.md.

What it does:
  1. Reads folio/profile.json (all the words, links and code excerpts).
  2. Draws the header, link buttons, section labels and project rows as PNGs,
     once for light mode and once for dark mode, into assets/folio/.
     Most have a wide version (computers) and a narrow one (phones).
  3. Writes the editor banner as animated SVGs: it types short excerpts from
     my repos, like the editor at the top of falakpatel.com. Pure SVG
     animation (no JavaScript), so GitHub shows it.
  4. Writes README.md, which picks the right image for the screen and theme.
  5. Removes old images in assets/folio that the build no longer makes.

Run it from the repo folder after editing profile.json, a font or the photo:
    pip install pillow
    python3 folio/build.py

The look follows falakpatel.com: the "night" theme in dark mode (near-black,
soft blue #8ab4f8) and the "paper" theme in light mode (warm off-white, ink
blue), Libre Baskerville for words, JetBrains Mono for the code bits, and my
logo: the Gujarati letter ફ (pha), my initial, turned on its side
(folio/logo-bold.svg).

Fonts live in folio/fonts with their SIL Open Font Licence files.
JetBrainsMono-code-400.woff2 is a tiny cut (plain Latin letters only) that
gets embedded in the editor SVG, because GitHub's image proxy blocks outside fonts.
"""

import base64
import json
import random
import re
from functools import lru_cache
from html import escape as _escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FOLIO = ROOT / "folio"
FONTS = FOLIO / "fonts"
LOGO = FOLIO / "logo-bold.svg"  # the heavier cut of the logo, made for small sizes
OUT = ROOT / "assets" / "folio"
GITHUB = "https://github.com/falakpat3l/"

# Everything is drawn at 4x and saved at 2x: lines and curves come out smooth,
# and text stays sharp on high-resolution screens.
S = 4
SAVE = 2

PAGE = 744    # width of the wide images (computers)
NARROW = 340  # width of the narrow images (phones)
WIDE_FROM = 1012  # GitHub's breakpoint: from this screen width up, the wide images show

# The two themes of falakpatel.com: "paper" for light mode, "night" for dark mode.
THEMES = {
    "light": {"name": "paper", "bg": "#f4efe4", "surface": "#ebe4d4", "code": "#efe9dc",
              "line": "#ddd3c0", "line2": "#cbbfa8", "fg": "#1d1a15", "muted": "#5d5548",
              "dim": "#a0957f", "accent": "#1f4a8a", "on_accent": "#ffffff", "warm": "#9c3b1a",
              "k": "#1f4a8a", "s": "#8e3816", "c": "#8d8371", "n": "#8e3816", "t": "#2c5f6b", "f": "#1d1a15"},
    "dark": {"name": "night", "bg": "#050505", "surface": "#0d0d0d", "code": "#090909",
             "line": "#1f1f1f", "line2": "#2a2a2a", "fg": "#ededed", "muted": "#9e9e9e",
             "dim": "#5c5c5c", "accent": "#8ab4f8", "on_accent": "#050505", "warm": "#e3b56f",
             "k": "#8ab4f8", "s": "#e3b56f", "c": "#6f6f6f", "n": "#e3b56f", "t": "#b8cdf2", "f": "#ededed"},
}


def mix(a, b, amount):
    """Blend colour a towards colour b (amount 0 to 1). Colours are '#rrggbb'."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(ca, cb))


# ---------------------------------------------------------------- fonts and text

@lru_cache(maxsize=None)
def font(style, size, weight=400):
    """style: "serif", "italic" or "mono". size is in screen pixels."""
    name = {"serif": "LibreBaskerville.ttf", "italic": "LibreBaskerville-Italic.ttf",
            "mono": "JetBrainsMono.ttf"}[style]
    f = ImageFont.truetype(str(FONTS / name), round(size * S))
    f.set_variation_by_axes([weight])  # both are variable fonts with one axis: weight
    return f


def escape(text):
    """Make text safe inside HTML or XML (keeps apostrophes readable)."""
    return _escape(text, quote=False).replace('"', "&quot;")


def wrap(draw, text, fnt, width):
    """Split text into lines that fit the given width (in drawing pixels)."""
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    return lines + [line] if line else lines


def canvas(w, h):
    """A transparent image of w x h screen pixels."""
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def save(img, name, written):
    """Save at 2x and return the size in screen pixels."""
    OUT.mkdir(parents=True, exist_ok=True)
    w, h = img.width // S, img.height // S
    small = img.resize((w * SAVE, h * SAVE), Image.LANCZOS)
    if not name.startswith("header"):
        # Flat colours and text: 256 colours look the same and the file is about a third the size.
        # (The header keeps full colour for the photo.)
        small = small.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    small.save(OUT / name, optimize=True)
    written.add(name)
    return w, h


# ---------------------------------------------------------------- the logo

@lru_cache(maxsize=None)
def logo_path():
    """The path data and box of folio/logo-bold.svg."""
    text = LOGO.read_text()
    d = re.search(r' d="([^"]+)"', text).group(1)
    box = [float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).split()]
    return d, box


@lru_cache(maxsize=None)
def logo_shapes():
    """The logo's outlines as lists of (x, y) points.

    The path only uses M, L, Q and Z, and is flipped upside down by scale(1,-1).
    """
    d = logo_path()[0]
    tokens = re.findall(r"[MLQZ]|-?[\d.]+(?:e-?\d+)?", d)
    shapes, shape, cmd, pos, i = [], [], None, (0.0, 0.0), 0
    while i < len(tokens):
        if tokens[i] in "MLQZ":
            cmd = tokens[i]
            i += 1
            if cmd == "Z":
                shapes.append(shape)
                shape = []
            continue
        nums = [float(v) for v in tokens[i:i + (4 if cmd == "Q" else 2)]]
        i += len(nums)
        if cmd == "Q":  # a curve: sample it as short straight steps
            (cx, cy), (ex, ey) = nums[:2], nums[2:]
            for k in range(1, 17):
                u = k / 16
                shape.append(((1 - u) ** 2 * pos[0] + 2 * (1 - u) * u * cx + u * u * ex,
                              (1 - u) ** 2 * pos[1] + 2 * (1 - u) * u * cy + u * u * ey))
            pos = (ex, ey)
        else:  # M, or L (numbers after M also count as L)
            pos = (nums[0], nums[1])
            shape.append(pos)
            cmd = "L" if cmd == "M" else cmd
    if shape:
        shapes.append(shape)
    return [[(x, -y) for x, y in sh] for sh in shapes]


def logo_width(height):
    shapes = logo_shapes()
    xs = [x for sh in shapes for x, _ in sh]
    ys = [y for sh in shapes for _, y in sh]
    return height * (max(xs) - min(xs)) / (max(ys) - min(ys))


def logo(img, cx, cy, height, colour):
    """Draw the logo centred on (cx, cy), `height` pixels tall, with smooth edges."""
    shapes = logo_shapes()
    xs = [x for sh in shapes for x, _ in sh]
    ys = [y for sh in shapes for _, y in sh]
    k = height / (max(ys) - min(ys))
    width = (max(xs) - min(xs)) * k
    left, top = int(cx - width / 2) - 1, int(cy - height / 2) - 1
    W, H = int(width) + 4, int(height) + 4
    ss = 4  # draw 4x larger again, then shrink, for clean curves
    x_off, y_off = (cx - width / 2 - left) * ss, (cy - height / 2 - top) * ss
    edges = []
    for sh in shapes:
        pts = [(x_off + (x - min(xs)) * k * ss, y_off + (y - min(ys)) * k * ss) for x, y in sh]
        for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
            if ya != yb:
                edges.append((xa, ya, xb, yb, 1 if yb > ya else -1))
    # Fill row by row with the "nonzero" rule, like a browser does (the letter's loop overlaps itself).
    mask = bytearray(W * ss * H * ss)
    for row in range(H * ss):
        y = row + 0.5
        hits = sorted((xa + (y - ya) * (xb - xa) / (yb - ya), s) for xa, ya, xb, yb, s in edges
                      if ya <= y < yb or yb <= y < ya)
        inside = 0
        for (x, s), nxt in zip(hits, hits[1:]):
            inside += s
            if inside:
                a, b = max(0, round(x)), min(W * ss, round(nxt[0]))
                mask[row * W * ss + a:row * W * ss + b] = b"\xff" * max(0, b - a)
    alpha = Image.frombytes("L", (W * ss, H * ss), bytes(mask)).resize((W, H), Image.BOX)
    layer = Image.new("RGBA", (W, H), colour)
    layer.putalpha(alpha)
    img.alpha_composite(layer, (left, top))


# ---------------------------------------------------------------- small line icons

def icon(d, kind, x, y, size, colour):
    """Line icons on a 24-unit grid, like the ones on falakpatel.com. (x, y) is the top left."""
    k = size / 24
    w = max(1, round(1.6 * k))

    def P(px, py):
        return (x + px * k, y + py * k)

    def line(*pts):
        d.line([P(*p) for p in pts], fill=colour, width=w, joint="curve")

    def arc(cx, cy, rx, ry, a0, a1, steps=24):
        import math
        return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
                 cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]

    if kind == "web":
        d.ellipse((*P(2.5, 2.5), *P(21.5, 21.5)), outline=colour, width=w)
        line(*arc(12, 12, 4.2, 9.5, -90, 90))
        line(*arc(12, 12, 4.2, 9.5, 90, 270))
        line((2.5, 12), (21.5, 12))
    elif kind == "linkedin":
        d.rounded_rectangle((*P(2.5, 2.5), *P(21.5, 21.5)), radius=3 * k, outline=colour, width=w)
        line((7.5, 10.5), (7.5, 16.5))
        d.ellipse((*P(6.6, 6.5), *P(8.4, 8.3)), fill=colour)
        line((11.5, 16.5), (11.5, 10.5))
        line(*arc(14, 13.2, 2.5, 2.7, 180, 360, 12), (16.5, 16.5))
    elif kind == "scholar":
        line((12, 4.2), (2.2, 9), (12, 13.8), (21.8, 9), (12, 4.2))
        line((6.4, 11.4), *arc(12, 16, 5.6, 3, 180, 0), (17.6, 11.4))
    elif kind == "x":
        line((5, 4.5), (19, 19.5))
        line((19, 4.5), (5, 19.5))
    elif kind == "linktree":
        line((12, 21.5), (12, 2.5))
        line((6, 8.5), (12, 13), (18, 8.5))
        line((5, 13.5), (19, 13.5))
    elif kind == "heart":
        import math
        pts = []
        for i in range(64):
            t = 2 * math.pi * i / 64
            pts.append(P(12 + 0.62 * 16 * math.sin(t) ** 3 / 1.6,
                         11 - 0.62 * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) / 1.6))
        d.polygon(pts, fill=colour)


# ---------------------------------------------------------------- header

def round_photo(diameter):
    """The photo cut into a circle, diameter in drawing pixels."""
    src = Image.open(FOLIO / PROFILE["photo"]).convert("RGB")
    side = min(src.size)
    src = src.crop(((src.width - side) // 2, (src.height - side) // 2,
                    (src.width + side) // 2, (src.height + side) // 2))
    photo = src.resize((diameter, diameter), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (diameter * 4, diameter * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter * 4 - 1, diameter * 4 - 1), fill=255)
    photo.putalpha(mask.resize((diameter, diameter), Image.LANCZOS))
    return photo


def top_bar(img, d, w, t, h):
    """The site's top bar: logo and address on the left, theme switch on the right."""
    mark_h = 15 * S
    mx = 20 * S
    logo(img, mx + logo_width(mark_h) / 2, h * S // 2, mark_h, t["accent"])
    d.text((mx + logo_width(mark_h) + 11 * S, h * S // 2), PROFILE["site"],
           font=font("mono", 12.5, 500), fill=t["fg"], anchor="lm")
    # The theme switch: a dot and the theme's name in a small outlined box.
    f = font("mono", 11.5)
    label = t["name"]
    bw = int(d.textlength(label, font=f)) + 34 * S
    bx1, by0, by1 = w * S - 16 * S, h * S // 2 - 13 * S, h * S // 2 + 13 * S
    d.rounded_rectangle((bx1 - bw, by0, bx1, by1), radius=6 * S, outline=t["line2"], width=S)
    cx, cy, r = bx1 - bw + 13 * S, h * S // 2, 4 * S
    d.ellipse((cx - r - 2 * S, cy - r - 2 * S, cx + r + 2 * S, cy + r + 2 * S), fill=mix(t["accent"], t["bg"], 0.72))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=t["accent"])
    d.text((cx + 11 * S, cy), label, font=f, fill=t["muted"], anchor="lm")
    d.line((0, h * S, w * S, h * S), fill=t["line"], width=S)


def draw_header(theme, narrow):
    t = THEMES[theme]
    p = PROFILE
    w = NARROW if narrow else PAGE
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    first, middle, last = p["name"].split(" ", 2)
    bar = 48 if not narrow else 46

    if not narrow:
        photo_d, px, tx = 128, 40, 40 + 128 + 42
        tw = (w - tx - 36) * S
        name_f, role_f, bio_f = font("serif", 37), font("serif", 17.5), font("serif", 14.5)
        ital_f = font("italic", 37)
        lab_f, val_f = font("mono", 11), font("serif", 13.5)
        bio_lines = wrap(probe, p["bio"], bio_f, tw)
        y_name = bar + 56
        y_role = y_name + 36
        y_bio = y_role + 30
        y_creds = y_bio + len(bio_lines) * 23 + 14
        h = y_creds + len(p["creds"]) * 22 + 30
    else:
        photo_d = 92
        tw = (w - 48) * S
        name_f, ital_f = font("serif", 27), font("italic", 27)
        role_f, bio_f = font("serif", 15.5), font("serif", 13.5)
        lab_f, val_f = font("mono", 10.5), font("serif", 13)
        bio_lines = wrap(probe, p["bio"], bio_f, tw)
        y_photo = bar + 30
        y_name = y_photo + photo_d + 46
        y_role = y_name + 30
        y_bio = y_role + 28
        y_creds = y_bio + len(bio_lines) * 21 + 16
        lab_w = max(probe.textlength(k, font=lab_f) for k, _ in p["creds"]) + 14 * S
        cred_rows = [wrap(probe, v, val_f, (w - 48) * S - lab_w) for _, v in p["creds"]]
        h = y_creds + sum(len(r) for r in cred_rows) * 20 + 4 * len(cred_rows) + 24

    img, d = canvas(w, h)
    d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=12 * S, fill=t["bg"], outline=t["line2"], width=S)
    top_bar(img, d, w, t, bar)
    if not narrow:  # the logo again, large and faint, in the empty corner
        mh = 58 * S
        logo(img, w * S - 36 * S - logo_width(mh) / 2, h * S - 30 * S - mh / 2, mh, mix(t["bg"], t["accent"], 0.11))

    # The round photo, with a thin accent ring like on the website.
    photo = round_photo(photo_d * S)
    if not narrow:
        y_photo = bar + (h - bar - photo_d) // 2
        cx = px + photo_d // 2
    else:
        cx = w // 2
    cy = y_photo + photo_d // 2
    ring = (photo_d / 2 + 5) * S
    d.ellipse((cx * S - ring, cy * S - ring, cx * S + ring, cy * S + ring), outline=t["accent"], width=round(1.25 * S))
    img.alpha_composite(photo, (cx * S - photo_d * S // 2, cy * S - photo_d * S // 2))

    # Name: first and last name upright, the middle name in italic and quieter, as on the site.
    parts = [(first + " ", name_f, t["fg"]), (middle, ital_f, t["muted"]), (" " + last, name_f, t["fg"])]
    total = sum(d.textlength(s, font=f) for s, f, _ in parts)
    if total > (w - (tx if not narrow else 24) - 24) * S:
        raise SystemExit("The name is too wide for the header. Make it shorter in profile.json.")
    x = tx * S if not narrow else w * S / 2 - total / 2
    for s, f, c in parts:
        d.text((x, y_name * S), s, font=f, fill=c, anchor="ls")
        x += d.textlength(s, font=f)

    if not narrow:
        d.text((tx * S, y_role * S), p["role"], font=role_f, fill=t["fg"], anchor="ls")
        for i, line in enumerate(bio_lines):
            d.text((tx * S, (y_bio + i * 23) * S), line, font=bio_f, fill=t["muted"], anchor="ls")
        for i, (k, v) in enumerate(p["creds"]):
            y = (y_creds + i * 22) * S
            d.text((tx * S, y), k, font=lab_f, fill=t["dim"], anchor="ls")
            d.text((tx * S + 78 * S, y), v, font=val_f, fill=t["muted"], anchor="ls")
    else:
        d.text((w * S / 2, y_role * S), p["role"], font=role_f, fill=t["fg"], anchor="ms")
        for i, line in enumerate(bio_lines):
            d.text((w * S / 2, (y_bio + i * 21) * S), line, font=bio_f, fill=t["muted"], anchor="ms")
        # The facts as a small table, centred as a block.
        block = lab_w + max(d.textlength(l, font=val_f) for r in cred_rows for l in r)
        x0 = w * S / 2 - block / 2
        y = y_creds
        d.line((24 * S, (y - 22) * S, w * S - 24 * S, (y - 22) * S), fill=t["line"], width=S)
        for (k, _), rows in zip(p["creds"], cred_rows):
            d.text((x0, y * S), k, font=lab_f, fill=t["dim"], anchor="ls")
            for line in rows:
                d.text((x0 + lab_w, y * S), line, font=val_f, fill=t["muted"], anchor="ls")
                y += 20
            y += 4
    return img


# ---------------------------------------------------------------- buttons, labels, rows

def draw_pill(label, kind, theme, colour=None):
    """A rounded outlined button with a line icon and a monospace label, like the site's links."""
    t = THEMES[theme]
    f = font("mono", 12.5)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    h, ic = 34, 15
    w = int(12 + ic + 8 + probe.textlength(label, font=f) / S + 15) + 2
    img, d = canvas(w, h)
    d.rounded_rectangle((S, S, (w - 1) * S, (h - 1) * S), radius=(h // 2 - 1) * S, outline=t["line2"], width=S)
    icon(d, kind, 12 * S, (h - ic) * S / 2, ic * S, colour or t["fg"])
    d.text(((12 + ic + 8) * S, h * S / 2), label, font=f, fill=t["fg"], anchor="lm")
    return img


def draw_label(number, text, count, theme, w):
    """Section heading like the site's: a small number in the accent colour, then the name."""
    t = THEMES[theme]
    h = 46
    img, d = canvas(w, h)
    nf, tf, cf = font("mono", 11.5), font("serif", 19), font("mono", 11)
    y = 30 * S
    x = 6 * S
    d.text((x, y), number, font=nf, fill=t["accent"], anchor="ls")
    x += d.textlength(number, font=nf) + 12 * S
    d.text((x, y), text, font=tf, fill=t["fg"], anchor="ls")
    x += d.textlength(text, font=tf) + 16 * S
    cw = d.textlength(count, font=cf)
    end = w * S - 6 * S - cw - 14 * S
    if end > x:
        d.line((x, y - 5 * S, end, y - 5 * S), fill=t["line2"], width=S)
    d.text((w * S - 6 * S, y), count, font=cf, fill=t["dim"], anchor="rs")
    return img


def state_colour(t, state):
    return {"active": t["accent"], "proto": t["warm"], "done": t["dim"]}[state]


def draw_row(p, theme, w, narrow):
    """One project as a row of the site's project list: name, line, version tag and status."""
    t = THEMES[theme]
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    name_f = font("mono", 13.5 if narrow else 14, 500)
    text_f = font("serif", 13.5 if narrow else 14.5)
    tag_f, st_f = font("mono", 11), font("mono", 10.5 if narrow else 11)
    pad = 16 if narrow else 20
    nx = pad + 14
    tag_w = probe.textlength(p["tag"], font=tag_f) + 16 * S
    if narrow:
        lines = wrap(probe, p["text"], text_f, (w - nx - pad) * S)
        h = 18 + 18 + len(lines) * 20 + 22 + 14
    else:
        lines = wrap(probe, p["text"], text_f, (w - nx - pad) * S)
        h = 18 + 22 + len(lines) * 21 + 16
    if probe.textlength(p["title"], font=name_f) + tag_w + 20 * S > (w - nx - pad) * S:
        raise SystemExit(f"Project '{p['id']}': the name is too long. Shorten it in profile.json.")
    img, d = canvas(w, h)
    m = 3  # a little air above and below, so stacked rows sit evenly apart
    d.rounded_rectangle((S, m * S, (w - 1) * S, (h - m) * S), radius=10 * S, fill=t["code"], outline=t["line2"], width=S)
    col = state_colour(t, p["state"])
    y_name = (m + 25) * S
    # A small dot shows the state: blue for active, amber for a prototype, grey for finished work.
    r = 3.5 * S
    cx, cy = (pad + 3) * S, y_name - 5 * S
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    d.text((nx * S, y_name), p["title"], font=name_f, fill=t["fg"], anchor="ls")
    # Version tag: an outlined chip on the right.
    tx1 = (w - pad) * S
    tag_col = t["accent"] if p["state"] == "active" else t["warm"] if p["state"] == "proto" else t["muted"]
    d.rounded_rectangle((tx1 - tag_w, y_name - 15 * S, tx1, y_name + 5 * S), radius=5 * S,
                        outline=mix(tag_col, t["code"], 0.55), width=S, fill=mix(tag_col, t["code"], 0.92))
    d.text((tx1 - tag_w / 2, y_name - 5 * S), p["tag"], font=tag_f, fill=tag_col, anchor="mm")
    if narrow:
        y = y_name + 22 * S
        for line in lines:
            d.text((nx * S, y), line, font=text_f, fill=t["muted"], anchor="ls")
            y += 20 * S
        d.text((nx * S, y + 1 * S), p["status"], font=st_f, fill=mix(t["dim"], t["muted"], 0.5), anchor="ls")
    else:
        y = y_name + 23 * S
        for line in lines:
            d.text((nx * S, y), line, font=text_f, fill=t["muted"], anchor="ls")
            y += 21 * S
        # The status sits on the name's line, just left of the tag.
        name_end = nx * S + d.textlength(p["title"], font=name_f)
        st_x = tx1 - tag_w - 12 * S
        if st_x - d.textlength(p["status"], font=st_f) < name_end + 24 * S:
            raise SystemExit(f"Project '{p['id']}': the status is too long. Shorten it in profile.json.")
        d.text((st_x, y_name), p["status"], font=st_f, fill=mix(t["dim"], t["muted"], 0.5), anchor="rs")
    return img


def draw_divider(theme):
    """The logo between two short lines, like the footer of the site."""
    t = THEMES[theme]
    w, h = 220, 34
    img, d = canvas(w, h)
    cx, cy = w * S // 2, h * S // 2
    half = logo_width(15 * S) / 2
    d.line((20 * S, cy, cx - half - 14 * S, cy), fill=t["line2"], width=S)
    d.line((cx + half + 14 * S, cy, w * S - 20 * S, cy), fill=t["line2"], width=S)
    logo(img, cx, cy, 15 * S, t["dim"])
    return img


# ---------------------------------------------------------------- the editor (animated SVG)

KEYWORDS = {
    "kotlin": set("object fun val var return if else when in is null true false class private const import package".split()),
    "javascript": set("function var let const return if else while for new null true false typeof this".split()),
}


def tokenize(lang, lines):
    """A small highlighter, the same as the site's: comments, strings, regexes, numbers,
    keywords, types and calls. Returns, per line, a list of [class, text]."""
    kw = KEYWORDS[lang]
    out, in_block = [], False
    for line in lines:
        toks, i, prev = [], 0, ""

        def push(cls, text):
            nonlocal prev
            toks.append([cls, text])
            if text.strip():
                prev = text.strip()[-1]

        while i < len(line):
            rest = line[i:]
            if in_block:
                end = rest.find("*/")
                if end < 0:
                    push("c", rest)
                    break
                push("c", rest[:end + 2])
                i += end + 2
                in_block = False
                continue
            if rest.startswith("//"):
                push("c", rest)
                break
            if rest.startswith("/*"):
                end = rest.find("*/", 2)
                if end < 0:
                    push("c", rest)
                    in_block = True
                    break
                push("c", rest[:end + 2])
                i += end + 2
                continue
            m = re.match(r'"(?:[^"\\]|\\.)*"?', rest) or re.match(r"'(?:[^'\\]|\\.)*'?", rest)
            if m:
                push("s", m.group(0))
                i += len(m.group(0))
                continue
            if lang == "javascript" and rest[0] == "/" and prev in "(,=:[!&|?{};":
                m = re.match(r"/(?:[^/\\]|\\.)+/[gimsuy]*", rest)
                if m:
                    push("s", m.group(0))
                    i += len(m.group(0))
                    continue
            m = re.match(r"\d[\d_]*(?:\.\d+)?", rest)
            if m:
                push("n", m.group(0))
                i += len(m.group(0))
                continue
            m = re.match(r"[A-Za-z_$][\w$]*", rest)
            if m:
                word = m.group(0)
                after = line[i + len(word):]
                cls = "k" if word in kw else "t" if word[0].isupper() else "f" if after.lstrip().startswith("(") else ""
                push(cls, word)
                i += len(word)
                continue
            push("", rest[0])
            i += 1
        out.append(toks)
    return out


def layout(lang, code, cols):
    """Split each line into screen rows of at most `cols` characters (soft wrap, like the site).

    Returns rows as dicts: line number (only on a line's first row), indent and chars [(ch, class)].
    """
    rows = []
    for n, toks in enumerate(tokenize(lang, code), 1):
        chars = [(ch, cls) for cls, text in toks for ch in text]
        indent = len(chars) - len("".join(c for c, _ in chars).lstrip(" ")) if chars else 0
        start, first = 0, True
        while True:
            end = start + cols
            if end >= len(chars):
                rows.append({"no": n if first else None, "indent": indent if first else 0, "chars": chars[start:]})
                break
            cut = max((k for k in range(start + cols // 3, end) if chars[k][0] == " "), default=None)
            end = cut + 1 if cut is not None else end
            rows.append({"no": n if first else None, "indent": indent if first else 0, "chars": chars[start:end]})
            start, first = end, False
    return rows


def fmt(v):
    """A short number for SVG: at most 3 decimals, no trailing zeros."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def at(sec):
    """A begin time inside the loop."""
    return "L.begin" if sec <= 0 else f"L.begin+{fmt(sec)}s"


def stepper(attr, points):
    """Jump an attribute through values at given times: points = [(time, value), ...]."""
    t0 = points[0][0]
    dur = points[-1][0] - t0 + 0.2
    keys = ";".join(fmt((t - t0) / dur) for t, _ in points)
    vals = ";".join(fmt(v) if isinstance(v, float) or isinstance(v, int) else v for _, v in points)
    return (f'<animate attributeName="{attr}" begin="{at(t0)}" dur="{fmt(dur)}s" calcMode="discrete" '
            f'keyTimes="{keys}" values="{vals}" fill="freeze"/>')


def show_between(start, end=None):
    """Make an element visible from start to end (times inside the loop)."""
    s = f'<set attributeName="visibility" to="visible" begin="{at(start)}"/>'
    if end is not None:
        s += f'<set attributeName="visibility" to="hidden" begin="{at(end)}"/>'
    return s


def editor_svg(theme, narrow):
    t = THEMES[theme]
    files = PROFILE["editor"]
    W = NARROW if narrow else PAGE
    fs = 10 if narrow else 12.5        # font size
    cw = fs * 0.6                      # JetBrains Mono: every character is 0.6 em wide
    rh = round(fs * 1.75 * 2) / 2      # row height, as on the site (to the nearest half pixel)
    gut = 30 if narrow else 44         # line number column
    x0 = gut
    cols = int((W - gut - (10 if narrow else 16)) // cw)
    top_h, stat_h, cmd_h = 34, 26, 28
    code_top = top_h + 10
    laid = [layout(f["lang"], f["code"], cols) for f in files]
    nrows = max(len(r) for r in laid) + 1   # one row of ~ under the longest file
    code_bot = code_top + nrows * rh + 6
    H = round(code_bot + stat_h + cmd_h)
    base = lambda top: top + rh / 2 + fs * 0.36  # text baseline inside a row
    cur_h = round(fs * 1.3, 2)
    # Typing is counted in characters: inside this transform, x = 1 is one character to the right
    # of the code's left edge. That keeps the long lists of animation steps short.
    chars_x = f"translate({x0} 0) scale({fmt(cw)} 1)"

    # The timeline, in seconds from the start of each loop. Typing speed varies a little per
    # row (seeded, so every build gives the same file); comments go faster, like the site.
    rnd = random.Random(7)
    plan, clock = [], 0.0
    for fi, (f, rows) in enumerate(zip(files, laid)):
        fp = {"start": clock, "rows": []}
        clock += 0.5
        for j, row in enumerate(rows):
            if row["no"] is not None and j > 0:
                clock += 0.12 + rnd.random() * 0.12
                if rnd.random() < 0.15:
                    clock += 0.3  # a short think
            typed = len(row["chars"]) - row["indent"]
            comment = sum(1 for _, c in row["chars"] if c == "c") > typed / 2
            per = (0.014 if comment else 0.027) * (0.85 + rnd.random() * 0.3)
            fp["rows"].append({"start": clock, "per": per})
            clock += max(1, typed + 1) * per
        fp["done"] = clock
        clock += 3.0  # read time, in NORMAL mode
        nxt = files[(fi + 1) % len(files)]
        fp["cmd"] = ":e " + (nxt["short"] if narrow else nxt["path"])
        fp["cmd_start"] = clock
        fp["cmd_per"] = 0.032
        clock += (len(fp["cmd"]) + 1) * fp["cmd_per"] + 0.55
        fp["end"] = clock
        plan.append(fp)
    total = clock

    def woff(name):
        return base64.b64encode((FONTS / name).read_bytes()).decode()

    code_bg = t["code"]
    status_bg = mix(code_bg, t["fg"], 0.03)
    hl = mix(code_bg, t["fg"], 0.035)
    css = (
        f'@font-face{{font-family:"JBM";src:url(data:font/woff2;base64,{woff("JetBrainsMono-code-400.woff2")}) format("woff2");font-weight:400}}'
        f'text{{font-family:"JBM","JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:{fmt(fs)}px;fill:{t["f"]};white-space:pre}}'
        f'.k{{fill:{t["k"]}}}.s{{fill:{t["s"]}}}.c{{fill:{t["c"]}}}.n{{fill:{t["n"]}}}.t{{fill:{t["t"]}}}.f{{fill:{t["f"]}}}'
        f'.no{{fill:{t["dim"]};text-anchor:end}}.tl{{fill:{t["dim"]};opacity:.55}}.ui{{font-size:{fmt(fs - 1 if not narrow else fs - 0.5)}px;fill:{t["muted"]}}}'
        f'.cur{{fill:{t["accent"]};animation:b 1.1s steps(1) infinite}}@keyframes b{{50%{{opacity:0}}}}'
        '@media (prefers-reduced-motion:reduce){.cur{animation:none}}'
    )
    about = ", ".join(f["about"] for f in files)
    label = f"A code editor typing short excerpts from my repositories: {about}."
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'role="img" aria-label="{escape(label)}" xml:space="preserve">',
         f"<title>{escape(label)}</title>", f"<style>{css}</style>"]
    # The loop: everything below starts again each time L ends.
    o.append(f'<rect width="0" height="0"><animate id="L" attributeName="x" from="0" to="0" begin="0s;L.end" dur="{fmt(total)}s"/></rect>')

    # Window, top bar, status line and command line.
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{code_bg}" stroke="{t["line2"]}"/>')
    o.append(f'<path d="M1 {top_h}.5H{W - 1}M1 {fmt(code_bot)}H{W - 1}" stroke="{t["line"]}"/>')
    o.append(f'<rect x="1" y="{fmt(code_bot + 0.5)}" width="{W - 2}" height="{stat_h - 0.5}" fill="{status_bg}"/>')
    d, box = logo_path()
    d = re.sub(r"\d+\.\d+", lambda m: fmt(round(float(m.group(0)), 1)), d)  # 0.1 units is plenty at this size
    mark_h = 11
    scale = mark_h / box[3]
    o.append(f'<g transform="translate({fmt(W - 16 - box[2] * scale)} {fmt(top_h / 2 - mark_h / 2)}) scale({fmt(scale)}) '
             f'translate({fmt(-box[0])} {fmt(-box[1])})" fill="{t["dim"]}"><path transform="scale(1,-1)" d="{d}"/></g>')

    # The column of ~ marks, drawn once and reused for each file.
    clips = ['<g id="tl">' + "".join(f'<text class="tl" x="{10 if narrow else 14}" y="{fmt(base(code_top + j * rh))}">~</text>'
                                     for j in range(nrows)) + "</g>"]
    cursor_anims = []
    for fi, (f, rows, fp) in enumerate(zip(files, laid, plan)):
        g = [f'<g visibility="hidden">{show_between(fp["start"], fp["end"])}']
        # Tab with the file name.
        name = f["path"].split("/")[-1]
        g.append(f'<circle cx="18" cy="{top_h / 2}" r="3" fill="{t["warm"]}"/>')
        g.append(f'<text class="ui" x="28" y="{fmt(top_h / 2 + fs * 0.33)}" style="fill:{t["fg"]}">{escape(name)}</text>')
        # Current row highlight.
        row_points = [(fp["start"], code_top)] + [(r["start"], code_top + j * rh) for j, r in enumerate(fp["rows"]) if j > 0]
        g.append(f'<rect x="1" y="{code_top}" width="{W - 2}" height="{rh}" fill="{hl}">{stepper("y", row_points)}</rect>')
        # Line numbers appear row by row; the ~ marks below them step down.
        gid = f"g{fi}"
        reveal = [(fp["start"], rh)] + [(r["start"], (j + 1) * rh) for j, r in enumerate(fp["rows"]) if j > 0]
        clips.append(f'<clipPath id="{gid}"><rect x="0" y="{code_top}" width="{gut}" height="{rh}">{stepper("height", reveal)}</rect></clipPath>')
        tildes = [(fp["start"], code_top + rh)] + [(r["start"], code_top + (j + 1) * rh) for j, r in enumerate(fp["rows"]) if j > 0]
        clips.append(f'<clipPath id="{gid}t"><rect x="0" y="{code_top + rh}" width="{gut}" height="{fmt(nrows * rh)}">{stepper("y", tildes)}</rect></clipPath>')
        nums = "".join(f'<text class="no" x="{gut - (10 if narrow else 16)}" y="{fmt(base(code_top + j * rh))}">{r["no"]}</text>'
                       for j, r in enumerate(rows) if r["no"] is not None)
        g.append(f'<g clip-path="url(#{gid})">{nums}</g>')
        g.append(f'<use href="#tl" clip-path="url(#{gid}t)"/>')
        # The code. Each row has its own rectangle in the file's clip, which widens one
        # character per step while that row is typed.
        row_rects, row_texts = [], []
        for j, (row, rp) in enumerate(zip(rows, fp["rows"])):
            chars = row["chars"][row["indent"]:]
            if not chars:
                cursor_anims.append(f'<set attributeName="x" to="0" begin="{at(rp["start"])}"/>')
                continue
            spans, cls, buf = [], None, ""
            for ch, c in chars:
                if c != cls and buf:
                    spans.append((cls, buf))
                    buf = ""
                cls = c
                buf += ch
            spans.append((cls, buf))
            # Calls ("f") are drawn in the plain text colour on the site, so they need no tspan.
            body = "".join(f'<tspan class="{c}">{escape(s)}</tspan>' if c and c != "f" else escape(s) for c, s in spans)
            n = len(chars)
            # Clip and cursor count in characters (see `chars_x`), so each step is a small whole number.
            cols_typed = ";".join(str(row["indent"] + k) for k in range(n + 1))
            dur = fmt((n + 1) * rp["per"])
            row_rects.append(f'<rect y="{fmt(code_top + j * rh)}" width="0" height="{rh}">'
                             f'<set attributeName="width" to="0" begin="L.begin"/>'
                             f'<animate attributeName="width" begin="{at(rp["start"])}" dur="{dur}s" calcMode="discrete" values="{cols_typed}" fill="freeze"/>'
                             f"</rect>")
            cursor_anims.append(f'<animate attributeName="x" begin="{at(rp["start"])}" dur="{dur}s" calcMode="discrete" values="{cols_typed}" fill="freeze"/>')
            row_texts.append(f'<text x="{fmt(x0 + row["indent"] * cw)}" y="{fmt(base(code_top + j * rh))}">{body}</text>')
        clips.append(f'<clipPath id="f{fi}" transform="{chars_x}">' + "".join(row_rects) + "</clipPath>")
        g.append(f'<g clip-path="url(#f{fi})">' + "".join(row_texts) + "</g>")
        # Status line: INSERT while typing, NORMAL when done, then the file's path.
        sy = code_bot + stat_h / 2 + fs * 0.33
        pill_w = 6 * cw + 20
        for mode, colour, vis in (("INSERT", t["warm"], (fp["start"], fp["done"])), ("NORMAL", t["accent"], (fp["done"], fp["end"]))):
            g.append(f'<g visibility="hidden">{show_between(*vis)}'
                     f'<rect x="1" y="{fmt(code_bot + 0.5)}" width="{fmt(pill_w)}" height="{stat_h - 0.5}" fill="{colour}"/>'
                     f'<text class="ui" x="{fmt(1 + pill_w / 2)}" y="{fmt(sy)}" text-anchor="middle" '
                     f'style="fill:{t["on_accent"]};letter-spacing:.06em">{mode}</text></g>')
        path = f["short"] if narrow else f'{f["path"]}  [{f["lang"]}]'
        g.append(f'<text class="ui" x="{fmt(pill_w + 12)}" y="{fmt(sy)}">{escape(path)}</text>')
        if not narrow:
            last = f["code"][-1]
            g.append(f'<g visibility="hidden">{show_between(fp["done"], fp["end"])}'
                     f'<text class="ui" x="{W - 14}" y="{fmt(sy)}" text-anchor="end">{len(f["code"])}:{len(last)}  All</text></g>')
        # Command line: ":e next/file" opens the next excerpt, the way vim does.
        cy = code_bot + stat_h + cmd_h / 2
        n = len(fp["cmd"])
        back = int((x0 - 10) // cw)  # the command line starts this many characters left of the code
        cols_typed = ";".join(str(k - back) for k in range(n + 1))
        dur = fmt((n + 1) * fp["cmd_per"])
        cid = f"c{fi}"
        clips.append(f'<clipPath id="{cid}" transform="{chars_x}"><rect x="{-back}" y="{fmt(cy - rh / 2)}" width="0" height="{rh}">'
                     f'<set attributeName="width" to="0" begin="L.begin"/>'
                     f'<animate attributeName="width" begin="{at(fp["cmd_start"])}" dur="{dur}s" calcMode="discrete" values="{";".join(str(k) for k in range(n + 1))}" fill="freeze"/>'
                     f"</rect></clipPath>")
        g.append(f'<text x="{fmt(x0 - back * cw)}" y="{fmt(cy + fs * 0.36)}" clip-path="url(#{cid})">{escape(fp["cmd"])}</text>')
        cursor_anims.append(f'<animate attributeName="x" begin="{at(fp["cmd_start"])}" dur="{dur}s" calcMode="discrete" values="{cols_typed}" fill="freeze"/>')
        # The cursor's row.
        ys = [(fp["start"], code_top + (rh - cur_h) / 2)]
        ys += [(r["start"], code_top + j * rh + (rh - cur_h) / 2) for j, r in enumerate(fp["rows"]) if j > 0]
        ys.append((fp["cmd_start"], cy - cur_h / 2))
        cursor_anims.append(stepper("y", ys))
        cursor_anims.append(f'<set attributeName="x" to="{rows[0]["indent"]}" begin="{at(fp["start"])}"/>')
        g.append("</g>")
        o.extend(g)

    o.insert(3, "<defs>" + "".join(clips) + "</defs>")
    o.append(f'<g transform="{chars_x}"><rect class="cur" x="0" y="{fmt(code_top + (rh - cur_h) / 2)}" width="1" height="{fmt(cur_h)}">'
             + "".join(cursor_anims) + "</rect></g>")
    o.append("</svg>")
    return "".join(o) + "\n", label


# ---------------------------------------------------------------- README

def picture(stub, alt, size, narrow_size=None, url=None, ext="png", extra=""):
    """HTML that shows the light or dark image to match the viewer's theme, and the wide or
    narrow one to match the screen. Width only: on a small screen the picture then shrinks
    without being squashed."""
    a = f"assets/folio/{stub}"
    if narrow_size:
        tag = (f'<picture>'
               f'<source media="(min-width: {WIDE_FROM}px) and (prefers-color-scheme: dark)" srcset="{a}-wide-dark.{ext}" width="{size[0]}" />'
               f'<source media="(min-width: {WIDE_FROM}px)" srcset="{a}-wide-light.{ext}" width="{size[0]}" />'
               f'<source media="(prefers-color-scheme: dark)" srcset="{a}-narrow-dark.{ext}" />'
               f'<img src="{a}-narrow-light.{ext}" alt="{escape(alt)}" width="{narrow_size[0]}"{extra} /></picture>')
    else:
        tag = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{a}-dark.{ext}" />'
               f'<img src="{a}-light.{ext}" alt="{escape(alt)}" width="{size[0]}"{extra} /></picture>')
    return f'<a href="{escape(url)}">{tag}</a>' if url else tag


def check_files(p):
    """Stop early if something profile.json needs is not there."""
    missing = [f"assets/icons/{icon}-{theme}.svg" for icon, _, _ in p["about"] for theme in THEMES
               if not (ROOT / "assets" / "icons" / f"{icon}-{theme}.svg").exists()]
    needed = [LOGO, FOLIO / p["photo"]] + [FONTS / n for n in (
        "LibreBaskerville.ttf", "LibreBaskerville-Italic.ttf", "JetBrainsMono.ttf",
        "JetBrainsMono-code-400.woff2")]
    missing += [str(f.relative_to(ROOT)) for f in needed if not f.exists()]
    if missing:
        raise SystemExit("Missing files:\n  " + "\n  ".join(sorted(set(missing))))


def main():
    p = PROFILE
    check_files(p)
    written = set()
    html = ["<!-- Made by folio/build.py from folio/profile.json. Edit those, then run: python3 folio/build.py -->", ""]

    # Header: photo, name, role and the facts, in a frame like the top of the website.
    for theme in THEMES:
        wide = save(draw_header(theme, False), f"header-wide-{theme}.png", written)
        narrow = save(draw_header(theme, True), f"header-narrow-{theme}.png", written)
    facts = ". ".join(f"{k}: {v}" for k, v in p["creds"])
    html.append('<p align="center">' + picture("header", f'{p["name"]}. {p["role"]}. {p["bio"]} {facts}.', wide, narrow) + "</p>")
    html.append("")

    # Links as small outlined buttons.
    pills = []
    for s in p["social"]:
        for theme in THEMES:
            size = save(draw_pill(s["label"], s["icon"], theme), f'link-{s["icon"]}-{theme}.png', written)
        pills.append(picture(f'link-{s["icon"]}', s["title"], size, url=s["url"]))
    html.append('<p align="center">\n  ' + "\n  ".join(pills) + "\n</p>")
    html.append("")

    # The editor that types itself.
    for theme in THEMES:
        for kind, narrow in (("wide", False), ("narrow", True)):
            svg, label = editor_svg(theme, narrow)
            (OUT / f"editor-{kind}-{theme}.svg").write_text(svg, encoding="utf-8")
            written.add(f"editor-{kind}-{theme}.svg")
            size = re.search(r'width="(\d+)" height="(\d+)"', svg).groups()
            if kind == "wide":
                wide = (int(size[0]), int(size[1]))
            else:
                narrow = (int(size[0]), int(size[1]))
    html.append('<p align="center">' + picture("editor", label, wide, narrow, ext="svg") + "</p>")
    html.append("")

    # Projects, as rows of the site's project list.
    for no, section in enumerate(p["sections"], 1):
        stub = "label-" + section["label"].lower().replace(" ", "-")
        count = f'{len(section["projects"])} projects'
        for theme in THEMES:
            wide = save(draw_label(f"{no:02d}", section["label"], count, theme, PAGE), f"{stub}-wide-{theme}.png", written)
            narrow = save(draw_label(f"{no:02d}", section["label"], count, theme, NARROW), f"{stub}-narrow-{theme}.png", written)
        rows = [picture(stub, section["label"], wide, narrow)]
        for proj in section["projects"]:
            for theme in THEMES:
                wide = save(draw_row(proj, theme, PAGE, False), f'row-{proj["id"]}-wide-{theme}.png', written)
                narrow = save(draw_row(proj, theme, NARROW, True), f'row-{proj["id"]}-narrow-{theme}.png', written)
            url = proj.get("url") or GITHUB + proj["repo"]
            alt = f'{proj["title"]} ({proj["tag"]}, {proj["status"]}): {proj["text"]}'
            rows.append(picture(f'row-{proj["id"]}', alt, wide, narrow, url=url))
        html.append('<p align="center">' + "<br />\n".join(rows) + "</p>")
        html.append("")

    # The logo as a quiet divider, then the Sponsor button (works once GitHub Sponsors is on).
    for theme in THEMES:
        size = save(draw_divider(theme), f"divider-{theme}.png", written)
    html.append('<p align="center">' + picture("divider", "", size) + "</p>")
    html.append("")
    if p.get("sponsor"):
        for theme in THEMES:
            size = save(draw_pill("sponsor", "heart", theme, colour="#bf3989"), f"sponsor-{theme}.png", written)
        html.append('<p align="center">' + picture("sponsor", "Sponsor me on GitHub", size, url=p["sponsor"]) + "</p>")
        html.append("")

    # The longer story stays as plain text, folded away.
    html.append("<details>\n<summary>More about me</summary>\n")
    for icon_name, head, text in p["about"]:
        html.append(
            f'- <picture><source media="(prefers-color-scheme: dark)" srcset="assets/icons/{icon_name}-dark.svg">'
            f'<img src="assets/icons/{icon_name}-light.svg" width="16" alt=""></picture> **{head}:** {text}'
        )
    html.append(f"\n**Tools:** {p['tools']}\n\n</details>")

    (ROOT / "README.md").write_text("\n".join(html) + "\n", encoding="utf-8")

    # Remove images an older build made that nothing uses now.
    for old in OUT.iterdir():
        if old.is_file() and old.name not in written and old.suffix in (".png", ".svg"):
            old.unlink()
    print(f"Wrote README.md and {len(written)} images in assets/folio/")


PROFILE = json.loads((FOLIO / "profile.json").read_text(encoding="utf-8"))

if __name__ == "__main__":
    main()
