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
