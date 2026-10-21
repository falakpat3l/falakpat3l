"""Build the GitHub profile: card images and README.md.

What it does:
  1. Reads folio/profile.json (all the words and links).
  2. Draws each card as a PNG, once for light mode and once for dark mode,
     into assets/folio/. Pictures for the cards come from folio/shots/.
  3. Writes README.md, which shows the right card for the viewer's theme.

Run it from the repo folder after editing profile.json or a picture:
    pip install pillow
    python3 folio/build.py

The look matches falakpatel.com: Times-style serif, black and white,
thin outlined cards with small corners, link blue for titles.
"""

import json
from html import escape as _escape
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FOLIO = ROOT / "folio"
SHOTS = FOLIO / "shots"
OUT = ROOT / "assets" / "folio"
GITHUB = "https://github.com/falakpat3l/"

S = 2  # draw at twice the size so text stays sharp on high-resolution screens

# Colours for each theme, taken from falakpatel.com.
THEMES = {
    "light": {"card": "#ffffff", "fg": "#000000", "muted": "#555555", "line": "#d0d0d0", "link": "#0000ee"},
    "dark": {"card": "#141414", "fg": "#e6e6e6", "muted": "#9a9a9a", "line": "#333333", "link": "#8ab4f8"},
}

# Card sizes in screen pixels (width, height). Each includes a 6 px gap all round.
GAP = 6
SIZES = {"big": (248, 300), "wide": (372, 120), "small": (248, 92)}
PAGE = 744  # three big cards side by side

# Times New Roman on a Mac, Liberation Serif (same letter widths) on Linux.
FONT_FILES = {
    "regular": ["/System/Library/Fonts/Supplemental/Times New Roman.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"],
    "bold": ["/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"],
    "italic": ["/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"],
}


def escape(text):
    """Make text safe inside an HTML attribute (keeps apostrophes readable)."""
    return _escape(text, quote=False).replace('"', "&quot;")


def font(style, size):
    for path in FONT_FILES[style]:
        if Path(path).exists():
            return ImageFont.truetype(path, size * S)
    raise SystemExit(f"No serif font found for '{style}'. Install Liberation Serif or Times New Roman.")


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
    draw.rounded_rectangle(box, radius=6 * S, fill=t["card"], outline=t["line"], width=S)
    return box


def picture(spec, theme, t, w, h):
    """The card's picture, cut or fitted to w x h screen pixels."""
    if spec.get("draw") == "watch":
        return watch_drawing(w, h, t)
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


def watch_drawing(w, h, t):
    """A simple line drawing of the e-paper watch (there is no photo yet)."""
    img = Image.new("RGB", (w * S, h * S), t["card"])
    d = ImageDraw.Draw(img)
    cx, cy = w * S // 2, h * S // 2
    bw, bh = 92 * S, 104 * S
    strap = (cx - 30 * S, 0, cx + 30 * S, h * S)
    d.rectangle(strap, fill=t["line"])
    body = (cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2)
    d.rounded_rectangle(body, radius=18 * S, fill=t["card"], outline=t["fg"], width=2 * S)
    screen = (body[0] + 10 * S, body[1] + 12 * S, body[2] - 10 * S, body[3] - 12 * S)
    d.rounded_rectangle(screen, radius=6 * S, fill="#e9e7e1")
    ink = "#1a1a1a"
    d.text((cx, cy - 12 * S), "08:42", font=font("bold", 26), fill=ink, anchor="mm")
    d.text((cx, cy + 18 * S), "4,210 steps", font=font("regular", 12), fill=ink, anchor="mm")
    d.line((screen[0] + 12 * S, cy + 32 * S, screen[2] - 12 * S, cy + 32 * S), fill=ink, width=S)
    return img


