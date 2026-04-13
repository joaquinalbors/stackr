const CACHE_NAME = 'apexa-v4';
const ASSETS = [
  '/app',
  '/creator-login',
  '/landing.html',
  '/creator-login.html',
  '/404.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  'https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap'
];

// Install — cache all assets
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS).catch(() => Promise.resolve());
    })
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network first, fallback to cache
self.addEventListener('fetch', e => {
  // Skip API calls — always go to network
  if (e.request.url.includes('/api/') || e.request.url.includes('railway.app')) return;

  e.respondWith(
    fetch(e.request).then(response => {
      if (response && response.status === 200) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(e.request, copy));
      }
      return response;
    }).catch(() => {
      return caches.match(e.request).then(cached => {
        return cached || caches.match('/app');
      });
    })
  );
});
