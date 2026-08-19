# Pharmazole

Pharmazole is an online pharmacy storefront for Nairobi, Kenya. Customers browse a catalog of medicines, pay with Mpesa till, and get same day delivery.

## Features

+ 155 products across 10 categories, with prescription only medicines clearly flagged
+ Category pages with hand drawn hero art and a search page with sorting
+ Cart drawer and checkout with Mpesa till payment
+ Order tracking with status updates and WhatsApp confirmations
+ Admin panel for managing orders and products
+ Responsive design that works on phone and desktop

## Tech stack

+ Astro for the static front end
+ Cloudflare Worker for the API and order storage
+ Supabase for the database (setup pending)
+ Paystack for payments (setup pending)

## Project layout

+ `src/data` holds site settings, the product catalog, and category helpers
+ `src/pages` holds all pages, including the category, search, checkout, order tracking, and admin pages
+ `src/layouts` holds the shared page layout
+ `public/images` holds the hand drawn category art and product icons
+ `public/scripts/store.js` holds the front end cart and checkout logic
+ `worker` holds the Cloudflare Worker API

## Local development

```
npm install
npm run dev
```

The site runs at http://localhost:4321. The astro config proxies `/api` calls to the worker on port 8787, so start the worker first.

## Worker

```
cd worker
npm install
npm run dev
```

Secrets are stored via `wrangler secret put`. See `worker/wrangler.toml` for the current setup.

## Production build

```
npm run build
npm run preview
```

## Configuration

Edit `src/data/site.json` to set the brand text, till number, WhatsApp number, delivery zones and fees, and the legal placeholders. Product data lives in `src/data/products.json`.

## License

Private project.