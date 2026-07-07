# ============================================================
#  message_card.py  —  Render a WhatsApp-style "Stock Bits"
#  card and export it as a portrait PDF.
#
#  The PDF page uses the same proportions as a WhatsApp chat
#  message bubble (~3:4 portrait, like the reference screenshot)
#  and is styled to look like an incoming dark-theme WhatsApp
#  message — but with OUR PureFrame branding/content.
#
#  Emojis render in full colour via Segoe UI Emoji (no headless
#  browser or RAQM needed). Text and emoji are drawn run-by-run
#  so each glyph uses the right font.
#
#  Usage (library):
#      from message_card import render_card_pdf
#      render_card_pdf(lines, "out.pdf")
#
#  Usage (CLI, renders the built-in Suzlon demo):
#      python message_card.py --out suzlon_card.pdf
#      python message_card.py --out card.pdf --time "09:43"
# ============================================================
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# ── Windows system fonts ─────────────────────────────────────
_FONT_DIR   = r"C:\Windows\Fonts"
FONT_REG    = os.path.join(_FONT_DIR, "segoeui.ttf")
FONT_BOLD   = os.path.join(_FONT_DIR, "segoeuib.ttf")
FONT_EMOJI  = os.path.join(_FONT_DIR, "seguiemj.ttf")

# Segoe UI Emoji is a bitmap-colour font that only ships specific
# pixel sizes; 109 px is the native strike Pillow must be asked for,
# then the glyph is scaled to the run's font size.
EMOJI_NATIVE_PX = 109

# ── WhatsApp dark-theme palette ──────────────────────────────
COL_PAGE_BG   = (11, 20, 26)      # #0B141A  chat wallpaper base
COL_BUBBLE    = (32, 44, 51)      # #202C33  incoming bubble
COL_TEXT      = (233, 237, 239)   # #E9EDEF  primary text
COL_BOLD      = (255, 255, 255)   # bold headline
COL_LINK      = (83, 189, 235)    # #53BDEB  link blue
COL_META      = (134, 150, 160)   # #8696A0  timestamp / footer

# ── Card geometry (rendered at high res, scaled down by PDF DPI) ──
CARD_W        = 900               # bubble width  in px
ASPECT        = 4 / 3             # height : width  → 3:4 portrait
PAGE_PAD      = 34                # gap between bubble and page edge
BUBBLE_PAD_X  = 44                # inner horizontal padding
BUBBLE_PAD_TOP= 40
BUBBLE_PAD_BOT= 30
CORNER        = 26                # bubble corner radius
LINE_GAP      = 14                # extra space between wrapped lines
PARA_GAP      = 10                # extra space for a blank source line

# Font sizes (px)
SZ_HEAD   = 40
SZ_BODY   = 33
SZ_META   = 26


# ─────────────────────────────────────────────────────────────
#  Emoji detection & clustering
# ─────────────────────────────────────────────────────────────
def _is_emoji_cp(cp: int) -> bool:
    """True if a codepoint is (part of) an emoji we render with the colour font."""
    return (
        0x1F300 <= cp <= 0x1FAFF or   # symbols & pictographs, supplemental, etc.
        0x1F000 <= cp <= 0x1F0FF or   # mahjong / dominoes / cards
        0x2600  <= cp <= 0x27BF  or   # misc symbols + dingbats (⚡ ✅ ➡ …)
        0x2B00  <= cp <= 0x2BFF  or   # stars, arrows (⭐ ⬆ …)
        0x2190  <= cp <= 0x21FF  or   # arrows
        cp in (0x203C, 0x2049, 0x2122, 0x2139) or
        0x1F1E6 <= cp <= 0x1F1FF      # regional indicators (flags)
    )


# Codepoints that GLUE onto the preceding emoji to form one cluster.
_EMOJI_JOINERS = {
    0xFE0F,   # variation selector-16 (emoji presentation)
    0xFE0E,   # variation selector-15 (text presentation)
    0x200D,   # zero-width joiner
    0x20E3,   # combining enclosing keycap
}


def _segment(text: str):
    """
    Split a string into ordered runs: ('text', str) | ('emoji', str).
    Consecutive emoji codepoints (with their joiners / variation selectors)
    are grouped so multi-codepoint emoji render as a single glyph.
    """
    runs = []
    buf = ""
    mode = None  # 'text' | 'emoji'

    def flush():
        nonlocal buf, mode
        if buf:
            runs.append((mode, buf))
        buf = ""

    for ch in text:
        cp = ord(ch)
        if cp in _EMOJI_JOINERS:
            # attach to whatever run we're in (keeps clusters intact)
            buf += ch
            continue
        is_e = _is_emoji_cp(cp)
        new_mode = "emoji" if is_e else "text"
        if new_mode != mode:
            flush()
            mode = new_mode
        buf += ch
    flush()
    return runs


