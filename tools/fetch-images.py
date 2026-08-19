#!/usr/bin/env python3
"""Fetch accurate product images for the Pharmazole catalog.

Sources (in order):
  1. Pharmaduka API (Kenyan pharmacy) - search by name, best fuzzy match
  2. Wikimedia Commons - search by product name
  3. Keep existing photo if it is a real image (not a placeholder)
  4. Generated placeholder with the product name

Outputs: public/images/products/{slug}.webp (400x400, webp q82)
"""
import json, os, re, sys, time, urllib.parse, urllib.request, io, socket
from pathlib import Path
from PIL import Image
try:
    import pillow_avif
except ImportError:
    print("WARNING: pillow-avif-plugin not installed; AVIF downloads will fail", file=sys.stderr)

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "public" / "images" / "products"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
PA_API = "https://api.pharmaduka.com/api/v1/products"
CM_API = "https://commons.wikimedia.org/w/api.php"
socket.setdefaulttimeout(25)

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def tokens(s):
    return set(norm(s).split())

def strength_nums(s):
    return {round(float(a), 2) for a, b in re.findall(r"(\d+(?:\.\d+)?)\s*(mg|ml|g|mcg|iu)\b", (s or ""), re.I)}

def score_match(qtokens, qtok_str, cand_name, cand_strength="", cand_pack="", cand_brand="", raw_name=""):
    ct = tokens(cand_name)
    if not qtokens or not ct:
        return 0.0
    inter = qtokens & ct
    jac = len(inter) / len(qtokens | ct) if (qtokens | ct) else 0.0
    cover = len(inter) / len(qtokens)
    s = 0.35 * jac + 0.55 * cover
    qnums = {(a.lower(), b.lower()) for a, b in
             re.findall(r"(\d+(?:\.\d+)?)\s*(mg|ml|g|mcg|iu|i\.u\.|units|doses|s|'s)", qtok_str)}
    cnums = {(a.lower(), b.lower()) for a, b in
             re.findall(r"(\d+(?:\.\d+)?)\s*(mg|ml|g|mcg|iu|i\.u\.|units|doses|s|'s)",
                        (cand_strength or "") + " " + (cand_pack or ""))}
    STRENGTH_UNITS = {"mg", "ml", "g", "mcg", "iu", "i.u.", "units"}
    qstr = strength_nums(raw_name)
    cstr = strength_nums(cand_strength)
    if qstr and cstr and not (qstr & cstr):
        return 0.0
    if qnums and cnums and (qnums & cnums):
        s += 0.25
    qp, cp = pack_num(qtok_str), pack_num(cand_pack or "")
    if qp and cp:
        if qp == cp:
            s += 0.15
        else:
            return 0.0
    if isinstance(cand_brand, str) and cand_brand and norm(cand_brand) in qtok_str:
        s += 0.10
    return min(1.0, max(0.0, s))

def pack_num(s):
    m = re.findall(r"(\d+(?:\.\d+)?)\s*('?s|tabs?|tablets?|caps?|caplets?|pcs|pieces|sachets?|packs?|units?|doses?|ml|g)\b", (s or ""), re.I)
    return m[-1][0] if m else None

def best_candidate(name, cands):
    qtok, qtok_str = tokens(name), norm(name)
    best, best_s = None, 0.0
    for c in cands:
        s = score_match(qtok, qtok_str, c.get("name", ""), c.get("strength", ""),
                        c.get("packSize", ""), c.get("brand", ""), raw_name=name)
        if s > best_s:
            best, best_s = c, s
    return best, best_s

def search_query(name, n=3):
    t = norm(name).split()
    return " ".join(t[:n]) or name

def http_get(url, headers=None, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req) as r:
        data = r.read()
    if binary:
        return data
    return data.decode("utf-8", "replace")

def pa_search(query):
    url = PA_API + "?" + urllib.parse.urlencode({"search": query})
    for attempt in range(4):
        try:
            data = http_get(url)
            return (json.loads(data).get("data") or [])
        except Exception:
            time.sleep(2 + attempt * 3)
    return []

def wm_search(query):
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": "6",
        "gsrlimit": "12", "prop": "imageinfo",
        "iiprop": "url|mime|size", "iiurlwidth": "800",
    }
    try:
        data = json.loads(http_get(CM_API + "?" + urllib.parse.urlencode(params)))
    except Exception:
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for pg in pages.values():
        ii = (pg.get("imageinfo") or [{}])[0]
        mime = ii.get("mime", "")
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            continue
        out.append({
            "title": pg.get("title", ""),
            "url": ii.get("thumburl") or ii.get("url"),
            "w": ii.get("thumbwidth") or ii.get("width") or 0,
            "h": ii.get("thumbheight") or ii.get("height") or 0,
            "mime": mime,
        })
    return out

