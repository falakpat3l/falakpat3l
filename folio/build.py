"""Build the GitHub profile: card images and README.md.

What it does:
  1. Reads folio/profile.json (all the words and links).
  2. Draws each card as a PNG, once for light mode and once for dark mode,
     into assets/folio/. Pictures for the cards come from folio/shots/.
  3. Writes README.md, which shows the right card for the viewer's theme.

Run it from the repo folder after editing profile.json or a picture:
    pip install pillow
    python3 folio/build.py

The look matches falakpatel.com: near-black cards, a serif close to
Times New Roman (Newsreader), small monospace labels (IBM Plex Mono),
one soft blue accent and a thin line-drawn eye ("drishti" means vision).
Both fonts are in folio/fonts with their SIL Open Font Licence files.
"""

import json
from functools import lru_cache
from html import escape as _escape
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FOLIO = ROOT / "folio"
SHOTS = FOLIO / "shots"
FONTS = FOLIO / "fonts"
OUT = ROOT / "assets" / "folio"
GITHUB = "https://github.com/falakpat3l/"

# Everything is drawn at 4x and saved at 2x: lines and curves come out smooth,
# and text stays sharp on high-resolution screens.
S = 4
SAVE = 2

# Colours for each theme. Dark follows falakpatel.com; light keeps the classic link blue.
THEMES = {
    "light": {"card": "#ffffff", "fg": "#1f2328", "muted": "#59636e", "line": "#d1d9e0",
              "link": "#0000ee", "accent": "#0000ee"},
    "dark": {"card": "#0d0d0d", "fg": "#ededed", "muted": "#9e9e9e", "line": "#2a2a2a",
             "link": "#8ab4f8", "accent": "#8ab4f8"},
}

# Card sizes in screen pixels (width, height). Each includes a 6 px gap all round.
GAP = 6
SIZES = {"big": (248, 318), "wide": (372, 138), "small": (248, 112)}
PAGE = 744  # three big cards side by side

TITLE_LINE, TEXT_LINE = 25, 20  # line heights in screen pixels


@lru_cache(maxsize=None)
def font(style, size, weight=400):
    """Newsreader (serif) for words, IBM Plex Mono for small labels.

    style: "serif", "italic" or "mono". size is in screen pixels.
    """
    if style == "mono":
        f = ImageFont.truetype(str(FONTS / ("IBMPlexMono-Medium.ttf" if weight >= 500 else "IBMPlexMono-Regular.ttf")), round(size * S))
        return f
    name = "Newsreader-Italic.ttf" if style == "italic" else "Newsreader.ttf"
    f = ImageFont.truetype(str(FONTS / name), round(size * S))
    # Axes are weight, then optical size (6 to 72). Match optical size to the text size.
    f.set_variation_by_axes([weight, max(6, min(72, size))])
    return f


def escape(text):
    """Make text safe inside an HTML attribute (keeps apostrophes readable)."""
    return _escape(text, quote=False).replace('"', "&quot;")


def wrap(draw, text, fnt, width):
    """Split text into lines that fit the given width."""
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def canvas(w, h):
    """A transparent image of w x h screen pixels."""
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def card_box(draw, w, h, t):
    """The outlined card with small rounded corners. Returns its inner box."""
    box = (GAP * S, GAP * S, (w - GAP) * S - 1, (h - GAP) * S - 1)
    draw.rounded_rectangle(box, radius=8 * S, fill=t["card"], outline=t["line"], width=S)
    return box


def picture(spec, theme, t, w, h):
    """The card's picture, cut or fitted to w x h screen pixels."""
    src = Image.open(SHOTS / spec[theme]).convert("RGB")
    if "crop" in spec:
        x0, y0, x1, y1 = spec["crop"]
        src = src.crop((int(x0 * src.width), int(y0 * src.height), int(x1 * src.width), int(y1 * src.height)))
    if spec.get("trim"):
        bg = src.getpixel((0, 0))
        diff = Image.new("RGB", src.size, bg)
        box = ImageChops.difference(src, diff).getbbox()
        if box:
            src = src.crop(box)
    W, H = w * S, h * S
    if spec.get("fit") == "contain":
        out = Image.new("RGB", (W, H), t["card"])
        scale = min((W - 24 * S) / src.width, (H - 24 * S) / src.height)
        small = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.LANCZOS)
        x, y = (W - small.width) // 2, (H - small.height) // 2
        if spec.get("bg"):  # a small rounded tile behind the picture (a QR code needs a light background)
            m = 6 * S
            ImageDraw.Draw(out).rounded_rectangle((x - m, y - m, x + small.width + m, y + small.height + m),
                                                  radius=6 * S, fill=spec["bg"])
        out.paste(small, (x, y))
        return out
    scale = max(W / src.width, H / src.height)  # "cover": fill the box, cut the edges
    big = src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1), Image.LANCZOS)
    left, top = (big.width - W) // 2, (big.height - H) // 2
    return big.crop((left, top, left + W, top + H))


