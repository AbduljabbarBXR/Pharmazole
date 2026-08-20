import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: process.env.ASTRO_SITE || 'https://pharmazole.netlify.app',
  base: process.env.ASTRO_BASE || '/',
  trailingSlash: 'ignore',
  integrations: [sitemap()],
  server: { port: 4321, host: true },
  build: { assets: '_assets' }
});
