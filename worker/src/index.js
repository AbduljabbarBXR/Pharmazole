const JSON_HEADERS = { 'content-type': 'application/json;charset=UTF-8' };

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...extra }
  });
}

function corsHeaders(env, origin) {
  const allowed = (env.ALLOWED_ORIGINS || '').split(',').map((s) => s.trim());
  if (!origin || !allowed.includes(origin)) return {};
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Vary': 'Origin'
  };
}

const enc = new TextEncoder();

async function pbkdf2Verify(password, stored) {
  const [algo, iter, saltB64, hashB64] = stored.split('$');
  if (algo !== 'pbkdf2') return false;
  const salt = Uint8Array.from(atob(saltB64), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: parseInt(iter, 10), hash: 'SHA-256' },
    key, 256
  );
  const expected = Uint8Array.from(atob(hashB64), (c) => c.charCodeAt(0));
  const got = new Uint8Array(bits);
  if (got.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < got.length; i++) diff |= got[i] ^ expected[i];
  return diff === 0;
}

async function hmac(keyStr, dataStr) {
  const key = await crypto.subtle.importKey('raw', enc.encode(keyStr), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(dataStr));
  return btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/=+$/, '');
}

function b64url(s) {
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function b64urlDecode(s) {
  return atob(s.replace(/-/g, '+').replace(/_/g, '/'));
}

async function makeSession(env) {
  const payload = { exp: Date.now() + 7 * 24 * 3600 * 1000 };
  const body = b64url(JSON.stringify(payload));
  const sig = await hmac(env.SESSION_SECRET, 'sess.' + body);
  return body + '.' + sig;
}

async function verifySession(env, cookie) {
  if (!cookie) return false;
  const parts = cookie.split('.');
  if (parts.length !== 2) return false;
  const sig = await hmac(env.SESSION_SECRET, 'sess.' + parts[0]);
  if (sig !== parts[1]) return false;
  try {
    const payload = JSON.parse(b64urlDecode(parts[0]));
    return payload.exp > Date.now();
  } catch (e) {
    return false;
  }
}

function makeToken(env, orderId, scope, ttlMs = 48 * 3600 * 1000) {
  const payload = { o: orderId, s: scope, exp: Date.now() + ttlMs };
  const body = b64url(JSON.stringify(payload));
  return body + '.' + crypto.randomUUID().slice(0, 8);
}

async function verifyToken(env, token, orderId, scope) {
  if (!token) return false;
  const parts = token.split('.');
  if (parts.length !== 2) return false;
  const sig = await hmac(env.SESSION_SECRET, 'tok.' + parts[0] + '.' + orderId + '.' + scope);
  if (sig !== parts[1]) return false;
  try {
    const payload = JSON.parse(b64urlDecode(parts[0]));
    return payload.exp > Date.now() && payload.o === orderId && payload.s === scope;
  } catch (e) {
    return false;
  }
}

const GITHUB = 'https://api.github.com';

async function gh(env, path, opts = {}) {
  const res = await fetch(GITHUB + path, {
    method: opts.method || 'GET',
    headers: {
      Authorization: 'Bearer ' + env.GITHUB_TOKEN,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'PharmazoleWorker',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(opts.headers || {})
    },
    body: opts.body
  });
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    const msg = (data && (data.message || data.errors && data.errors[0] && data.errors[0].message)) || ('GitHub error ' + res.status);
    throw new Error(msg);
  }
  return data;
}

async function ghGetFile(env, repo, path) {
  try {
    return await gh(env, `/repos/${repo}/contents/${path}`);
  } catch (e) {
    return null;
  }
}

async function ghPutFile(env, repo, path, contentB64, message) {
  const existing = await ghGetFile(env, repo, path);
  const body = { message, content: contentB64, branch: 'main' };
  if (existing && existing.sha) body.sha = existing.sha;
  return gh(env, `/repos/${repo}/contents/${path}`, { method: 'PUT', body: JSON.stringify(body) });
}

function genId() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let s = '';
  const r = crypto.getRandomValues(new Uint8Array(6));
  for (const b of r) s += chars[b % chars.length];
  return 'PZ-' + s;
}

