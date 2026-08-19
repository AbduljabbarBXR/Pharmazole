import productsJson from './products.json';
import siteJson from './site.json';

export const site = siteJson;

export const products = productsJson.products || [];

export function bySlug(slug) {
  return products.find((p) => p.slug === slug);
}

export function categories() {
  const map = new Map();
  for (const p of products) {
    if (!map.has(p.category)) map.set(p.category, 0);
    map.set(p.category, map.get(p.category) + 1);
  }
  return [...map.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
}

export function cartIndex() {
  const idx = {};
  for (const p of products) {
    idx[p.id] = {
      id: p.id,
      slug: p.slug,
      name: p.name,
      price: p.price,
      image: p.image,
      prescription: p.prescription,
      inStock: p.inStock,
      category: p.category
    };
  }
  return idx;
}

export function categorySlug(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function categoryBySlug(slug) {
  return categories().find((c) => categorySlug(c.name) === slug) || null;
}

export function productsFor(name) {
  return products.filter((p) => p.category === name);
}

export const categoryBlurbs = {
  'Pain & Fever':
    'Relief for headaches, body aches, fever, and everyday pain. Analgesics and anti inflammatory medicines for the whole family, delivered the same day.',
  'Cold & Flu':
    'Cold, flu, and sinus relief: decongestants, antihistamines, and combination formulas to get you back on your feet.',
  'Cough & Throat':
    'Cough syrups, lozenges, expectorants, and inhalers to calm a dry chest, ease a tickly throat, and clear congestion.',
  Antibiotics:
    'Prescription antibiotics, reviewed by our pharmacist before dispatch to make sure the medicine is right for you.',
  'Blood Pressure':
    'Daily blood pressure medicines from trusted brands, with pharmacist guidance and easy refills.',
  'Stomach & Digestion':
    'Heartburn, indigestion, and tummy troubles: antacids and digestive health essentials for fast, soothing relief.',
  Diabetes:
    'Insulins, pens, and oral diabetes medicines to help you manage blood sugar levels day to day with confidence.',
  'Blood & Heart':
    'Cholesterol and heart health medicines to support long term cardiovascular care, dispensed with care.',
  Allergy:
    'Antihistamines and allergy relief for sneezing, hives, itching, and hay fever, so the season never slows you down.',
  Malaria:
    'Quality assured antimalarials to treat and prevent malaria, supplied by a PPB licensed pharmacy.'
};
