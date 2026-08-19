import { site } from '../data/catalog.mjs';

const FALLBACK_IMAGE = 'images/fallback-product.png';

export function pathFor(image) {
  if (!image) return import.meta.env.BASE_URL + FALLBACK_IMAGE.replace(/^\//, '');
  if (/^https?:\/\//.test(image)) return image;
  return import.meta.env.BASE_URL + image.replace(/^\//, '');
}

export function fallbackPath() {
  return import.meta.env.BASE_URL + FALLBACK_IMAGE.replace(/^\//, '');
}

export const img = {
  url: (p) => pathFor(p && p.image),
  fallback: fallbackPath
};

export function waLink(text) {
  return 'https://wa.me/' + site.whatsapp + '?text=' + encodeURIComponent(text);
}