def draw_card(card, theme):
    t = THEMES[theme]
    w, h = SIZES[card["kind"]]
    img, d = canvas(w, h)
    x0, y0, x1, y1 = card_box(d, w, h, t)
    pad = 13 * S
    title_f, text_f, meta_f = font("serif", 18, 600), font("serif", 14.5), font("mono", 11)

    if card["kind"] == "big":
        pic_h = 150
        pic = picture(card["image"], theme, t, w - 2 * GAP - 2, pic_h)
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width - 1, pic.height + 20 * S), radius=8 * S, fill=255)
        img.paste(pic, (x0 + S, y0 + S), mask)
        d.line((x0, y0 + S + pic.height, x1, y0 + S + pic.height), fill=t["line"], width=S)
        tx, ty, tw = x0 + pad, y0 + S + pic.height + 10 * S, x1 - x0 - 2 * pad
    elif card["kind"] == "wide":
        pic_w = 120
        pic = picture(card["image"], theme, t, pic_w, h - 2 * GAP - 2)
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width + 20 * S, pic.height - 1), radius=8 * S, fill=255)
        img.paste(pic, (x0 + S, y0 + S), mask)
        d.line((x0 + S + pic.width, y0, x0 + S + pic.width, y1), fill=t["line"], width=S)
        tx, ty, tw = x0 + S + pic.width + pad, y0 + 10 * S, x1 - (x0 + pic.width) - 2 * pad
    else:
        tx, ty, tw = x0 + pad, y0 + 10 * S, x1 - x0 - 2 * pad
    title_w = tw
    if card["kind"] == "small" and card.get("icon"):  # a small line drawing at the end of the title row
        size = 20 * S
        cx, cy = x1 - pad - size // 2, ty + 12 * S
        line_icon(d, card["icon"], cx, cy, size, t["muted"])
        title_w -= size + 8 * S

    # Stop with a clear message instead of drawing text past the card's edge.
    if d.textlength(card["title"], font=title_f) > title_w:
        raise SystemExit(f"Card '{card['id']}': the title is too long for a {card['kind']} card. Shorten it in profile.json.")
    meta_y = y1 - pad - 12 * S
    bottom = (meta_y - 4 * S) if card.get("meta") else (y1 - 6 * S)  # keep a small margin
    lines = wrap(d, card["text"], text_f, tw)
    if ty + TITLE_LINE * S + (len(lines) - 1) * TEXT_LINE * S + text_f.getbbox("gy")[3] > bottom:
        raise SystemExit(f"Card '{card['id']}': the text needs {len(lines)} lines and does not fit. Shorten it in profile.json.")
    if card.get("meta") and d.textlength(card["meta"], font=meta_f) > tw:
        raise SystemExit(f"Card '{card['id']}': the meta line is too long. Shorten it in profile.json.")

    d.text((tx, ty), card["title"], font=title_f, fill=t["link"])
    ty += TITLE_LINE * S
    for line in lines:
        d.text((tx, ty), line, font=text_f, fill=t["fg"])
        ty += TEXT_LINE * S
    if card.get("meta"):
        d.text((tx, meta_y), card["meta"], font=meta_f, fill=t["muted"])
    return img


