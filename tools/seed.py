#!/usr/bin/env python3
"""Seed the Pharmazole catalog from crawled online pharmacy data (12k+ products).

Price = crawled JSON-LD price x SALE_MULT (typical ~25% everyday discount),
so we match the real shelf price, then owner refines via admin.
"""
import json, os, re, sys, time, urllib.request, io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("PZ_RAW", "/tmp/opencode/catalog_full.json"))
IMG_DIR = ROOT / "public" / "images" / "products"
MAX_ITEMS = int(os.environ.get("PZ_MAX", "240"))
SALE_MULT = float(os.environ.get("PZ_MULT", "0.75"))

IMG_DIR.mkdir(parents=True, exist_ok=True)

DROP_CAT = {"snacks-and-drinks", "iv-therapy", "pata-tiba-na-thao", "offers", "new-on-mydawa",
            "wellness-check-ups", "vaccines", "dependence", "cancer-care"}
DROP_WORDS = ["foundation", "lip gloss", "make up", "mascara", "eyeshadow", "blush", "body mist",
              "parfum", "perfume", "cologne", "essential oil", "hair oil", "sex toy", "vibrator",
              "dildo", "cock", "ring", "condom cover", "wrestling"]

def sanitize(p):
    """Strip store names / placeholder brands out of a crawled product."""
    name = re.sub(r"(?i)^\s*(mydawa|goodlife|pharmaduka)\s+", "", p["name"] or "").strip()
    brand = (p.get("brand") or "").upper()
    if brand in {"MYDAWA", "GOODLIFE", "PHARMADUKA", "PHARMADUKA.COM"}:
        brand = ""
    desc = re.sub(r"(?i)\b(mydawa|goodlife|pharmaduka)\b", "", p.get("description") or "")
    desc = re.sub(r"(?i)order now from \w+ and we will deliver to your doorstep\.?\s*", "", desc)
    return name, brand, desc.strip()

