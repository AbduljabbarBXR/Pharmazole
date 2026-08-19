window.PZ = (function () {
  const CART_KEY = 'pz_cart_v1';
  const ZONE_KEY = 'pz_zone_v1';

  function readJson(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  const dataEl = document.getElementById('pz-data');
  const SITE = readJson('pz-site') || {};
  const PRODUCTS = readJson('pz-catalog') || {};
  const BASE = (SITE.apiBase || '/api').replace(/\/$/, '');
  const BASE_URL = readJson('pz-base') || '';

  function cart() {
    try { return JSON.parse(localStorage.getItem(CART_KEY)) || {}; } catch (e) { return {}; }
  }
  function saveCart(c) { localStorage.setItem(CART_KEY, JSON.stringify(c)); }
  function zone() {
    try { return JSON.parse(localStorage.getItem(ZONE_KEY)) || null; } catch (e) { return null; }
  }
  function saveZone(z) { localStorage.setItem(ZONE_KEY, JSON.stringify(z)); }

  function count() {
    return Object.values(cart()).reduce((a, b) => a + b, 0);
  }

  function addToCart(id, qty) {
    const c = cart();
    c[id] = (c[id] || 0) + qty;
    saveCart(c);
    emit();
  }
  function setQty(id, qty) {
    const c = cart();
    if (qty <= 0) delete c[id]; else c[id] = qty;
    saveCart(c);
    emit();
  }
  function clearCart() { saveCart({}); emit(); }

  function items() {
    const c = cart();
    return Object.entries(c).map(([id, qty]) => {
      const p = PRODUCTS[id] || {};
      return { id, qty, ...p };
    }).filter((i) => i.name);
  }

  function subtotal() { return items().reduce((a, i) => a + i.price * i.qty, 0); }

  function hasRx() { return items().some((i) => i.prescription); }

  function deliveryFee() {
    const z = zone();
    if (!z) return null;
    const zf = (SITE.delivery && SITE.delivery.zones || []).find((x) => x.id === z.id);
    return zf ? zf.fee : null;
  }

  function total() {
    const fee = deliveryFee();
    return subtotal() + (fee == null ? 0 : fee);
  }

  function toast(msg, isErr) {
    let t = document.querySelector('.toast');
    if (!t) {
      t = document.createElement('div');
      t.className = 'toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.toggle('err', !!isErr);
    t.classList.add('show');
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove('show'), 2600);
  }

  function fmt(n) { return 'KES ' + Number(n || 0).toLocaleString('en-KE'); }

  async function api(path, opts) {
    const res = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      ...opts
    });
    let body = null;
    try { body = await res.json(); } catch (e) {}
    if (!res.ok) {
      const msg = (body && (body.error || body.message)) || 'Something went wrong';
      throw new Error(msg);
    }
    return body;
  }

  const listeners = [];
  function on(fn) { listeners.push(fn); }
  function emit() { listeners.forEach((fn) => fn()); }

  function initDrawer() {
    const overlay = document.getElementById('drawer-overlay');
    const drawer = document.getElementById('cart-drawer');
    if (!overlay || !drawer) return;
    const open = () => { overlay.classList.add('open'); drawer.classList.add('open'); };
    const close = () => { overlay.classList.remove('open'); drawer.classList.remove('open'); };
    overlay.addEventListener('click', close);
    window.PZ_closeCart = close;
    window.PZ_openCart = open;
    on(() => renderDrawer());
    renderDrawer();
  }

  function imgUrl(p) {
    const u = (p && p.image) || '';
    return /^https?:\/\//.test(u) ? u : BASE_URL + u;
  }

  function renderDrawer() {
    const list = document.getElementById('drawer-list');
    const countEl = document.getElementById('cart-count');
    if (countEl) {
      const n = count();
      countEl.textContent = n;
      countEl.classList.toggle('hide', n === 0);
    }
    if (!list) return;
    const its = items();
    if (!its.length) {
      list.innerHTML = '<div class="drawer-empty">Your cart is empty.<br>Add a product to get started.</div>';
    } else {
      list.innerHTML = its.map((i) => `
        <div class="cart-item">
          <img src="${imgUrl(i)}" alt="${esc(i.name)}" loading="lazy">
          <div class="cart-item-info">
            <div class="cart-item-name">${esc(i.name)}</div>
            <div class="cart-item-meta">${fmt(i.price)}${i.prescription ? ' &middot; Rx' : ''}</div>
          </div>
          <div class="qty-ctl">
            <button type="button" data-dec="${i.id}">&minus;</button>
            <span>${i.qty}</span>
            <button type="button" data-inc="${i.id}">+</button>
          </div>
          <button type="button" class="cart-remove" data-rm="${i.id}" title="Remove">&times;</button>
        </div>`).join('');
      list.querySelectorAll('[data-dec]').forEach((b) => b.addEventListener('click', () => {
        const it = items().find((x) => x.id === b.dataset.dec);
        setQty(b.dataset.dec, it ? it.qty - 1 : 0);
      }));
      list.querySelectorAll('[data-inc]').forEach((b) => b.addEventListener('click', () => {
        const it = items().find((x) => x.id === b.dataset.inc);
        setQty(b.dataset.inc, (it ? it.qty : 0) + 1);
      }));
      list.querySelectorAll('[data-rm]').forEach((b) => b.addEventListener('click', () => setQty(b.dataset.rm, 0)));
    }
    const sub = document.getElementById('drawer-subtotal');
    const fee = deliveryFee();
    const tot = total();
    if (sub) {
      sub.innerHTML = `
        <div class="summary-row"><span>Subtotal</span><span>${fmt(subtotal())}</span></div>
        <div class="summary-row"><span>Delivery</span><span>${fee == null ? (zone() ? '-' : 'Choose at checkout') : fmt(fee)}</span></div>
        <div class="summary-row total"><span>Total</span><span>${fmt(tot)}</span></div>`;
    }
    const checkBtn = document.getElementById('drawer-checkout');
    if (checkBtn) checkBtn.addEventListener('click', () => { window.location.href = BASE_URL + 'checkout'; });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
  }

  return { SITE, PRODUCTS, BASE, BASE_URL, cart, addToCart, setQty, clearCart, items, subtotal, total, deliveryFee, hasRx, count, toast, fmt, api, on, initDrawer, zone, saveZone, esc, readJson };
})();

document.addEventListener('DOMContentLoaded', () => PZ.initDrawer());