function orderPath(id) {
  const ym = new Date().toISOString().slice(0, 7);
  return `orders/${ym}/${id}.json`;
}

const treeCache = new Map();
async function findOrderFile(env, id) {
  const cached = treeCache.get(env.PRIVATE_REPO);
  if (cached && cached.at > Date.now() - 5 * 60 * 1000) {
    const hit = cached.paths.find((p) => p.endsWith(`/${id}.json`));
    if (hit) return hit;
  }
  try {
    const tree = await gh(env, `/repos/${env.PRIVATE_REPO}/git/trees/main?recursive=1`);
    const paths = (tree.tree || []).map((t) => t.path);
    treeCache.set(env.PRIVATE_REPO, { at: Date.now(), paths });
    return paths.find((p) => p.endsWith(`/${id}.json`)) || null;
  } catch (e) {
    return null;
  }
}

function statusFlow() {
  return ['placed', 'awaiting-payment', 'payment-submitted', 'confirmed', 'dispatched', 'delivered'];
}

// ---------- rate limiting (in-memory) ----------
const rateMap = new Map();
function rateLimit(key, max, windowMs) {
  const now = Date.now();
  const entry = rateMap.get(key);
  if (!entry || entry.reset < now) {
    rateMap.set(key, { n: 1, reset: now + windowMs });
    return true;
  }
  if (entry.n >= max) return false;
  entry.n++;
  return true;
}

