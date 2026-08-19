import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://abduljabbarbxr.github.io',
  base: '/Pharmazole/',
  trailingSlash: 'ignore',
  integrations: [sitemap()],
  server: { port: 4321, host: true },
  build: { assets: '_assets' }
});
