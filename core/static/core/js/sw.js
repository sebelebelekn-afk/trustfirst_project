// ==========================================================================
// TRUSTFIRST SERVICE WORKER — PWA + OFFLINE + CACHING
// ==========================================================================
const CACHE_VERSION = 'trustfirst-v3.0';
const STATIC_CACHE = CACHE_VERSION + '-static';
const DYNAMIC_CACHE = CACHE_VERSION + '-dynamic';
const IMAGE_CACHE = CACHE_VERSION + '-images';

const STATIC_ASSETS = [
  '/'
];

const MAX_DYNAMIC_CACHE = 50;
const MAX_IMAGE_CACHE = 100;

// Install — Cache static shell
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

// Activate — Clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== DYNAMIC_CACHE && key !== IMAGE_CACHE)
          .map((key) => {
            console.log('[SW] Deleting old cache:', key);
            return caches.delete(key);
          })
      );
    })
  );
  self.clients.claim();
});

// Fetch — Strategy: Cache First for static, Network First for API, Stale While Revalidate for images
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // ONLY ever handle our own same-origin requests. Third-party calls
  // (Supabase auth / REST / realtime / storage, CDNs, etc.) must go straight to
  // the network — never route them through the cache or the offline fallback,
  // or failures surface as confusing CORS errors and break login/data loading.
  if (url.origin !== self.location.origin) return;

  // API calls — Network First
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(event.request, DYNAMIC_CACHE));
    return;
  }

  // Images — Stale While Revalidate
  if (
    event.request.destination === 'image' ||
    url.hostname === 'picsum.photos' ||
    url.pathname.match(/\.(jpg|jpeg|png|gif|webp|svg)$/)
  ) {
    event.respondWith(staleWhileRevalidate(event.request, IMAGE_CACHE, MAX_IMAGE_CACHE));
    return;
  }

  // App shell (HTML pages + our own JS/CSS) — Network First so code updates
  // reach users immediately when online, with cache fallback for offline.
  if (
    event.request.mode === 'navigate' ||
    (url.origin === self.location.origin && url.pathname.match(/\.(js|css)$/))
  ) {
    event.respondWith(networkFirst(event.request, STATIC_CACHE));
    return;
  }

  // Other static assets (fonts, etc.) — Cache First
  event.respondWith(cacheFirst(event.request, STATIC_CACHE));
});

// Strategy: Cache First
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    return offlineFallback();
  }
}

// Strategy: Network First
async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
      trimCache(cacheName, MAX_DYNAMIC_CACHE);
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    return cached || offlineFallback();
  }
}

// Strategy: Stale While Revalidate
async function staleWhileRevalidate(request, cacheName, maxItems) {
  const cached = await caches.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        caches.open(cacheName).then((cache) => {
          cache.put(request, response.clone());
          trimCache(cacheName, maxItems);
        });
      }
      return response;
    })
    .catch(() => cached);

  return cached || fetchPromise;
}

// Trim cache to max size
async function trimCache(cacheName, maxItems) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length > maxItems) {
    await cache.delete(keys[0]);
    trimCache(cacheName, maxItems);
  }
}

// Offline fallback page
function offlineFallback() {
  return new Response(
    `<!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
      body{font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#000;color:#fff;text-align:center;margin:0;}
      .offline-box{padding:40px;}
      h1{font-size:28px;margin-bottom:10px;}
      p{color:#888;margin-bottom:25px;}
      button{background:#007AFF;color:white;border:none;padding:14px 28px;border-radius:20px;font-weight:bold;font-size:16px;cursor:pointer;}
    </style></head>
    <body><div class="offline-box">
      <h1>You're Offline</h1>
      <p>TrustFirst needs a connection to load new content.</p>
      <button onclick="location.reload()">Try Again</button>
    </div></body></html>`,
    { headers: { 'Content-Type': 'text/html' } }
  );
}

// Push Notifications
self.addEventListener('push', (event) => {
  let data = { title: 'TrustFirst', body: 'You have a new notification' };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/core/icon-dark-192.png',
      badge: '/static/core/icon-dark-192.png',
      vibrate: [100, 50, 100],
      data: data.url || '/',
      actions: [
        { action: 'open', title: 'Open' },
        { action: 'dismiss', title: 'Dismiss' }
      ]
    })
  );
});

// Notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'dismiss') return;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow(event.notification.data || '/');
    })
  );
});

// Background Sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-posts') {
    event.waitUntil(syncPendingPosts());
  }
  if (event.tag === 'sync-messages') {
    event.waitUntil(syncPendingMessages());
  }
});

async function syncPendingPosts() {
  // Pull from IndexedDB queue and POST to server
  console.log('[SW] Syncing pending posts...');
}

async function syncPendingMessages() {
  console.log('[SW] Syncing pending messages...');
}