DRUG_CATS = [
    (r"\b(coartem|artefan|artemether|lumefantrine|aluya|amodiaquine|falcidin|ardiam|quinate|anti-malaria|antimalaria|malar|duocotexin)\b", "Malaria"),
    (r"\b(amoxicillin|amoxiclav|augmentin|ampicillin|azithromycin|cefixime|cefuroxime|cephalexin|ciprofloxacin|cloxacillin|clindamycin|cotrimoxazole|septrin|doxycycline|erythromycin|flagyl|metronidazole|nitrofurantoin|ofloxacin|penicillin|tetracycline|bactrim|ceftriaxone|fusidic|macrodantin)\b", "Antibiotics"),
    (r"\b(amlodipine|losartan|lisinopril|enalapril|atenolol|bisoprolol|propranolol|carvedilol|nifedipine|valsartan|telmisartan|hydrochlorothiazide|cardace|blopress|azilsartan)\b", "Blood Pressure"),
    (r"\b(metformin|glibenclamide|gliclazide|glimepiride|glipizide|pioglitazone|insulin|lantus|novomix|actrapid|humulin|januvia|sitagliptin|empagliflozin|dapagliflozin)\b", "Diabetes"),
    (r"\b(atorvastatin|simvastatin|rosuvastatin|lipitor|ezetimibe|aspirin|clopidogrel|cardiprin|warfarin|rivaroxaban|apixaban)\b", "Blood & Heart"),
    (r"\b(panadol|paracetamol|cetamol|parafast|calpol|acetaminophen|brufen|ibuprofen|diclofenac|voltaren|mefenamic|ponstan|naproxen|ketoprofen|celecoxib|etoricoxib|arcoxia|mobic|meloxicam|piroxicam|mefenamic acid|indomethacin)\b", "Pain & Fever"),
    (r"\b(cetirizine|loratadine|zyrtec|clarityn|ebastine|fexofenadine|piriton|chlorpheniramine|levocetirizine|hydroxyzine)\b", "Allergy"),
    (r"\b(benylin|bisolvon|cough|expectorant|dextromethorphan|guaifenesin|linctus|mucinex|pholcodine|salbutamol|ventolin|fluticasone|beclometasone|prednisolone|budesonide|asthma|inhaler)\b", "Cough & Throat"),
    (r"\b(cold|flu|congest|pseudoephedrine|sinex|nasal)\b", "Cold & Flu"),
    (r"\b(omeprazole|esomeprazole|losec|nexium|pantoprazole|rabeprazole|ranitidine|gaviscon|maalox|antacid|mylanta|domperidone|metoclopramide|motonium|loperamide|imodium|diarrhoea|diarrhea|ors|rehydrat|zeddy|buscopan|hyoscine|dicyclomine|collogen|ulcer|gastro)\b", "Stomach & Digestion"),
    (r"\b(mebendazole|albendazole|vermox|worm|anthelmin|praziquantel)\b", "Worm Infections"),
    (r"\b(zinc|vitamin|vitamins|multivit|multivitamin|omega|ferrous|iron|folic|folate|calcium|collagen|probiotic|glucosamine|selenium|magnesium|b-complex|centrum|supravite|abidec)\b", "Vitamins & Supplements"),
    (r"\b(candid|canesten|clotrimazole|miconazole|ketoconazole|betnovate|hydrocortisone|antifungal|bepanthen|sudocrem|fucidin|bactroban|mupirocin|epimax|epimol|emollient|eczema|psorias|dermatitis|acne|acnes|ointment|diaper rash|nappy rash)\b", "Skin Care"),
    (r"\b(eye|ear|otic|auricular|ocular|artificial tears|chloramphenicol|ciprofloxacin.*ear|otozambon|sodium cromoglicate|betamethasone.*(eye|ear))\b", "Eye & Ear"),
    (r"\b(mouth|tooth|dental|corsodyl|rexidine|sensodyne|periodont|fluoride|toothpaste)\b", "Oral Care"),
    (r"\b(insect|repell|mosquito|bite)\b", "Insect & Bites"),
    (r"\b(first aid|bandage|plaster|wound|dressing|gauze|antiseptic|betadine|savlon|surgical|gloves)\b", "First Aid"),
    (r"\b(thermometer|glucose meter|glucometer|blood pressure|bp monitor|pulse oximeter|nebulizer|inhaler device|test strips|mask)\b", "Medical Devices"),
    (r"\b(pregnancy test|condom|contracept|postinor|preg test|emergency pill|iud)\b", "Sexual Health"),
    (r"\b(pad|sanitary|menstrual|period|tampon)\b", "Period & Feminine"),
    (r"\b(baby|infant|kids|child|preg|prenatal|maternity|gripe|teething|nappy|diaper|wellbaby|wellkid|biogaia|colic|formula)\b", "Mum & Baby"),
    (r"\b(thyroid|levothyroxine|el-troxin|insomnia|zopiclone|diazepam|dependence|psych|antidepress|sertraline|fluoxetine|sertraline|quetiapine|haloperidol)\b", "Mental & Thyroid"),
    (r"\b(motion sickness|travel|antihistamine)\b", "General Health"),
]

def category_for(p):
    name = (p["name"] or "").lower()
    cat = (p.get("category") or "").lower()
    if cat in DROP_CAT:
        return None
    if any(w in name for w in DROP_WORDS):
        return None
    for pat, label in DRUG_CATS:
        if re.search(pat, name):
            return label
    return "General Health"

def slug_of(url):
    return url.rstrip("/").split("/")[-1]

def strength_and_pack(name):
    m = re.search(r"((?:\d+(?:\.\d+)?\s*(?:mg|ml|g|i\.u\.|iu|mcg|ug))+)", name, re.I)
    strength = m.group(1).strip() if m else ""
    m = re.search(r"(\d+\s*(?:'s|s|tabs?|tablets?|caps?|caplets?|pcs|pieces|sachets?|packs?|units?|ml|g)\b)", name, re.I)
    pack = m.group(1).strip() if m else ""
    return strength, pack