# ─────────────────────────────────────────────────────────────
#  Font cache
# ─────────────────────────────────────────────────────────────
_font_cache: dict = {}


def _font(path: str, size: int):
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


def _emoji_font(size: int):
    # Colour bitmap font: always load the native strike, scale on draw.
    key = ("__emoji__", EMOJI_NATIVE_PX)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_EMOJI, EMOJI_NATIVE_PX)
    return _font_cache[key]


# ─────────────────────────────────────────────────────────────
#  A "styled token" is one run with a resolved font role & colour.
#  We build a flat list of tokens per source line, wrap them to
#  the bubble width, then paint.
# ─────────────────────────────────────────────────────────────
class Tok:
    __slots__ = ("kind", "text", "bold", "color", "size")

    def __init__(self, kind, text, bold, color, size):
        self.kind = kind      # 'text' | 'emoji'
        self.text = text
        self.bold = bold
        self.color = color
        self.size = size


def _is_link_word(word: str) -> bool:
    """A single whitespace-delimited word that should render in link blue."""
    low = word.strip().strip(".,").lower()
    return (
        low.startswith("http://")
        or low.startswith("https://")
        or low.startswith("www.")
        or "pureframe.ai" in low
    )


def _tokens_for_line(line: str, size: int, base_color, force_bold=False):
    """
    Turn one logical line into styled tokens.
    Supports *bold* spans (WhatsApp markdown) and auto-blue links.
    Link colouring is applied per WORD, so a URL inside a sentence turns
    blue while the surrounding text keeps `base_color`.
    """
    tokens = []
    # split on *bold* markers, keeping bold state
    parts = []
    bold = force_bold
    seg = ""
    for ch in line:
        if ch == "*":
            if seg:
                parts.append((seg, bold))
                seg = ""
            bold = not bold
            continue
        seg += ch
    if seg:
        parts.append((seg, bold))

    for txt, is_bold in parts:
        # re-split each part on spaces so link colour is decided word-by-word,
        # while preserving the spaces as their own tokens.
        pieces = txt.split(" ")
        for i, word in enumerate(pieces):
            if word:
                color = COL_LINK if _is_link_word(word) else base_color
                for kind, run in _segment(word):
                    tokens.append(Tok(kind, run, is_bold, color, size))
            if i < len(pieces) - 1:
                tokens.append(Tok("space", " ", is_bold, base_color, size))
    return tokens


def _measure(draw, tok: Tok) -> float:
    if tok.kind == "emoji":
        ef = _emoji_font(tok.size)
        scale = tok.size / EMOJI_NATIVE_PX
        return draw.textlength(tok.text, font=ef, embedded_color=True) * scale
    f = _font(FONT_BOLD if tok.bold else FONT_REG, tok.size)
    return draw.textlength(tok.text, font=f)


def _space_w(draw, size, bold=False) -> float:
    return draw.textlength(" ", font=_font(FONT_BOLD if bold else FONT_REG, size))


def _wrap(draw, tokens, max_w):
    """Greedy word-wrap a token stream into lines of tokens (word-aware)."""
    lines = [[]]
    x = 0.0

    # Break text tokens into word-tokens so wrapping happens on spaces.
    expanded = []
    for t in tokens:
        if t.kind == "text" and " " in t.text:
            words = t.text.split(" ")
            for i, w in enumerate(words):
                if w:
                    expanded.append(Tok("text", w, t.bold, t.color, t.size))
                if i < len(words) - 1:
                    expanded.append(Tok("space", " ", t.bold, t.color, t.size))
        else:
            expanded.append(t)

    for t in expanded:
        w = _space_w(draw, t.size, t.bold) if t.kind == "space" else _measure(draw, t)
        if t.kind == "space":
            if x == 0:            # no leading space on a fresh line
                continue
            lines[-1].append(t)
            x += w
            continue
        if x + w > max_w and lines[-1]:
            # drop a trailing space before wrapping
            if lines[-1] and lines[-1][-1].kind == "space":
                lines[-1].pop()
            lines.append([])
            x = 0.0
        lines[-1].append(t)
        x += w
    return lines