def draw_card(card, theme):
    t = THEMES[theme]
    w, h = SIZES[card["kind"]]
    img, d = canvas(w, h)
    x0, y0, x1, y1 = card_box(d, w, h, t)
    pad = 12 * S
    title_f, text_f, tag_f = font("bold", 17), font("regular", 14), font("regular", 12)

    if card["kind"] == "big":
        pic_h = 150
        pic = picture(card["image"], theme, t, w - 2 * GAP - 2, pic_h)
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width - 1, pic.height + 20 * S), radius=6 * S, fill=255)
        img.paste(pic, (x0 + S, y0 + S), mask)
        d.line((x0, y0 + S + pic.height, x1, y0 + S + pic.height), fill=t["line"], width=S)
        tx, ty, tw = x0 + pad, y0 + S + pic.height + 10 * S, x1 - x0 - 2 * pad
    elif card["kind"] == "wide":
        pic_w = 120
        pic = picture(card["image"], theme, t, pic_w, h - 2 * GAP - 2)
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width + 20 * S, pic.height - 1), radius=6 * S, fill=255)
        img.paste(pic, (x0 + S, y0 + S), mask)
        d.line((x0 + S + pic.width, y0, x0 + S + pic.width, y1), fill=t["line"], width=S)
        tx, ty, tw = x0 + S + pic.width + pad, y0 + 10 * S, x1 - (x0 + pic.width) - 2 * pad
    else:
        tx, ty, tw = x0 + pad, y0 + 10 * S, x1 - x0 - 2 * pad
        if card.get("icon"):  # a small line drawing on the right
            size = 30 * S
            cx, cy = x1 - pad - size // 2, (y0 + y1) // 2
            line_icon(d, card["icon"], cx, cy, size, t["muted"])
            tw -= size + 8 * S

    # Stop with a clear message instead of drawing text past the card's edge.
    if d.textlength(card["title"], font=title_f) > tw:
        raise SystemExit(f"Card '{card['id']}': the title is too long for a {card['kind']} card. Shorten it in profile.json.")
    bottom = (y1 - pad - 16 * S) if card.get("tags") else (y1 - 6 * S)  # keep a small margin
    lines = wrap(d, card["text"], text_f, tw)
    if ty + 24 * S + (len(lines) - 1) * 19 * S + text_f.getbbox("gy")[3] > bottom:
        raise SystemExit(f"Card '{card['id']}': the text needs {len(lines)} lines and does not fit. Shorten it in profile.json.")
    if card.get("tags") and d.textlength(card["tags"], font=tag_f) > tw:
        raise SystemExit(f"Card '{card['id']}': the tags line is too long. Shorten it in profile.json.")

    d.text((tx, ty), card["title"], font=title_f, fill=t["link"])
    ty += 24 * S
    for line in lines:
        d.text((tx, ty), line, font=text_f, fill=t["fg"])
        ty += 19 * S
    if card.get("tags"):
        d.text((tx, y1 - pad - 14 * S), card["tags"], font=tag_f, fill=t["muted"])
    return img


def line_icon(d, kind, cx, cy, size, colour):
    """Tiny line drawings: 'cube', 'spark' or 'globe', centred on (cx, cy)."""
    r, w = size // 2, max(1, int(1.5 * S))
    if kind == "cube":
        a, b = int(r * 0.9), int(r * 0.45)
        top = [(cx, cy - a), (cx + a, cy - b), (cx, cy), (cx - a, cy - b)]
        d.polygon(top, outline=colour, width=w)
        d.line([(cx - a, cy - b), (cx - a, cy + b), (cx, cy + a), (cx + a, cy + b), (cx + a, cy - b)], fill=colour, width=w)
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


