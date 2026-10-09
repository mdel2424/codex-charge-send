#!/usr/bin/env python3
# Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
"""Render the illustrated README demo; no terminal or model request is made.

Regenerate with: python3 scripts/render-readme-demo.py
Requires Pillow and DejaVu fonts (Ubuntu: fonts-dejavu-core).
These are optional documentation tools, unrelated to building ChargeSend.
"""

from pathlib import Path
import argparse

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, SCALE = 1080, 560, 2
FRAME_MS, HOLD_MS, TOTAL_MS = 50, 5200, 8600
EFFORTS = ("Low", "Medium", "High", "Extra High", "Max")
BACKGROUND = "#090f1b"
TERMINAL = "#101827"
COMPOSER = "#182336"
TEXT = "#eef3fa"
MUTED = "#95a5bd"
FAINT = "#61738e"
BORDER = "#2c3b52"


def snapshot(elapsed_ms):
    """Illustrate controller.rs with five offered tiers and an Extra High start."""
    half, start, maximum = 2000, 3, len(EFFORTS) - 1
    if elapsed_ms < half:
        rise = 0 if elapsed_ms <= 150 else elapsed_ms
        position, descending = start * half + (maximum - start) * rise, False
    else:
        phase = (elapsed_ms - half) % (half * 2)
        descending = phase < half
        position = maximum * (half - phase if descending else phase - half)
    index = (position + half // 2) // half
    return EFFORTS[index], position * 1000 // (maximum * half), descending


def charge_color(position):
    """Match the green/yellow/red interpolation in chargesend/bar.rs."""
    if position <= 500:
        first, last, offset = (70, 200, 95), (240, 205, 70), position
    else:
        first, last, offset = (240, 205, 70), (235, 70, 65), position - 500
    # Rust integer division truncates toward zero, including negative channels.
    return tuple(a + int((b - a) * offset / 500) for a, b in zip(first, last))


def render(elapsed_ms, fonts):
    canvas = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BACKGROUND)
    draw = ImageDraw.Draw(canvas)

    def text(x, y, value, font="mono", fill=TEXT):
        draw.text((x * SCALE, y * SCALE), value, font=fonts[font], fill=fill)

    def rectangle(box, fill, outline=None, radius=0):
        draw.rounded_rectangle(
            tuple(value * SCALE for value in box), radius=radius * SCALE,
            fill=fill, outline=outline, width=SCALE,
        )

    held = elapsed_ms < HOLD_MS
    label, permille, descending = snapshot(min(elapsed_ms, HOLD_MS - FRAME_MS))
    accent = charge_color(permille)
    text(48, 25, "ChargeSend", "title")
    text(49, 82, "Hold Enter. Choose your effort. Release to send.", "subtitle", MUTED)

    rectangle((48, 128, 1032, 410), TERMINAL, BORDER, 14)
    text(72, 145, "kitty / chargesend", "small_mono", MUTED)
    text(805, 147, "UNOFFICIAL CODEX CLI", "tiny_mono", FAINT)
    draw.line((49 * SCALE, 181 * SCALE, 1031 * SCALE, 181 * SCALE), fill=BORDER, width=SCALE)

    if not held:
        text(76, 204, "› Trace this bug and propose a fix.", fill=TEXT)
        seconds = (elapsed_ms - HOLD_MS) // 1000
        text(76, 241, f"Working ({seconds}s • esc to interrupt) · {label} Reasoning", "status", MUTED)

    rectangle((70, 289, 1010, 337), COMPOSER, radius=6)
    text(84, 301, "›", fill=MUTED)
    text(114, 301, "Trace this bug and propose a fix." if held else "Ask Codex to do anything", fill=TEXT if held else FAINT)

    if held:
        x, y = 83, 356
        prefix = f"{label:<10} ["
        text(x, y, prefix, "bar", accent)
        step = fonts["bar"].getlength("=") / SCALE
        x += len(prefix) * step
        filled = permille * 12 // 1000
        for index in range(12):
            text(x, y, "=" if index < filled else "-", "bar",
                 charge_color(index * 1000 // 11) if index < filled else FAINT)
            x += step
        text(x, y, "]", "bar", accent)
        direction = "v" if descending else "^"
        text(x + step, y, f" {direction} · release Enter to send · Esc cancels", "bar", MUTED)
    else:
        text(83, 358, "? for shortcuts", "bar", FAINT)

    key_y = 443 if held else 439
    rectangle((49, 449, 187, 520), "#060b14", radius=10)
    rectangle((49, key_y, 187, key_y + 70), COMPOSER, accent if held else BORDER, 10)
    text(78, key_y + 10, "Enter", "key", TEXT)
    text(101 if held else 87, key_y + 44, "HELD" if held else "RELEASED", "tiny_mono", accent if held else MUTED)

    if not held:
        headline = f"Released. Sent with {label} reasoning."
        detail = "The Working line shows the effort used for this turn."
    elif elapsed_ms < 2000:
        headline = "Hold Enter to charge."
        detail = "Start at Extra High and rise to the highest offered tier."
    elif elapsed_ms < 4000:
        headline = "Keep holding. The bar comes back down."
        detail = "Each ascent or descent takes about two seconds."
    else:
        headline = "Release at the effort you want."
        detail = "The cycle repeats for as long as Enter is held."
    text(218, 439, headline, "instruction")
    text(219, 478, detail, "detail", MUTED)
    text(49, 538, "Illustrated demo · Kitty · Extra High start · Example model with Low–Max tiers", "note", FAINT)
    return canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=Path("/usr/share/fonts/truetype/dejavu"))
    parser.add_argument("--output", type=Path, default=ROOT / "assets/chargesend-demo.gif")
    args = parser.parse_args()
    sizes = {
        "title": ("DejaVuSans-Bold.ttf", 42),
        "subtitle": ("DejaVuSans.ttf", 20),
        "instruction": ("DejaVuSans-Bold.ttf", 25),
        "detail": ("DejaVuSans.ttf", 17),
        "note": ("DejaVuSans.ttf", 12),
        "mono": ("DejaVuSansMono.ttf", 20),
        "status": ("DejaVuSansMono.ttf", 19),
        "bar": ("DejaVuSansMono.ttf", 17),
        "small_mono": ("DejaVuSansMono.ttf", 14),
        "tiny_mono": ("DejaVuSansMono.ttf", 11),
        "key": ("DejaVuSansMono-Bold.ttf", 23),
    }
    fonts = {name: ImageFont.truetype(str(args.font_dir / filename), size * SCALE)
             for name, (filename, size) in sizes.items()}
    frames = [render(time, fonts) for time in range(0, TOTAL_MS, FRAME_MS)]

    # Share a palette to keep text and background colors steady across frames.
    samples = [frames[index] for index in [0, 20, 40, 60, 80, 100, 110, 140]]
    palette_sheet = Image.new("RGB", (WIDTH, HEIGHT * len(samples) + 100))
    for index, frame in enumerate(samples):
        palette_sheet.paste(frame, (0, index * HEIGHT))
    palette_draw = ImageDraw.Draw(palette_sheet)
    for x in range(WIDTH):
        palette_draw.line((x, HEIGHT * len(samples), x, palette_sheet.height), fill=charge_color(x * 1000 // (WIDTH - 1)))
    palette = palette_sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    animation = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    animation[0].save(args.output, save_all=True, append_images=animation[1:],
                      duration=FRAME_MS, loop=0, optimize=True, disposal=1)
    print(f"Rendered {args.output} ({WIDTH}×{HEIGHT}, {TOTAL_MS / 1000:g}s, {args.output.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
