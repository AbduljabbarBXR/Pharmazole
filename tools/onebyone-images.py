#!/usr/bin/env python3
"""One-by-one image fetch for products still lacking real photos.

Per product (in catalog order == user's list order):
  1. mydawa.com product page (real photos; rate-limited -> retried next pass)
  2. Wikimedia Commons (generics: aspirin, warfarin, amoxicillin, ...)
  3. pharmaduka API thumbnail ONLY if it is a real photo (not gray generic)

Verification: image must NOT be gray-generic (>=45% (230,232,234)-ish),
not our green placeholder bg, and >= 64 colors.
"""
import importlib.util, io, json, os, re, sys, time, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "public" / "images" / "products"
CM_API = "https://commons.wikimedia.org/w/api.php"

_spec = importlib.util.spec_from_file_location("fi", ROOT / "tools" / "fetch-images.py")
fi = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fi)
_spec2 = importlib.util.spec_from_file_location("mi", ROOT / "tools" / "mydawa-images.py")
mi = importlib.util.module_from_spec(_spec2); _spec2.loader.exec_module(mi)

WM_BAD = {"structure", "skeletal", "formula", "molecular", "molecule", "chemical",
          "diagram", "reaction", "svg", "synthesis", "ecg", "x-ray", "microscop",
          "histopath", "patent", "cartoon", "logo"}
FORMS = {"tablets", "tablet", "capsules", "capsule", "syrup", "suspension", "ointment",
         "spray", "inhaler", "gel", "cream", "drops", "solution", "injection", "vial",
         "medicine", "box", "blister", "pack", "pill", "bottle"}
CONTEXT = FORMS | {"tbl", "tabs", "tab", "photo", "image", "pills"}


def wm_search2(query):
    params = {"action": "query", "format": "json", "generator": "search",
              "gsrsearch": query, "gsrnamespace": "6", "gsrlimit": "15",
              "prop": "imageinfo", "iiprop": "url|mime|size", "iiurlwidth": "800"}
    try:
        data = json.loads(fi.http_get(CM_API + "?" + urllib.parse.urlencode(params)))
    except Exception:
        return []
    out = []
    for pg in ((data.get("query") or {}).get("pages") or {}).values():
        ii = (pg.get("imageinfo") or [{}])[0]
        if ii.get("mime", "") != "image/jpeg":
            continue
        out.append({"title": pg.get("title", ""), "url": ii.get("thumburl") or ii.get("url")})
    return out


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


def wm_hunt(name):
    qtok, qtok_str = fi.tokens(name), fi.norm(name)
    drug = {t for t in fi.tokens(name) if re.fullmatch(r"[a-z]+", t) and len(t) >= 4}
    drug = drug - FORMS - {"n", "g", "s", "dispersible", "soluble", "extended", "release", "es"}
    if not drug:
        return None
    stems = sorted(drug, key=len, reverse=True)
    form = next((f for f in FORMS if f in re.sub(r"[^a-z]", " ", name.lower()).split()), "medicine")
    name_mgs = set(re.findall(r"(\d+(?:\.\d+)?)\s*(?:mg|mcg)", name.lower(), flags=re.I))
    best, bs = None, -1.0
    for stem in stems:
        found = False
        for q in (f"{stem} {form}", stem):
            for x in wm_search2(q):
                found = True
                t = x["title"].lower()
                if any(w in t for w in WM_BAD):
                    continue
                if stem not in t:
                    continue
                s = fi.score_match(qtok, qtok_str, x["title"], raw_name=name)
                title_mgs = set(re.findall(r"(\d+(?:\.\d+)?)\s*(?:mg|mcg)", t))
                if name_mgs and title_mgs:
                    if name_mgs.isdisjoint(title_mgs):
                        s -= 0.15
                    else:
                        s += 0.1
                if not any(w in t for w in CONTEXT):
                    s -= 0.2
                if s > bs:
                    best, bs = x, s
        if found:
            break
    if best is None or bs < 0.10:
        return None
    try:
        data = fi.http_get(best["url"], binary=True)
        if acceptable(data):
            return data
    except Exception:
        pass
    return None


def main():
    order = [x.strip() for x in open(ROOT / "tools" / "img-order.txt") if x.strip()]
    catalog = json.load(open(ROOT / "src" / "data" / "products.json"))["products"]
    by_name = {re.sub(r"[^a-z0-9]+", "", p["name"].lower()): p for p in catalog}
    targets = [by_name[re.sub(r"[^a-z0-9]+", "", n.lower())] for n in order]
    targets = [p for p in targets if p]
    print(f"targets: {len(targets)}", flush=True)
    stats = {"mydawa": 0, "wikimedia": 0, "pharmaduka": 0, "kept": 0, "failed": 0}

    for p in targets:
        slug, name = p["slug"], p["name"]
        path = IMG_DIR / f"{slug}.webp"
        if path.exists():
            try:
                if acceptable(path.read_bytes()):
                    stats["kept"] += 1
                    continue
            except Exception:
                pass
        try:
            done = False
            for c in (mi.slugify(name), "mydawa-" + mi.slugify(name)):
                mname, img = mi.probe_mydawa(c)
                if mname and img:
                    s = fi.score_match(fi.tokens(name), fi.norm(name), mname, raw_name=name)
                    qp, cp = fi.pack_num(name), fi.pack_num(mname)
                    if s >= 0.55 and (not qp or not cp or qp == cp):
                        try:
                            data = fi.http_get(img, binary=True)
                            if acceptable(data):
                                fi.save_image(data, slug)
                                stats["mydawa"] += 1
                                print(f"OK  {slug} <- mydawa [{mname[:28]}]", flush=True)
                                done = True
                                break
                        except Exception:
                            pass
                time.sleep(2.0)
            if done:
                continue

            data = wm_hunt(name)
            if data:
                fi.save_image(data, slug)
                stats["wikimedia"] += 1
                print(f"OK  {slug} <- wikimedia", flush=True)
                continue

            cands2 = fi.pa_search(fi.search_query(name, 3))
            best, best_s = fi.best_candidate(name, cands2)
            if best and best_s >= 0.62:
                url = (best.get("thumbnail") or (best.get("images") or [None])[0] or "")
                if url:
                    try:
                        data = fi.http_get(url + ("&" if "?" in url else "?") + "format=webp", binary=True)
                        if acceptable(data):
                            fi.save_image(data, slug)
                            stats["pharmaduka"] += 1
                            print(f"OK  {slug} <- pharmaduka [{best.get('name')[:28]}]", flush=True)
                            continue
                    except Exception:
                        pass
            time.sleep(2)
            stats["failed"] += 1
            print(f"FAIL {slug} | {name}", flush=True)
        except Exception as e:
            stats["failed"] += 1
            print(f"ERR {slug} | {name} | {e!r}", flush=True)

    print("DONE:", dict(stats), flush=True)


if __name__ == "__main__":
    main()
