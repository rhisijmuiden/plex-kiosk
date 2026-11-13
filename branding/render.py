#!/usr/bin/env python3
"""Renders the brand PNGs and the Plymouth splash assets from the SVG sources.
Requires: pip install cairosvg pillow"""
from pathlib import Path
import cairosvg
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
PNG = HERE / "png"; PNG.mkdir(exist_ok=True)
PLY = HERE / "plymouth"; PLY.mkdir(exist_ok=True)

for size in (32, 64, 128, 256, 512):
    cairosvg.svg2png(url=str(HERE / "logo-mark.svg"), write_to=str(PNG / f"mark-{size}.png"),
                     output_width=size, output_height=size)
cairosvg.svg2png(url=str(HERE / "logo.svg"), write_to=str(PNG / "logo-840.png"), output_width=840)

# Plymouth: mark at 192px, progress bar track + fill (scaled by the script)
cairosvg.svg2png(url=str(HERE / "logo-mark.svg"), write_to=str(PLY / "mark.png"),
                 output_width=192, output_height=192)

def pill(path, colour, w=320, h=6):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=colour)
    img.save(path)

pill(PLY / "track.png", (42, 49, 64, 255))
pill(PLY / "fill.png", (245, 165, 36, 255))
print("rendered")