def placeholder_image(slug, name):
    img = Image.new("RGB", (400, 400), "#e6f5ee")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 399, 399], outline="#0b7a4b", width=3)
    d.line([(200, 130), (200, 270)], fill="#0b7a4b", width=14)
    d.line([(130, 200), (270, 200)], fill="#0b7a4b", width=14)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    label = (name[:26] + "…") if len(name) > 26 else name
    d.text((200, 310), label, fill="#075c38", font=font, anchor="mm")
    return img

def download_image(url, slug, name):
    out = IMG_DIR / f"{slug}.webp"
    if out.exists() and out.stat().st_size > 0:
        return f"images/products/{out.name}"
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            scale = min(1.0, 400 / max(img.size))
            if scale < 1.0:
                img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
            canvas = Image.new("RGB", (400, 400), "#ffffff")
            canvas.paste(img, ((400 - img.width) // 2, (400 - img.height) // 2))
            canvas.save(out, "WEBP", quality=82)
            return f"images/products/{out.name}"
        except Exception:
            time.sleep(1)
    placeholder_image(slug, name).save(out, "WEBP", quality=82)
    return f"images/products/{out.name}"

def main():
    raw = json.load(open(RAW))
    print(f"raw products: {len(raw)}", flush=True)
    seen = {}
    byname = {}
    for p in raw:
        byname.setdefault(p["name"], []).append(p)
    for name, group in byname.items():
        p = group[0]
        cat = category_for(p)
        if not cat:
            continue
        name, brand, desc = sanitize(p)
        slug = slug_of(p["url"])
        slug = re.sub(r"(?i)^(mydawa|goodlife|pharmaduka)[-_]?", "", slug)
        strength, pack = strength_and_pack(name)
        seen[name] = {
            "slug": slug,
            "name": name,
            "brand": brand,
            "category": cat,
            "price": max(1, int(round(p["price"] * SALE_MULT))),
            "prescription": bool(p.get("prescriptionRequired")),
            "inStock": True,
            "image": "",
            "description": desc,
            "generic": strength,
            "pack": pack,
        }
    items = list(seen.values())
    print(f"after filter/dedupe: {len(items)}", flush=True)
    order = []
    for c in ["Malaria", "Antibiotics", "Blood Pressure", "Diabetes", "Blood & Heart",
              "Pain & Fever", "Allergy", "Cold & Flu", "Cough & Throat", "Stomach & Digestion",
              "Worm Infections", "Eye & Ear", "Skin Care", "Oral Care", "First Aid",
              "Medical Devices", "Mental & Thyroid", "Vitamins & Supplements", "Mum & Baby",
              "Period & Feminine", "Sexual Health", "Insect & Bites", "General Health"]:
        pool = [p for p in items if p["category"] == c]
        pool.sort(key=lambda p: (p["prescription"], -p["price"]))
        order += pool
    picked = order[:MAX_ITEMS]
    print(f"picked: {len(picked)}", flush=True)
    for i, p in enumerate(picked):
        p["image"] = download_image(byname[p["name"]][0]["image"], p["slug"], p["name"])
        if (i + 1) % 25 == 0:
            print(f"  images {i + 1}/{len(picked)}", flush=True)
    for i, p in enumerate(picked):
        p["id"] = f"p{1000 + i:04d}"
    catalog = {"updatedAt": time.strftime("%Y-%m-%d"), "products": picked}
    (ROOT / "src" / "data" / "products.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    (ROOT / "public" / "products.json").write_text(json.dumps(picked, indent=2, ensure_ascii=False))
    print(f"written {len(picked)} products", flush=True)
    rx = sum(1 for p in picked if p["prescription"])
    print(f"prescription items: {rx}", flush=True)
    cats = {}
    for p in picked:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {c}", flush=True)

if __name__ == "__main__":
    main()
