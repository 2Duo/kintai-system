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
  const url = new URL(event.request.url);
  if (
    event.request.headers.get('accept') === 'text/event-stream' ||
    url.pathname === '/events'
  ) {
    // SSEはキャッシュせずに直接取得
    event.respondWith(fetch(event.request));
    return;
  }
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
  );
});
