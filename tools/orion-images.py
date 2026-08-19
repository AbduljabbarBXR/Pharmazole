#!/usr/bin/env python3
"""Fetch real product photos from orionpharmacy.co.ke for matched catalog items."""
import importlib.util, io, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "public" / "images" / "products"

_spec = importlib.util.spec_from_file_location("fi", ROOT / "tools" / "fetch-images.py")
fi = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fi)

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"}


def page_data(url):
    import urllib.request
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def extract(html):
    og = re.search(r'og:image"\s+content="([^"]+)"', html)
    name = None
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if m:
        name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    imgs = re.findall(r'wp-content/uploads/[^"\'\\]+\.(?:jpg|jpeg|png|webp)', html)
    return og and og.group(1), name, imgs


def is_gray_generic(data):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        px = im.getdata()
        total = max(1, im.width * im.height)
        gray = sum(1 for (r, g, b) in px
                   if abs(r - 231) <= 8 and abs(g - 232) <= 8 and abs(b - 234) <= 8)
        return gray / total >= 0.45
    except Exception:
        return True


def acceptable(data):
    return bool(fi.is_real_bytes(data, min_colors=64)) and not is_gray_generic(data)


def main():
    matches = json.load(open("/tmp/opencode/orion-match.json"))
    stats = {"ok": 0, "skip": 0, "fail": 0}
    for m in matches:
        slug, name, url = m["cat"], m["name"], m["url"]
        path = IMG_DIR / f"{slug}.webp"
        if path.exists():
            try:
                if acceptable(path.read_bytes()):
                    stats["skip"] += 1
                    continue
            except Exception:
                pass
        try:
            html = page_data(url).decode("utf-8", "replace")
            img, page_name, imgs = extract(html)
            if not img:
                stats["fail"] += 1
                print(f"FAIL {slug} no og:image", flush=True)
                time.sleep(1.5)
                continue
            if not img.startswith("http"):
                img = "https://orionpharmacy.co.ke" + img
            if page_name:
                s = fi.score_match(fi.tokens(name), fi.norm(name), page_name, raw_name=name)
                qp, cp = fi.pack_num(name), fi.pack_num(page_name)
                ok = s >= 0.55 and (not qp or not cp or qp == cp)
                if not ok:
                    print(f"NAME-MISMATCH {slug} | '{page_name}' score={s:.2f}", flush=True)
                    time.sleep(1.5)
                    continue
            data = fi.http_get(img, binary=True)
            if acceptable(data):
                fi.save_image(data, slug)
                stats["ok"] += 1
                print(f"OK  {slug} <- orion [{page_name or ''}]", flush=True)
            else:
                stats["fail"] += 1
                print(f"REJECT {slug} | bad image ({len(data)}B)", flush=True)
        except Exception as e:
            stats["fail"] += 1
            print(f"ERR  {slug} | {e!r}", flush=True)
        time.sleep(1.5)
    print("DONE:", dict(stats), flush=True)


if __name__ == "__main__":
    main()
