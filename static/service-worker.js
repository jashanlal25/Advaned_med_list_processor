/* Medicine List Processor - Service Worker (Stage 1)
 *
 * Policy:
 *  - Cache ONLY static shell assets (icons, manifest). No uploaded files,
 *    no search results, no chatbot messages, no API responses.
 *  - Network-first for page navigations so dynamic app pages stay fresh.
 *  - Never intercept POST requests (uploads, searches, generation, etc.).
 *  - Never cache private / user-specific data.
 */
const CACHE_NAME = 'medlist-shell-v4';

const SHELL_ASSETS = [
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-maskable-192.png',
  '/static/icon-maskable-512.png',
  '/static/shared-store.js'
];

/* Paths that must ALWAYS hit the network. These carry user data or
 * dynamic results and must never be cached or served from cache.
 */
const NETWORK_ONLY_PREFIXES = [
  '/upload',
  '/upload-lists',
  '/remove-file',
  '/search-medicines',
  '/deduplicate-upload',
  '/generate-html',
  '/download',
  '/download-html',
  '/preview-html',
  '/share',
  '/share-target',
  '/shared-file',
  '/search',
  '/diff'
];

function isNetworkOnly(url) {
  return NETWORK_ONLY_PREFIXES.some(function (prefix) {
    return url.pathname.indexOf(prefix) === 0;
  });
}

// Install: pre-cache static shell assets only.
self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(SHELL_ASSETS).catch(function () {
        // Ignore individual cache failures - installation should still complete.
      });
    })
  );
  self.skipWaiting();
});

// Activate: remove old caches, take control of clients.
self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (key) {
          return key !== CACHE_NAME;
        }).map(function (key) {
          return caches.delete(key);
        })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  var url = new URL(request.url);

  // Only handle same-origin GET requests.
  if (request.method !== 'GET') {
    return;
  }
  if (url.origin !== self.location.origin) {
    return;
  }

  // Dynamic / API / user-data routes: always network.
  if (isNetworkOnly(url)) {
    return;
  }

  // Page navigations: network-first, fall back to cached shell only when offline.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then(function (response) {
        // Optionally keep a fresh copy of the shell index for offline fallback.
        if (url.pathname === '/') {
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put('/index.html', copy);
          });
        }
        return response;
      }).catch(function () {
        return caches.match('/index.html').then(function (cached) {
          return cached || caches.match('/');
        });
      })
    );
    return;
  }

  // Static shell assets: cache-first with background refresh.
  event.respondWith(
    caches.match(request).then(function (cached) {
      var fetchPromise = fetch(request).then(function (response) {
        if (response && response.ok) {
          var copy = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(request, copy);
          });
        }
        return response;
      });
      return cached || fetchPromise;
    })
  );
});