def line_icon(d, kind, cx, cy, size, colour):
    """Tiny line drawings: 'cube', 'spark', 'watch', 'pulse' or 'globe', centred on (cx, cy)."""
    r, w = size // 2, max(1, int(1.5 * S))
    if kind == "cube":
        a, b = int(r * 0.9), int(r * 0.45)
        top = [(cx, cy - a), (cx + a, cy - b), (cx, cy), (cx - a, cy - b)]
        d.polygon(top, outline=colour, width=w)
        d.line([(cx - a, cy - b), (cx - a, cy + b), (cx, cy + a), (cx + a, cy + b), (cx + a, cy - b)], fill=colour, width=w, joint="curve")
        d.line([(cx, cy), (cx, cy + a)], fill=colour, width=w)
    elif kind == "spark":
        a, b = int(r * 0.95), int(r * 0.22)
        pts = [(cx, cy - a), (cx + b, cy - b), (cx + a, cy), (cx + b, cy + b),
               (cx, cy + a), (cx - b, cy + b), (cx - a, cy), (cx - b, cy - b)]
        d.polygon(pts, outline=colour, width=w)
    elif kind == "watch":
        a, h = int(r * 0.55), int(r * 0.7)
        d.rounded_rectangle((cx - a, cy - h, cx + a, cy + h), radius=int(r * 0.25), outline=colour, width=w)
        d.line([(cx - a // 2, cy - h), (cx - a // 2, cy - r), (cx + a // 2, cy - r), (cx + a // 2, cy - h)], fill=colour, width=w)
        d.line([(cx - a // 2, cy + h), (cx - a // 2, cy + r), (cx + a // 2, cy + r), (cx + a // 2, cy + h)], fill=colour, width=w)
    elif kind == "pulse":
        pts = [(-1, 0), (-0.45, 0), (-0.25, -0.6), (0.05, 0.7), (0.25, -0.2), (0.4, 0), (1, 0)]
        d.line([(cx + int(x * r), cy + int(y * r)) for x, y in pts], fill=colour, width=w, joint="curve")
    elif kind == "globe":
        a = int(r * 0.9)
        d.ellipse((cx - a, cy - a, cx + a, cy + a), outline=colour, width=w)
        d.ellipse((cx - a // 2, cy - a, cx + a // 2, cy + a), outline=colour, width=w)
        d.line([(cx - a, cy), (cx + a, cy)], fill=colour, width=w)


def eye(d, cx, cy, half_w, t, width):
    """A thin line-drawn eye: two lid curves, an iris and a small pupil."""
    half_h = half_w * 0.5
    steps = 48

    def lid(sign):
        # A quadratic curve from corner to corner through the lid's middle.
        pts = []
        for i in range(steps + 1):
            u = i / steps
            x = cx - half_w + 2 * half_w * u
            y = cy + sign * 4 * half_h * u * (1 - u)  # half_h at the middle
            pts.append((x, y))
        return pts

    d.line(lid(-1), fill=t["muted"], width=width, joint="curve")
    d.line(lid(1), fill=t["muted"], width=width, joint="curve")
    r = half_h * 0.62
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=t["accent"], width=width)
    p = r * 0.38
    d.ellipse((cx - p, cy - p, cx + p, cy + p), fill=t["accent"])


def draw_label(text, theme):
    """Section heading in small monospace, like a code comment, between two thin lines."""
    t = THEMES[theme]
    w, h = 300, 34  # narrow enough to show at full size on a phone
    img, d = canvas(w, h)
    f = font("mono", 12.5)
    text, prefix = text.lower(), "// "
    pw, tw = d.textlength(prefix, font=f), d.textlength(text, font=f)
    cy = h * S // 2
    x = w * S / 2 - (pw + tw) / 2
    d.text((x, cy), prefix, font=f, fill=t["accent"], anchor="lm")
    d.text((x + pw, cy), text, font=f, fill=t["muted"], anchor="lm")
    gap, edge = 12 * S, 16 * S
    for a, b in ((edge, x - gap), (x + pw + tw + gap, w * S - edge)):
        d.line((a, cy, b, cy), fill=t["line"], width=S)
    return img


def draw_divider(theme):
    """A short line with a small open eye in the middle."""
    t = THEMES[theme]
    w, h = 200, 26
    img, d = canvas(w, h)
    cx, cy, half = w * S // 2, h * S // 2, 15 * S
    d.line((16 * S, cy, cx - half - 10 * S, cy), fill=t["line"], width=S)
    d.line((cx + half + 10 * S, cy, w * S - 16 * S, cy), fill=t["line"], width=S)
    eye(d, cx, cy, half, t, int(1.4 * S))
    return img


def draw_sponsor(theme):
    """An outlined 'Sponsor' button with a small heart."""
    t = THEMES[theme]
    w, h = 132, 40
    img, d = canvas(w, h)
    d.rounded_rectangle((2 * S, 4 * S, (w - 2) * S, (h - 4) * S), radius=16 * S, fill=t["card"], outline=t["line"], width=S)
    # The heart: two circles and a triangle.
    hx, hy, r = 26 * S, h * S // 2 - S, 4 * S
    heart = "#bf3989"  # GitHub's sponsor pink
    d.ellipse((hx - 2 * r, hy - r, hx, hy + r), fill=heart)
    d.ellipse((hx, hy - r, hx + 2 * r, hy + r), fill=heart)
    d.polygon([(hx - 2 * r + S, hy + S), (hx + 2 * r - S, hy + S), (hx, hy + 2 * r + 2 * S)], fill=heart)
    d.text((hx + 16 * S, h * S // 2), "Sponsor", font=font("serif", 17), fill=t["fg"], anchor="lm")
    return img


def draw_text_image(lines, w, theme):
    """Centred text block: [(text, style, size, weight, colour key, line height), ...]."""
    t = THEMES[theme]
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    rows = []
    for text, style, size, weight, key, lh in lines:
        f = font(style, size, weight)
        for line in wrap(probe, text, f, (w - 24) * S):
            rows.append((line, f, int(size * lh), t[key]))
    h = sum(step for _, _, step, _ in rows) + 8
    img, d = canvas(w, h)
    y = 4 * S
    for line, f, step, colour in rows:
        d.text((w * S // 2, y), line, font=f, fill=colour, anchor="ma")
        y += step * S
    return img


def save(img, name):
    """Save at 2x (smooth edges) and return the size in screen pixels."""
    OUT.mkdir(parents=True, exist_ok=True)
    w, h = img.width // S, img.height // S
    img.resize((w * SAVE, h * SAVE), Image.LANCZOS).save(OUT / name, optimize=True)
    return w, h


def themed(name_stub, alt, url=None, size=None, extra=""):
    """HTML that shows the light or dark image to match the viewer's theme."""
    # Width only: on a narrow phone screen the picture then shrinks without being squashed.
    w = size[0]
    tag = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/folio/{name_stub}-dark.png" />'
           f'<img src="assets/folio/{name_stub}-light.png" alt="{escape(alt)}" width="{w}"{extra} /></picture>')
    return f'<a href="{escape(url)}">{tag}</a>' if url else tag


def check_files(p):
    """Stop early if profile.json points at a picture, icon or font that is not there."""
    missing = []
    icons = [s["icon"] for s in p["social"]] + [row[0] for row in p["about"]]
    for icon in icons:
        missing += [f"assets/icons/{icon}-{theme}.svg" for theme in THEMES
                    if not (ROOT / "assets" / "icons" / f"{icon}-{theme}.svg").exists()]
    for section in p["sections"]:
        for row in section["rows"]:
            for card in row:
                image = card.get("image", {})
                missing += [f"folio/shots/{image[theme]}" for theme in THEMES
                            if theme in image and not (SHOTS / image[theme]).exists()]
    for name in ("Newsreader.ttf", "Newsreader-Italic.ttf", "IBMPlexMono-Regular.ttf", "IBMPlexMono-Medium.ttf"):
        if not (FONTS / name).exists():
            missing.append(f"folio/fonts/{name}")
    if missing:
        raise SystemExit("Missing files:\n  " + "\n  ".join(sorted(set(missing))))


def main():
    p = json.loads((FOLIO / "profile.json").read_text())
    check_files(p)
    html = ["<!-- Made by folio/build.py from folio/profile.json. Edit those, then run: python3 folio/build.py -->", ""]

    # Name, tagline and bio. Each has a wide version for computers and a narrow one for phones.
    for theme in THEMES:
        size = save(draw_text_image([(p["name"], "serif", 40, 400, "fg", 1.3),
                                     (p["tagline"], "italic", 17, 400, "muted", 1.5)], PAGE, theme), f"name-{theme}.png")
        nsize = save(draw_text_image([(p["name"], "serif", 31, 400, "fg", 1.3),
                                      (p["tagline"], "italic", 16, 400, "muted", 1.4)], 320, theme), f"name-narrow-{theme}.png")
        wide = save(draw_text_image([(p["bio"], "serif", 17, 400, "fg", 1.5)], PAGE, theme), f"bio-wide-{theme}.png")
        narrow = save(draw_text_image([(p["bio"], "serif", 16.5, 400, "fg", 1.5)], 320, theme), f"bio-narrow-{theme}.png")
    html.append(
        '<p align="center"><picture>'
        f'<source media="(min-width: 1012px) and (prefers-color-scheme: dark)" srcset="assets/folio/name-dark.png" width="{size[0]}" />'
        f'<source media="(min-width: 1012px)" srcset="assets/folio/name-light.png" width="{size[0]}" />'
        '<source media="(prefers-color-scheme: dark)" srcset="assets/folio/name-narrow-dark.png" />'
        f'<img src="assets/folio/name-narrow-light.png" alt="{escape(p["name"] + ". " + p["tagline"])}" width="{nsize[0]}" />'
        "</picture></p>"
    )
    html.append(
        '<p align="center"><picture>'
        f'<source media="(min-width: 1012px) and (prefers-color-scheme: dark)" srcset="assets/folio/bio-wide-dark.png" width="{wide[0]}" />'
        f'<source media="(min-width: 1012px)" srcset="assets/folio/bio-wide-light.png" width="{wide[0]}" />'
        '<source media="(prefers-color-scheme: dark)" srcset="assets/folio/bio-narrow-dark.png" />'
        f'<img src="assets/folio/bio-narrow-light.png" alt="{escape(p["bio"])}" width="{narrow[0]}" />'
        "</picture></p>"
    )
    for theme in THEMES:
        size = save(draw_divider(theme), f"divider-{theme}.png")
    html.append('<p align="center">' + themed("divider", "", size=size) + "</p>")
    html.append("")

    # Links as small icons (the icons live in assets/icons).
    icons = []
    for s in p["social"]:
        icons.append(
            f'<a href="{escape(s["url"])}" title="{escape(s["title"])}"><picture>'
            f'<source media="(prefers-color-scheme: dark)" srcset="assets/icons/{s["icon"]}-dark.svg" />'
            f'<img src="assets/icons/{s["icon"]}-light.svg" width="22" height="22" alt="{escape(s["title"])}" /></picture></a>'
        )
    html.append('<p align="center">\n  ' + "&nbsp;&nbsp;&nbsp;\n  ".join(icons) + "\n</p>")
    html.append("")

    # Project cards, one section at a time.
    for section in p["sections"]:
        stub = "label-" + section["label"].lower().replace(" ", "-")
        for theme in THEMES:
            size = save(draw_label(section["label"], theme), f"{stub}-{theme}.png")
        html.append('<p align="center">' + themed(stub, section["label"], size=size) + "</p>")
        rows = []
        for row in section["rows"]:
            cells = []
            for card in row:
                for theme in THEMES:
                    size = save(draw_card(card, theme), f"card-{card['id']}-{theme}.png")
                url = card.get("url") or GITHUB + card["repo"]
                alt = f'{card["title"]}: {card["text"]}' + (f' ({card["meta"]})' if card.get("meta") else "")
                cells.append(themed(f"card-{card['id']}", alt, url=url, size=size, extra=' align="top"'))
            rows.append("".join(cells))
        html.append('<p align="center">' + "<br />".join(rows) + "</p>")
        html.append("")

    # Sponsor button (works once GitHub Sponsors is turned on for the account).
    if p.get("sponsor"):
        for theme in THEMES:
            size = save(draw_sponsor(theme), f"sponsor-{theme}.png")
        html.append('<p align="center">' + themed("sponsor", "Sponsor me on GitHub", url=p["sponsor"], size=size) + "</p>")
        html.append("")

    # The longer story stays as plain text, folded away.
    html.append("<details>\n<summary>More about me</summary>\n")
    for icon, head, text in p["about"]:
        html.append(
            f'- <picture><source media="(prefers-color-scheme: dark)" srcset="assets/icons/{icon}-dark.svg">'
            f'<img src="assets/icons/{icon}-light.svg" width="16" alt=""></picture> **{head}:** {text}'
        )
    html.append(f"\n**Tools:** {p['tools']}\n\n</details>")

    (ROOT / "README.md").write_text("\n".join(html) + "\n")
    print(f"Wrote README.md and {len(list(OUT.glob('*.png')))} images in assets/folio/")


if __name__ == "__main__":
    main()
