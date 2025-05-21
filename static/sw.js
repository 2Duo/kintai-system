const CACHE_NAME = 'kintai-app-cache-v1';
const urlsToCache = [
  '/',
  '/static/style.css',
  // 必要に応じて他の静的リソース
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
  );
});
