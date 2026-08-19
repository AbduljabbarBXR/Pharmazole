#!/usr/bin/env python3
"""Generate Pharmazole logo PNGs (512/192/favicon 64) with PIL — no browser needed."""
import os
from PIL import Image, ImageDraw, ImageFont

GREEN = (11, 122, 75, 255)
GREEN_DARK = (7, 92, 56, 255)
TEAL = (18, 140, 126, 255)
WHITE = (255, 255, 255, 255)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public')
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def rounded_bg(size, radius_frac=0.18):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * radius_frac)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=GREEN)
    # subtle diagonal highlight
    grad = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        col = tuple(int(GREEN[i] + (TEAL[i] - GREEN[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, y), (size, y)], fill=col)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def draw_cross(d, c, s, size):
    """White rounded medical cross centred at (cx,cy), half-width s."""
    cx, cy = int(c[0]), int(c[1])
    t = int(s * 2 * 0.34)
    s = int(s)
    d.rounded_rectangle([cx - t / 2, cy - s, cx + t / 2, cy + s], radius=int(t / 2), fill=WHITE)
    d.rounded_rectangle([cx - s, cy - t / 2, cx + s, cy + t / 2], radius=int(t / 2), fill=WHITE)
    d.rectangle([cx - t / 2, cy - t / 2, cx + t / 2, cy + t / 2], fill=WHITE)


def draw_pill(img, x, y, w, h, angle=0):
    """White capsule rotated `angle` degrees around its centre, pasted onto img."""
    tmp = Image.new('RGBA', (int(w * 2), int(h * 2)), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    td.rounded_rectangle([int(tmp.width / 2 - w / 2), int(tmp.height / 2 - h / 2),
                          int(tmp.width / 2 + w / 2), int(tmp.height / 2 + h / 2)],
                         radius=int(h / 2), fill=WHITE)
    tmp = tmp.rotate(angle, resample=Image.BICUBIC)
    img.paste(tmp, (int(x - tmp.width / 2), int(y - tmp.height / 2)), tmp)


def make(size, with_text):
    img = rounded_bg(size)
    d = ImageDraw.Draw(img)
    icon_area = size * (0.52 if with_text else 0.72)
    cx = size / 2
    cy = size * (0.38 if with_text else 0.50)
    draw_cross(d, (cx, cy), icon_area * 0.19, size)
    draw_pill(img, cx, cy, icon_area * 0.36, icon_area * 0.15, angle=-30)
    if with_text:
        f = ImageFont.truetype(FONT, int(size * 0.115))
        text = 'Pharmazole'
        w = d.textlength(text, font=f)
        d.text((cx - w / 2, size * 0.74), text, font=f, fill=WHITE)
    bg = Image.new('RGB', (size, size), (255, 255, 255))
    bg.paste(img, (0, 0), img)
    return bg


os.makedirs(OUT, exist_ok=True)
make(512, with_text=True).save(os.path.join(OUT, 'logo.png'))
make(192, with_text=False).save(os.path.join(OUT, 'logo-192.png'))
make(512, with_text=False).save(os.path.join(OUT, 'logo-512.png'))
make(64, with_text=False).save(os.path.join(OUT, 'favicon.png'))
print('written:', sorted(f for f in os.listdir(OUT) if f.startswith(('logo', 'favicon'))))