def save_image(data, slug):
    out = IMG_DIR / f"{slug}.webp"
    img = Image.open(io.BytesIO(data)).convert("RGB")
    scale = min(1.0, 400 / max(img.size))
    if scale < 1.0:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (400, 400), "#ffffff")
    canvas.paste(img, ((400 - img.width) // 2, (400 - img.height) // 2))
    canvas.save(out, "WEBP", quality=82)
    return out

def is_real_bytes(data, min_colors=64):
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if min(im.size) < 64:
            return False
        return len(im.getcolors(maxcolors=1 << 24) or []) >= min_colors
    except Exception:
        return False

def is_real_image(path):
    try:
        if os.path.getsize(path) < 2000:
            return False
        im = Image.open(path).convert("RGB")
        ncolors = len(im.getcolors(maxcolors=1 << 24) or [])
        if ncolors < 64:
            return False
        px = im.getdata()
        total = max(1, im.width * im.height)
        bg = sum(1 for p in px if p == (230, 245, 238))
        if bg / total > 0.5:
            return False
        return True
    except Exception:
        return False

def placeholder_image(slug, name):
    try:
        from PIL import ImageDraw, ImageFont
    except ImportError:
        pass
    img = Image.new("RGB", (400, 400), "#e6f5ee")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 399, 399], outline="#0b7a4b", width=3)
    d.line([(200, 130), (200, 270)], fill="#0b7a4b", width=14)
    d.line([(130, 200), (270, 200)], fill="#0b7a4b", width=14)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    label = (name[:26] + "\u2026") if len(name) > 26 else name
    d.text((200, 310), label, fill="#075c38", font=font, anchor="mm")
    return img

def main():
    catalog = json.load(open(ROOT / "src" / "data" / "products.json"))
    products = catalog["products"]
    print(f"products: {len(products)}", flush=True)
    stats = {"pharmaduka": 0, "wikimedia": 0, "kept": 0, "placeholder": 0, "fail": 0}
    report = []
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    for i, p in enumerate(products):
        slug, name = p["slug"], p["name"]
        path = IMG_DIR / f"{slug}.webp"
        qtok, qtok_str = tokens(name), norm(name)
        source = None

        if path.exists() and is_real_image(path):
            source = "kept"
            stats["kept"] += 1
            report.append({"slug": slug, "source": source, "name": name})
            continue

        # 1) Pharmaduka (retry with fewer tokens until results found)
        cands, best, best_s = [], None, 0.0
        for n in (3, 2, 1):
            cands = pa_search(search_query(name, n))
            best, best_s = best_candidate(name, cands)
            if cands:
                break
            time.sleep(0.2)
        if best and best_s >= 0.62:
            img_url = (best.get("thumbnail") or (best.get("images") or [None])[0] or "")
            if img_url:
                try:
                    data = http_get(img_url + ("&" if "?" in img_url else "?") + "format=webp", binary=True)
                    if is_real_bytes(data, min_colors=16):
                        save_image(data, slug)
                        source = "pharmaduka"
                        stats["pharmaduka"] += 1
                except Exception:
                    pass
        time.sleep(0.3)

        # 2) Wikimedia Commons
        if not source:
            search_q = re.sub(r"\b((\d+['s]?s?)|(ml|mg|g|mcg|iu|doses?|tabs?|tablets?|caps?|sachets?|pcs?|units?|pack(s)?))\b", " ", qtok_str, flags=re.I)
            search_q = re.sub(r"\s{2,}", " ", search_q).strip()
            cands = wm_search(search_q or qtok_str)
            best, best_s = None, 0.0
            for c in cands:
                s = score_match(qtok, qtok_str, c["title"], raw_name=name)
                if s > best_s:
                    best, best_s = c, s
            if best and best_s >= 0.30:
                try:
                    data = http_get(best["url"], binary=True)
                    if is_real_bytes(data):
                        save_image(data, slug)
                        source = "wikimedia"
                        stats["wikimedia"] += 1
                except Exception:
                    pass
            time.sleep(0.35)

        # 4) placeholder
        if not source:
            source = "placeholder"
            stats["placeholder"] += 1
            placeholder_image(slug, name).save(path, "WEBP", quality=82)

        report.append({"slug": slug, "source": source, "name": name})
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(products)}  {dict(stats)}", flush=True)

    json.dump(report, open("/tmp/opencode/img-sources.json", "w"), indent=1)
    print("DONE:", dict(stats), flush=True)

if __name__ == "__main__":
    main()