function cookieHeader(cookie) {
  return `pz_auth=${cookie}; Path=/; HttpOnly; SameSite=None; Secure; Max-Age=${7 * 24 * 3600}`;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(env, origin);
    const path = url.pathname;
    const method = request.method;

    if (method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    const send = (body, status = 200) => json(body, status, cors);
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';

    // ---------- admin auth ----------
    if (path === '/api/admin/login' && method === 'POST') {
      if (!rateLimit('login:' + ip, 10, 60 * 1000)) return send({ error: 'Too many attempts, try again in a minute' }, 429);
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const ok = await pbkdf2Verify(String(body.password || ''), env.PBKDF2_HASH);
      if (!ok) return send({ error: 'Invalid password' }, 401);
      const cookie = await makeSession(env);
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { ...JSON_HEADERS, ...cors, 'Set-Cookie': cookieHeader(cookie) }
      });
    }

    if (path === '/api/admin/logout' && method === 'POST') {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { ...JSON_HEADERS, ...cors, 'Set-Cookie': 'pz_auth=; Path=/; HttpOnly; SameSite=None; Secure; Max-Age=0' }
      });
    }

    if (path === '/api/admin/session' && method === 'GET') {
      const cookie = request.headers.get('Cookie') || '';
      const authed = await verifySession(env, cookie.match(/pz_auth=([^;]+)/)?.[1]);
      return send({ authed });
    }

    const cookie = request.headers.get('Cookie') || '';
    const authed = await verifySession(env, cookie.match(/pz_auth=([^;]+)/)?.[1]);

    const isAdminRoute = path.startsWith('/api/admin/') && !path.startsWith('/api/admin/session') && !path.startsWith('/api/admin/login');
    if (isAdminRoute && !authed) return send({ error: 'Not authorised' }, 401);

    // ---------- public: order creation ----------
    if (path === '/api/order' && method === 'POST') {
      if (!rateLimit('order:' + ip, 20, 60 * 1000)) return send({ error: 'Too many orders, slow down' }, 429);
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const { customer, zone, items, subtotal, delivery, total, prescription } = body;

      if (!customer || !customer.name || !customer.phone || !customer.address) {
        return send({ error: 'Missing customer details' }, 400);
      }
      if (!/^2547\d{8}$/.test(customer.phone)) return send({ error: 'Invalid phone number' }, 400);
      if (!zone || !zone.id || typeof zone.fee !== 'number') return send({ error: 'Missing delivery zone' }, 400);
      if (!Array.isArray(items) || !items.length) return send({ error: 'Cart is empty' }, 400);
      if (typeof total !== 'number' || total <= 0) return send({ error: 'Invalid total' }, 400);
      if (items.some((i) => i.prescription) && !prescription) {
        return send({ error: 'A prescription is required for prescription items' }, 400);
      }
      if (prescription && (!prescription.data || (prescription.data.length > 8 * 1024 * 1024))) {
        return send({ error: 'Prescription image is missing or too large' }, 400);
      }

      const id = genId();
      const now = new Date().toISOString();
      const hasRx = items.some((i) => i.prescription);
      const storedPath = orderPath(id);
      const order = {
        id,
        path: storedPath,
        createdAt: now,
        status: 'placed',
        statusHistory: [{ at: now, status: 'placed' }],
        customer: { name: customer.name, phone: customer.phone, address: customer.address, note: customer.note || '' },
        zone,
        items,
        subtotal,
        delivery,
        total,
        paymentCode: null,
        paidAt: null,
        prescription: hasRx ? { file: `prescriptions/${id}${extOf(prescription.name)}` } : null,
        ownerToken: makeToken(env, id, 'owner')
      };

      try {
        await ghPutFile(env, env.PRIVATE_REPO, storedPath, b64(JSON.stringify(order, null, 2)), `Create order ${id}`);
        if (hasRx) {
          await ghPutFile(env, env.PRIVATE_REPO, `prescriptions/${id}${extOf(prescription.name)}`, prescription.data, `Prescription for ${id}`);
        }
      } catch (e) {
        return send({ error: 'Could not save order: ' + e.message }, 502);
      }
      treeCache.delete(env.PRIVATE_REPO);
      return send({ ok: true, id, tillNumber: env.TILL_NUMBER || '', tillName: env.TILL_NAME || '', whatsapp: env.OWNER_WHATSAPP });
    }

    // ---------- public: order lookup ----------
    let orderMatch = path.match(/^\/api\/order\/(PZ-[A-Z0-9]+)\/payment$/);
    if (orderMatch && method === 'POST') {
      const id = orderMatch[1];
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const token = url.searchParams.get('token') || '';
      const phone = url.searchParams.get('phone') || '';
      const storedPath = await findOrderFile(env, id);
      if (!storedPath) return send({ error: 'Order not found' }, 404);
      const file = await ghGetFile(env, env.PRIVATE_REPO, storedPath);
      const order = JSON.parse(b64Decode(file.content));
      if (order.customer.phone !== phone && !(await verifyToken(env, token, id, 'owner'))) {
        return send({ error: 'Not authorised' }, 401);
      }
      if (!body.code || String(body.code).length < 6) return send({ error: 'Enter a valid M-Pesa confirmation code' }, 400);
      if (order.paymentCode) return send({ error: 'Payment code already submitted' }, 400);
      order.paymentCode = String(body.code).toUpperCase();
      order.paidAt = new Date().toISOString();
      order.status = 'payment-submitted';
      order.statusHistory.push({ at: order.paidAt, status: 'payment-submitted' });
      await ghPutFile(env, env.PRIVATE_REPO, storedPath, b64(JSON.stringify(order, null, 2)), `Payment submitted for ${id}`);
      return send({ ok: true, status: order.status });
    }

    orderMatch = path.match(/^\/api\/order\/(PZ-[A-Z0-9]+)$/);
    if (orderMatch && method === 'GET') {
      const id = orderMatch[1];
      const token = url.searchParams.get('token') || '';
      const phone = url.searchParams.get('phone') || '';
      const storedPath = await findOrderFile(env, id);
      if (!storedPath) return send({ error: 'Order not found' }, 404);
      const file = await ghGetFile(env, env.PRIVATE_REPO, storedPath);
      const order = JSON.parse(b64Decode(file.content));
      if (order.customer.phone !== phone && !(await verifyToken(env, token, id, 'owner'))) {
        return send({ error: 'Order not found' }, 404);
      }
      return send({
        id: order.id,
        status: order.status,
        items: order.items,
        subtotal: order.subtotal,
        delivery: order.delivery,
        total: order.total,
        customer: { name: order.customer.name, phone: order.customer.phone, address: order.customer.address },
        prescription: order.prescription,
        paymentCode: order.paymentCode,
        createdAt: order.createdAt
      });
    }

    // ---------- owner prescription image ----------
    orderMatch = path.match(/^\/api\/order\/(PZ-[A-Z0-9]+)\/prescription$/);
    if (orderMatch && method === 'GET') {
      const id = orderMatch[1];
      const token = url.searchParams.get('token') || '';
      if (!(await verifyToken(env, token, id, 'owner')) && !authed) {
        return send({ error: 'Not authorised' }, 401);
      }
      const storedPath = await findOrderFile(env, id);
      if (!storedPath) return send({ error: 'Order not found' }, 404);
      const file = await ghGetFile(env, env.PRIVATE_REPO, storedPath);
      const order = JSON.parse(b64Decode(file.content));
      if (!order.prescription) return send({ error: 'No prescription on this order' }, 404);
      const img = await ghGetFile(env, env.PRIVATE_REPO, order.prescription.file);
      if (!img) return send({ error: 'Prescription file not found' }, 404);
      return send({ data: img.content, mime: mimeOf(order.prescription.file), name: order.prescription.file.split('/').pop() });
    }

    // ---------- admin: orders ----------
    if (path === '/api/admin/orders' && method === 'GET') {
      let tree;
      try {
        tree = await gh(env, `/repos/${env.PRIVATE_REPO}/git/trees/main?recursive=1`);
        treeCache.set(env.PRIVATE_REPO, { at: Date.now(), paths: (tree.tree || []).map((t) => t.path) });
      } catch (e) {
        return send({ error: 'Could not list orders: ' + e.message }, 502);
      }
      const orderFiles = (tree.tree || []).filter((t) => t.path.startsWith('orders/') && t.path.endsWith('.json')).slice(-150);
      const orders = [];
      for (const f of orderFiles) {
        try {
          const content = await gh(env, `/repos/${env.PRIVATE_REPO}/contents/${f.path}`);
          orders.push(JSON.parse(b64Decode(content.content)));
        } catch (e) {}
      }
      orders.sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''));
      const summary = orders.map((o) => ({
        id: o.id, createdAt: o.createdAt, status: o.status, total: o.total,
        customer: o.customer && o.customer.name, phone: o.customer && o.customer.phone,
        itemCount: (o.items || []).length, hasRx: (o.items || []).some((i) => i.prescription),
        paymentCode: o.paymentCode
      }));
      return send({ orders: summary });
    }

    // ---------- admin: order detail / status ----------
    orderMatch = path.match(/^\/api\/admin\/orders\/(PZ-[A-Z0-9]+)\/prescription$/);
    if (orderMatch && method === 'GET') {
      const id = orderMatch[1];
      const storedPath = await findOrderFile(env, id);
      if (!storedPath) return send({ error: 'Order not found' }, 404);
      const file = await ghGetFile(env, env.PRIVATE_REPO, storedPath);
      const order = JSON.parse(b64Decode(file.content));
      if (!order.prescription) return send({ error: 'No prescription on this order' }, 404);
      const img = await ghGetFile(env, env.PRIVATE_REPO, order.prescription.file);
      if (!img) return send({ error: 'Prescription file not found' }, 404);
      return send({ data: img.content, mime: mimeOf(order.prescription.file), name: order.prescription.file.split('/').pop() });
    }

    orderMatch = path.match(/^\/api\/admin\/orders\/(PZ-[A-Z0-9]+)$/);
    if (orderMatch && method === 'GET') {
      const id = orderMatch[1];
      const storedPath = await findOrderFile(env, id);
      if (!storedPath) return send({ error: 'Order not found' }, 404);
      const file = await ghGetFile(env, env.PRIVATE_REPO, storedPath);
      const order = JSON.parse(b64Decode(file.content));
      const { ownerToken, ...rest } = order;
      return send(rest);
    }

    orderMatch = path.match(/^\/api\/admin\/orders\/(PZ-[A-Z0-9]+)\/status$/);
    if (orderMatch && method === 'PUT') {
      const id = orderMatch[1];
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const status = String(body.status || '');
      if (!statusFlow().includes(status)) return send({ error: 'Invalid status' }, 400);
      const storedPath = await findOrderFile(env, id);
      if (!storedPath) return send({ error: 'Order not found' }, 404);
      const file = await ghGetFile(env, env.PRIVATE_REPO, storedPath);
      const order = JSON.parse(b64Decode(file.content));
      order.status = status;
      order.statusHistory.push({ at: new Date().toISOString(), status });
      await ghPutFile(env, env.PRIVATE_REPO, storedPath, b64(JSON.stringify(order, null, 2)), `Order ${id} → ${status}`);
      return send({ ok: true, status: order.status });
    }

    // ---------- admin: site settings ----------
    if (path === '/api/admin/site' && method === 'PUT') {
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const site = body.site;
      if (!site || typeof site !== 'object') return send({ error: 'Invalid site data' }, 400);
      const clean = {
        brand: String(site.brand || 'Pharmazole'),
        tagline: String(site.tagline || ''),
        heroTitle: String(site.heroTitle || ''),
        tillNumber: String(site.tillNumber || ''),
        tillName: String(site.tillName || ''),
        whatsapp: String(site.whatsapp || '').replace(/[^\d]/g, ''),
        whatsappDisplay: String(site.whatsappDisplay || ''),
        apiBase: '/api',
        currency: 'KES',
        delivery: site.delivery || {},
        legal: site.legal || {},
        whatsappTemplates: site.whatsappTemplates || {}
      };
      await ghPutFile(env, env.SITE_REPO, 'src/data/site.json', b64(JSON.stringify(clean, null, 2)), 'Update site settings');
      return send({ ok: true, site: clean });
    }

    // ---------- admin: products ----------
    if (path === '/api/admin/products' && method === 'PUT') {
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const products = body.products;
      if (!Array.isArray(products)) return send({ error: 'Invalid products data' }, 400);
      const clean = products.map((p) => ({
        id: String(p.id),
        slug: String(p.slug),
        name: String(p.name),
        brand: String(p.brand || ''),
        category: String(p.category || 'General'),
        price: Math.max(0, Number(p.price) || 0),
        prescription: !!p.prescription,
        inStock: p.inStock !== false,
        image: String(p.image || ''),
        description: String(p.description || ''),
        generic: String(p.generic || ''),
        pack: String(p.pack || '')
      }));
      await ghPutFile(env, env.SITE_REPO, 'src/data/products.json', b64(JSON.stringify({ updatedAt: new Date().toISOString().slice(0, 10), products: clean }, null, 2)), `Update catalog (${clean.length} products)`);
      await ghPutFile(env, env.SITE_REPO, 'public/products.json', b64(JSON.stringify(clean, null, 2)), `Sync public catalog (${clean.length} products)`);
      return send({ ok: true, count: clean.length });
    }

    // ---------- admin: image upload ----------
    if (path === '/api/admin/image' && method === 'POST') {
      let body = {};
      try { body = await request.json(); } catch (e) {}
      const { filename, data } = body;
      if (!filename || !data) return send({ error: 'Missing filename or data' }, 400);
      if (!/^[a-z0-9-_]+\.(webp|png|jpe?g)$/i.test(filename)) return send({ error: 'Invalid filename' }, 400);
      if (data.length > 6 * 1024 * 1024) return send({ error: 'Image too large' }, 400);
      const clean = filename.toLowerCase();
      await ghPutFile(env, env.SITE_REPO, `public/images/products/${clean}`, data, `Upload image ${clean}`);
      return send({ ok: true, path: `images/products/${clean}` });
    }

    return send({ error: 'Not found' }, 404);
  }
};

function b64(s) {
  const bytes = enc.encode(s);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function b64Decode(s) {
  const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/'));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

function extOf(name) {
  const m = /\.([a-z0-9]+)$/i.exec(name || '');
  const e = m ? m[1].toLowerCase() : 'jpg';
  return e === 'jpeg' ? 'jpg' : e;
}

function mimeOf(file) {
  if (file.endsWith('.png')) return 'image/png';
  if (file.endsWith('.webp')) return 'image/webp';
  return 'image/jpeg';
}