def _line_height(size: int) -> int:
    return int(size * 1.34)


# ─────────────────────────────────────────────────────────────
#  Painting
# ─────────────────────────────────────────────────────────────
def _paint_line(base_img, draw, tokens, x0, y, line_h):
    for t in tokens:
        if t.kind == "space":
            x0 += _space_w(draw, t.size, t.bold)
            continue
        if t.kind == "emoji":
            size = t.size
            ef = _emoji_font(size)
            scale = size / EMOJI_NATIVE_PX
            adv = draw.textlength(t.text, font=ef, embedded_color=True) * scale
            # Render emoji on its own RGBA layer at native size, scale down, paste.
            native_w = max(1, int(draw.textlength(t.text, font=ef, embedded_color=True)))
            layer = Image.new("RGBA", (native_w + 8, EMOJI_NATIVE_PX + 40), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            ld.text((0, 0), t.text, font=ef, embedded_color=True)
            new_w = max(1, int(layer.width * scale))
            new_h = max(1, int(layer.height * scale))
            layer = layer.resize((new_w, new_h), Image.LANCZOS)
            # vertical align emoji roughly to the text baseline
            y_off = int(y + (line_h - size) / 2 - size * 0.12)
            base_img.paste(layer, (int(x0), y_off), layer)
            x0 += adv
        else:
            f = _font(FONT_BOLD if t.bold else FONT_REG, t.size)
            draw.text((x0, y), t.text, font=f, fill=t.color)
            x0 += draw.textlength(t.text, font=f)
    return x0


# ─────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────
def render_card_image(lines, timestamp: str = "09:43") -> Image.Image:
    """
    Render the message lines into a WhatsApp-style card image.

    `lines` is a list of dicts or strings:
        {"text": "...", "size": SZ_BODY, "head": False}
    or a plain string (treated as body text). A blank string → paragraph gap.
    Returns a PIL RGB image sized to a >= 3:4 portrait ratio.
    """
    # scratch canvas just for measuring
    scratch = Image.new("RGB", (10, 10))
    md = ImageDraw.Draw(scratch)

    text_w = CARD_W - 2 * BUBBLE_PAD_X

    # 1) Build wrapped physical lines with their heights.
    physical = []   # list of (tokens, line_h) ; tokens == None → blank gap
    for item in lines:
        if isinstance(item, str):
            item = {"text": item}
        txt  = item.get("text", "")
        size = item.get("size", SZ_HEAD if item.get("head") else SZ_BODY)
        if txt == "":
            physical.append((None, PARA_GAP + SZ_BODY // 3))
            continue
        if item.get("head"):
            base_color = COL_BOLD
        elif item.get("muted"):
            base_color = COL_META
        else:
            base_color = COL_TEXT
        toks = _tokens_for_line(
            txt, size, base_color,
            force_bold=item.get("head", False),
        )
        for wl in _wrap(md, toks, text_w):
            physical.append((wl, _line_height(size)))

    content_h = sum(h for _, h in physical) + (len(physical) - 1) * 0 + LINE_GAP * 0
    # add per-line gaps
    content_h = sum(h for _, h in physical)

    bubble_inner_h = content_h + SZ_META + 18          # room for timestamp row
    bubble_h = bubble_inner_h + BUBBLE_PAD_TOP + BUBBLE_PAD_BOT

    # 2) Enforce >= 3:4 portrait ratio on the whole PAGE.
    page_w = CARD_W + 2 * PAGE_PAD
    min_page_h = int(page_w * ASPECT)
    page_h = max(min_page_h, bubble_h + 2 * PAGE_PAD)

    # If we had to grow the page, grow the bubble to keep it centred/filled.
    bubble_h = page_h - 2 * PAGE_PAD

    img = Image.new("RGB", (page_w, page_h), COL_PAGE_BG)
    draw = ImageDraw.Draw(img)

    # subtle wallpaper vignette (kept minimal & theme-consistent)
    bx0, by0 = PAGE_PAD, PAGE_PAD
    bx1, by1 = PAGE_PAD + CARD_W, PAGE_PAD + bubble_h
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=CORNER, fill=COL_BUBBLE)

    # 3) Paint content.
    x0 = bx0 + BUBBLE_PAD_X
    y = by0 + BUBBLE_PAD_TOP
    for toks, h in physical:
        if toks is None:
            y += h
            continue
        _paint_line(img, draw, toks, x0, y, h)
        y += h

    # 4) Timestamp bottom-right inside the bubble.
    ts_font = _font(FONT_REG, SZ_META)
    ts_w = draw.textlength(timestamp, font=ts_font)
    draw.text((bx1 - BUBBLE_PAD_X - ts_w, by1 - BUBBLE_PAD_BOT - SZ_META),
              timestamp, font=ts_font, fill=COL_META)

    return img


def render_card_pdf(lines, out_path: str, timestamp: str = "09:43", dpi: int = 300):
    """Render the card and save as a single-page PDF sized to a 3:4 portrait ratio."""
    img = render_card_image(lines, timestamp=timestamp)
    img.save(out_path, "PDF", resolution=dpi)
    return out_path


# Footer lines that should render small & muted (grey) like the reference.
_MUTED_STARTS = ("you are receiving", "disclaimer", "you can add or remove")


def lines_from_message(text: str):
    """
    Turn a formatted WhatsApp-style message (the kind output.py / the bot's AI
    caption produces) into card `lines`. The first non-empty line becomes the
    bold headline; footer/disclaimer lines render small & muted; blank lines
    become paragraph gaps. `*bold*` spans, emojis and URLs are handled by the
    renderer itself.
    """
    lines = []
    seen_content = False
    for raw in (text or "").splitlines():
        stripped = raw.strip()
        if stripped == "":
            # collapse leading blanks; keep interior/trailing gaps
            if seen_content:
                lines.append({"text": ""})
            continue
        low = stripped.lower().lstrip("* ")
        if not seen_content:
            lines.append({"text": stripped, "head": True})
            seen_content = True
        elif low.startswith(_MUTED_STARTS):
            lines.append({"text": stripped, "size": SZ_META, "muted": True})
        else:
            lines.append({"text": stripped})
    # drop a trailing blank gap so the timestamp doesn't float too low
    while lines and lines[-1].get("text") == "":
        lines.pop()
    return lines or [{"text": text or "NSE filing", "head": True}]


def render_message_pdf(text: str, out_path: str, timestamp: str = "09:43", dpi: int = 300):
    """Convenience: render a formatted message string straight to a card PDF."""
    return render_card_pdf(lines_from_message(text), out_path, timestamp=timestamp, dpi=dpi)


# ─────────────────────────────────────────────────────────────
#  Built-in demo content (PureFrame-branded version of the ref)
# ─────────────────────────────────────────────────────────────
def demo_lines():
    return [
        {"text": "📢 *PureFrame Stock Bits!!*", "head": True},
        {"text": ""},
        {"text": "🏢 Suzlon Energy Ltd"},
        {"text": ""},
        {"text": "⚡ Investor Conference Participation"},
        {"text": ""},
        {"text": ("🤖 Suzlon Energy representatives will attend an analysts and "
                  "investors conference organized by Maybank on July 7th and July "
                  "8th, 2026. The company confirmed that only the publicly available "
                  "Investor Relations presentation will be discussed, and no new "
                  "price-sensitive information will be shared. #LowImpact")},
        {"text": ""},
        {"text": "🔗 https://pureframe.ai/t/AjnN5Y"},
        {"text": ""},
        {"text": "You are receiving this stock update per your request on https://pureframe.ai",
         "size": SZ_META, "muted": True},
        {"text": "Disclaimer: https://pureframe.ai/t/fLVC1g", "size": SZ_META, "muted": True},
    ]


def main():
    ap = argparse.ArgumentParser(description="Render a WhatsApp-style Stock Bits card to PDF")
    ap.add_argument("--out", default="stock_bits_card.pdf", help="Output PDF path")
    ap.add_argument("--png", default=None, help="Also save a PNG preview to this path")
    ap.add_argument("--time", default="09:43", help="Timestamp shown in the bubble")
    ap.add_argument("--dpi", type=int, default=300, help="PDF resolution (controls physical size)")
    args = ap.parse_args()

    lines = demo_lines()
    img = render_card_image(lines, timestamp=args.time)
    img.save(args.out, "PDF", resolution=args.dpi)
    w_mm = img.width / args.dpi * 25.4
    h_mm = img.height / args.dpi * 25.4
    print(f"[OK] PDF -> {args.out}")
    print(f"     page: {img.width}x{img.height}px  "
          f"({w_mm:.0f}x{h_mm:.0f} mm @ {args.dpi} dpi)  "
          f"ratio {img.height / img.width:.3f}:1 (portrait)")
    if args.png:
        img.save(args.png, "PNG")
        print(f"[OK] PNG preview -> {args.png}")


if __name__ == "__main__":
    main()
