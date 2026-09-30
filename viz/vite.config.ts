import { defineConfig, loadEnv } from 'vite';
import { resolve } from 'path';
import { readdirSync, readFileSync } from 'fs';

// VITE_CITY_ALLOWLIST (src/cities.ts) trims a deployment to some cities. Check it here so a typo
// fails the build instead of shipping a site with no cities, or one that defaults to a devOnly city.
function checkCityAllowlist(mode: string): void {
  const raw = process.env.VITE_CITY_ALLOWLIST ?? loadEnv(mode, resolve(__dirname, 'env')).VITE_CITY_ALLOWLIST ?? '';
  const keys = raw.split(',').map((k) => k.trim().toLowerCase()).filter(Boolean);
  if (!keys.length) return;
  // Exact city keys (JSON basenames), not paths: '../cities/asheville' must not pass.
  const dir = resolve(__dirname, 'src/cities');
  const known = new Set(readdirSync(dir).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, -5)));
  const file = (k: string) => resolve(dir, `${k}.json`);
  const unknown = keys.filter((k) => !known.has(k));
  if (unknown.length) throw new Error(`VITE_CITY_ALLOWLIST names unknown cities: ${unknown.join(', ')}`);
  if (keys.every((k) => JSON.parse(readFileSync(file(k), 'utf8')).devOnly))
    throw new Error('VITE_CITY_ALLOWLIST has only devOnly cities; a deployed build would have no default city');
}

export default defineConfig(({ mode }) => {
  checkCityAllowlist(mode);
  return {
    // Serve from domain root in production deployments (Azure SWA)
    // If you later host under a subpath, set base accordingly
    base: '/',
    // Point env loading at a sandbox-safe folder to avoid .env permission issues
    envDir: resolve(__dirname, 'env'),
    build: {
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes('node_modules/maplibre-gl')) return 'maplibre';
            if (id.includes('node_modules/pmtiles')) return 'pmtiles';
            if (
              id.includes('node_modules/geoparquet') ||
              id.includes('node_modules/hyparquet')
            ) {
              return 'parquet';
            }
            return undefined;
          }
        },
        input: {
          main: resolve(__dirname, 'index.html'),
          app: resolve(__dirname, 'app.html'),
          cities: resolve(__dirname, 'cities.html'),
          parking: resolve(__dirname, 'parking.html'),
          contribute: resolve(__dirname, 'contribute.html')
        }
      }
    },
    // Dev server proxies
    server: {
      proxy: {
        // Proxy API requests to local API server on port 8080
        '/api': {
          target: 'http://localhost:8080',
          changeOrigin: true,
          secure: false
        },

        // Proxy remote GeoParquet to avoid browser CORS (dev only)
        '/data': {
          target: process.env.VITE_PARQUET_BASE_URL || 'https://landeconomics.blob.core.windows.net/parquets-dev',
          changeOrigin: true,
          secure: true,
          rewrite: (p: string) => p.replace(/^\/data/, '')
        }
      }
    }
  };
});