def draw_label(text, theme):
    """Section heading: italic words between two thin lines with a dot at each end."""
    t = THEMES[theme]
    w, h = 400, 34
    img, d = canvas(w, h)
    f = font("italic", 15)
    tw = d.textlength(text, font=f)
    cy = h * S // 2
    d.text((w * S // 2, cy), text, font=f, fill=t["muted"], anchor="mm")
    gap, edge, dot = 14 * S, 40 * S, 2 * S
    for x0, x1 in ((edge, w * S // 2 - tw / 2 - gap), (w * S // 2 + tw / 2 + gap, w * S - edge)):
        d.line((x0, cy, x1, cy), fill=t["line"], width=S)
    for x in (edge, w * S - edge):
        d.ellipse((x - dot, cy - dot, x + dot, cy + dot), fill=t["muted"])
    return img


def draw_divider(theme):
    """A short line with a small diamond in the middle."""
    t = THEMES[theme]
    w, h = 160, 18
    img, d = canvas(w, h)
    cx, cy, a = w * S // 2, h * S // 2, 4 * S
    d.line((10 * S, cy, cx - 3 * a, cy), fill=t["line"], width=S)
    d.line((cx + 3 * a, cy, w * S - 10 * S, cy), fill=t["line"], width=S)
    d.polygon([(cx, cy - a), (cx + a, cy), (cx, cy + a), (cx - a, cy)], outline=t["muted"], width=S)
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
    d.text((hx + 16 * S, h * S // 2), "Sponsor", font=font("regular", 16), fill=t["fg"], anchor="lm")
    return img


def draw_text_image(lines, w, theme):
    """Centred text block: [(text, style, size, colour key), ...]."""
    t = THEMES[theme]
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    rows = []
    for text, style, size, key in lines:
        f = font(style, size)
        for line in wrap(probe, text, f, (w - 24) * S):
            rows.append((line, f, size, t[key]))
    h = sum(int(size * 1.45) for _, _, size, _ in rows) + 8
    img, d = canvas(w, h)
    y = 4 * S
    for line, f, size, colour in rows:
        d.text((w * S // 2, y), line, font=f, fill=colour, anchor="ma")
        y += int(size * 1.45) * S
    return img


def save(img, name):
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name, optimize=True)
    return img.width // S, img.height // S


def themed(name_stub, alt, url=None, size=None, extra=""):
    """HTML that shows the light or dark image to match the viewer's theme."""
    w, h = size
    tag = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/folio/{name_stub}-dark.png" />'
           f'<img src="assets/folio/{name_stub}-light.png" alt="{escape(alt)}" width="{w}" height="{h}"{extra} /></picture>')
    return f'<a href="{escape(url)}">{tag}</a>' if url else tag


def check_files(p):
    """Stop early if profile.json points at a picture or icon that is not there."""
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
    if missing:
        raise SystemExit("Missing files:\n  " + "\n  ".join(sorted(set(missing))))


def main():
    p = json.loads((FOLIO / "profile.json").read_text())
    check_files(p)
    html = ["<!-- Made by folio/build.py from folio/profile.json. Edit those, then run: python3 folio/build.py -->", ""]

    # Name, tagline and bio. The bio has a wide version for computers and a narrow one for phones.
    for theme in THEMES:
        size = save(draw_text_image([(p["name"], "regular", 34, "fg"), (p["tagline"], "italic", 16, "muted")], PAGE, theme), f"name-{theme}.png")
        nsize = save(draw_text_image([(p["name"], "regular", 28, "fg"), (p["tagline"], "italic", 15, "muted")], 320, theme), f"name-narrow-{theme}.png")
        wide = save(draw_text_image([(p["bio"], "regular", 16, "fg")], PAGE, theme), f"bio-wide-{theme}.png")
        narrow = save(draw_text_image([(p["bio"], "regular", 16, "fg")], 320, theme), f"bio-narrow-{theme}.png")
    # Name: a wide version for computers and a narrow one for phones, so the text stays readable.
    html.append(
        '<p align="center"><picture>'
        f'<source media="(min-width: 1012px) and (prefers-color-scheme: dark)" srcset="assets/folio/name-dark.png" width="{size[0]}" height="{size[1]}" />'
        f'<source media="(min-width: 1012px)" srcset="assets/folio/name-light.png" width="{size[0]}" height="{size[1]}" />'
        '<source media="(prefers-color-scheme: dark)" srcset="assets/folio/name-narrow-dark.png" />'
        f'<img src="assets/folio/name-narrow-light.png" alt="{escape(p["name"] + ". " + p["tagline"])}" width="{nsize[0]}" height="{nsize[1]}" />'
        "</picture></p>"
    )
    html.append(
        '<p align="center"><picture>'
        f'<source media="(min-width: 1012px) and (prefers-color-scheme: dark)" srcset="assets/folio/bio-wide-dark.png" width="{wide[0]}" height="{wide[1]}" />'
        f'<source media="(min-width: 1012px)" srcset="assets/folio/bio-wide-light.png" width="{wide[0]}" height="{wide[1]}" />'
        '<source media="(prefers-color-scheme: dark)" srcset="assets/folio/bio-narrow-dark.png" />'
        f'<img src="assets/folio/bio-narrow-light.png" alt="{escape(p["bio"])}" width="{narrow[0]}" height="{narrow[1]}" />'
        "</picture></p>"
    )
    for theme in THEMES:
        size = save(draw_divider(theme), f"divider-{theme}.png")
    html.append('<p align="center">' + themed("divider", "", size=size) + "</p>")
    html.append("")

    # Links as small icons (the icons already live in assets/icons).
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
                alt = f'{card["title"]}: {card["text"]}'
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
