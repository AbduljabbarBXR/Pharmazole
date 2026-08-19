#!/usr/bin/env python3
"""Fetch real product images from mydawa.com product pages.

For each product: derive mydawa slug from the name, probe
https://mydawa.com/products/{slug}, verify the JSON-LD name against ours,
download the image, and save as 400x400 WEBP.

Fallbacks per product: mydawa slug variants -> pharmaduka API -> wikimedia.
"""
import json, os, re, sys, time, urllib.parse, urllib.request, io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "public" / "images" / "products"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

import importlib.util
_spec = importlib.util.spec_from_file_location("fi", ROOT / "tools" / "fetch-images.py")
fi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fi)


def slugify(name):
    s = name.lower()
    s = s.replace("'", "").replace(".", "").replace("/", "").replace("(", "").replace(")", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def probe_mydawa(slug):
    url = f"https://mydawa.com/products/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception:
        return None, None
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("@type") == "Product":
            im = d.get("image")
            if isinstance(im, list):
                im = im[0] if im else None
            return d.get("name"), im
    return None, None


def main():
    catalog = json.load(open(ROOT / "src" / "data" / "products.json"))
    products = catalog["products"]
    targets = [p for p in products
               if not (IMG_DIR / f"{p['slug']}.webp").exists() or not fi.is_real_image(IMG_DIR / f"{p['slug']}.webp")]
    print(f"targets: {len(targets)}", flush=True)
    stats = {"mydawa": 0, "pharmaduka": 0, "wikimedia": 0, "failed": 0}
    report = []
    PACK_WORDS = {"s", "tabs", "tablets", "caps", "capsules", "susp", "suspension",
                  "syrup", "inhaler", "doses", "vial", "cartridges", "ml", "g"}

    for i, p in enumerate(targets):
        slug, name = p["slug"], p["name"]
        path = IMG_DIR / f"{slug}.webp"
        source = None

        # 1) mydawa slug probes
        base = slugify(name)
        cands = [base, "mydawa-" + base, slug, base.replace("-120-doses", "-120doses"), base.replace("-5-s", "-5s")]
        seen = set()
        for c in cands:
            if c in seen:
                continue
            seen.add(c)
            mname, img = probe_mydawa(c)
            if not mname:
                continue
            qtok, qtok_str = fi.tokens(name), fi.norm(name)
            s = fi.score_match(qtok, qtok_str, mname, raw_name=name)
            qp, cp = fi.pack_num(name), fi.pack_num(mname)
            if qp and cp and qp != cp:
                continue
            if s >= 0.55 and img:
                try:
                    data = fi.http_get(img, binary=True)
                    if fi.is_real_bytes(data, min_colors=16):
                        fi.save_image(data, slug)
                        source = "mydawa"
                        stats["mydawa"] += 1
                        break
                except Exception:
                    pass
            time.sleep(0.25)

        # 2) pharmaduka
        if not source:
            cands2, best, best_s = [], None, 0.0
            for n in (3, 2, 1):
                cands2 = fi.pa_search(fi.search_query(name, n))
                best, best_s = fi.best_candidate(name, cands2)
                if cands2:
                    break
                time.sleep(0.2)
            if best and best_s >= 0.62:
                img_url = (best.get("thumbnail") or (best.get("images") or [None])[0] or "")
                if img_url:
                    try:
                        data = fi.http_get(img_url + ("&" if "?" in img_url else "?") + "format=webp", binary=True)
                        if fi.is_real_bytes(data, min_colors=16):
                            fi.save_image(data, slug)
                            source = "pharmaduka"
                            stats["pharmaduka"] += 1
                    except Exception:
                        pass
            time.sleep(0.3)

        # 3) wikimedia
        if not source:
            search_q = re.sub(r"\b((\d+['s]?s?)|(ml|mg|g|mcg|iu|doses?|tabs?|tablets?|caps?|sachets?|pcs?|units?|pack(s)?))\b", " ", qtok_str, flags=re.I)
            search_q = re.sub(r"\s{2,}", " ", search_q).strip()
            wm = fi.wm_search(search_q or qtok_str)
            best, best_s = None, 0.0
            for c in wm:
                s = fi.score_match(qtok, qtok_str, c["title"], raw_name=name)
                if s > best_s:
                    best, best_s = c, s
            if best and best_s >= 0.30:
                try:
                    data = fi.http_get(best["url"], binary=True)
                    if fi.is_real_bytes(data):
                        fi.save_image(data, slug)
                        source = "wikimedia"
                        stats["wikimedia"] += 1
                except Exception:
                    pass
            time.sleep(0.35)

        if not source:
            stats["failed"] += 1
            print(f"  FAIL {slug} | {name}", flush=True)
        report.append({"slug": slug, "source": source or "placeholder", "name": name})
        if (i + 1) % 15 == 0:
            print(f"  {i + 1}/{len(targets)} {dict(stats)}", flush=True)

    json.dump(report, open("/tmp/opencode/mydawa-report.json", "w"), indent=1)
    print("DONE:", dict(stats), flush=True)


if __name__ == "__main__":
    main()
