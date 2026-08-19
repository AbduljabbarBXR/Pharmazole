#!/usr/bin/env python3
"""DailyMed hunter v2: real FDA pack photos, throttle-aware, with brand->generic synonyms."""
import importlib.util, io, json, re, sys, time, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "public" / "images" / "products"
DM = "https://dailymed.nlm.nih.gov/dailymed"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0"}

_spec = importlib.util.spec_from_file_location("fi", ROOT / "tools" / "fetch-images.py")
fi = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fi)

STOPS = {"tablets", "tablet", "capsules", "capsule", "syrup", "suspension", "ointment",
         "spray", "inhaler", "solution", "injection", "soluble", "dispersible",
         "extended", "release", "cartridges", "vial", "suppository", "doses", "nph",
         "retard", "respiration", "respirator", "evohaler", "solostar", "flexpen",
         "es", "ec", "sf", "ds", "hfa", "mdi", "forte", "pediatric", "sodium"}
SYN = {"septrin": "trimethoprim", "flagyl": "metronidazole", "augmentin": "amoxicillin",
       "co-amoxiclav": "amoxicillin", "lipitor": "atorvastatin", "mobic": "meloxicam",
       "arcoxia": "etoricoxib", "ponstan": "mefenamic", "voltaren": "diclofenac",
       "cardace": "ramipril", "lantus": "glargine", "novomix": "insulin aspart",
       "humulin": "insulin human", "actrapid": "insulin", "momate": "mometasone",
       "nasonex": "mometasone", "flusort": "fluticasone", "budecort": "budesonide",
       "foralin": "albuterol", "levolin": "levosalbutamol", "saltrol": "salbutamol",
       "asthalin": "albuterol", "aerovent": "ipratropium", "formonide": "formoterol",
       "fortide": "fluticasone", "azmasol": "albuterol", "combiwave": "fluticasone",
       "cortin": "fluticasone", "ryaltris": "olopatadine", "symbicort": "budesonide",
       "warfarin-warexx": "warfarin", "tetracycline-skin": "tetracycline",
       "penicillin": "penicillin v", "cefixime": "cefixime", "ibutop": "ibuprofen",
       "brozelin": "bromhexine", "solvin": "solvin"}


def get(url, tries=3):
    import urllib.request
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=40).read()
        except Exception:
            if i < tries - 1:
                time.sleep(20)
    raise RuntimeError("dailymed unreachable")


def dailymed_images(drug):
    html = get(DM + "/search.cfm?" + urllib.parse.urlencode({"query": drug})).decode("utf-8", "replace")
    setids = re.findall(r'href="(/dailymed/drugInfo\.cfm\?setid=([0-9a-f-]+))"', html)
    seen = set()
    for url, setid in setids:
        if setid in seen:
            continue
        seen.add(setid)
        page = get(DM + url).decode("utf-8", "replace")
        if len(page) < 60000 and "image.cfm" not in page:
            time.sleep(25)
            page = get(DM + url).decode("utf-8", "replace")
        title = re.search(r"<title>([^<]*)</title>", page)
        tt = (title and title.group(1)) or ""
        if drug.lower() not in tt.lower() and drug.lower() not in page[:30000].lower():
            continue
        imgs = re.findall(r'href="(/dailymed/image\.cfm\?name=image-\d+\.jpg[^"]*)"', page)
        if imgs:
            return url, [f"https://dailymed.nlm.nih.gov{d.replace('&amp;', '&')}" for d in imgs]
        time.sleep(1.2)
    return None, []


def is_gray(data):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        px = im.getdata()
        gray = sum(1 for (r, g, b) in px
                   if abs(r - 231) <= 8 and abs(g - 232) <= 8 and abs(b - 234) <= 8) / max(1, len(px))
        return gray >= 0.45
    except Exception:
        return True


def acceptable(data):
    return bool(fi.is_real_bytes(data, min_colors=64)) and not is_gray(data)


def drug_tokens(name):
    toks = {t for t in fi.tokens(name) if re.fullmatch(r"[a-z]+", t) and len(t) >= 4}
    toks -= STOPS
    return sorted(toks, key=len)


def hunt(name):
    toks = drug_tokens(name)
    for tok in toks:
        candidates = [tok]
        if tok in SYN:
            candidates.append(SYN[tok])
        for c in candidates:
            label, imgs = dailymed_images(c)
            if not imgs:
                time.sleep(1.2)
                continue
            for u in imgs[:6]:
                try:
                    data = get(u)
                except Exception:
                    time.sleep(20)
                    continue
                if acceptable(data):
                    return c, data
                time.sleep(0.8)
            return c, None
    return None, None


def main():
    targets = sys.argv[1:] or None
    catalog = {p["slug"]: p for p in json.load(open(ROOT / "src" / "data" / "products.json"))["products"]}
    slugs = targets or list(catalog)
    stats = {"ok": 0, "fail": 0}
    for slug in slugs:
        name = catalog[slug]["name"]
        path = IMG_DIR / f"{slug}.webp"
        if path.exists():
            try:
                if acceptable(path.read_bytes()):
                    stats["ok"] += 1
                    continue
            except Exception:
                pass
        tok, data = hunt(name)
        if data:
            fi.save_image(data, slug)
            stats["ok"] += 1
            print(f"OK  {slug} <- dailymed [{tok}]", flush=True)
        else:
            stats["fail"] += 1
            print(f"FAIL {slug} | {name} [{tok}]", flush=True)
        time.sleep(1.5)
    print("DONE:", dict(stats), flush=True)


if __name__ == "__main__":
    main()
