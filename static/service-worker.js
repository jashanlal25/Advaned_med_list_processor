/* Medicine List Processor - Service Worker (Stage 1)
 *
 * Policy:
 *  - Cache ONLY static shell assets (icons, manifest). No uploaded files,
 *    no search results, no chatbot messages, no API responses.
 *  - Network-first for page navigations so dynamic app pages stay fresh.
 *  - Normalize share-target POST bodies; pass other POST requests through.
 *  - Never cache private / user-specific data.
 */
const SHARE_WORKER_VERSION = 'v9';
const CACHE_NAME = 'medlist-shell-v9';

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
    }).then(function () {
      return self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    }).then(function (clientsList) {
      clientsList.forEach(function (client) {
        client.postMessage({
          type: 'SHARE_WORKER_UPDATED',
          version: SHARE_WORKER_VERSION
        });
      });
    })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  var url = new URL(request.url);

  if (url.origin === self.location.origin && request.method === 'POST' &&
      (url.pathname === '/share-target' || url.pathname === '/share')) {
    event.respondWith(forwardSharedDocument(request));
    return;
  }

  // Only handle same-origin GET requests.
  if (request.method !== 'GET') {
    return;
  }
  if (url.origin !== self.location.origin) {
    return;
  }

  // Share settings must come from the current deployment, not the shell cache.
  if (url.pathname === '/static/manifest.json') {
    event.respondWith(fetch(request, { cache: 'no-store' }));
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

function headerValue(headers, name, fallback) {
  const value = headers.get(name);
  return value === null || value === '' ? fallback : value;
}

function clientSummary(userAgent) {
  const chrome = /Chrome\/([\d.]+)/.exec(userAgent || '');
  if (/Android/i.test(userAgent || '')) {
    return 'Android Chrome ' + (chrome ? chrome[1].split('.')[0] : 'unknown');
  }
  if (/iPhone|iPad|iPod/i.test(userAgent || '')) {
    return 'iOS Safari (PWA share target unsupported)';
  }
  return chrome ? 'Chrome ' + chrome[1].split('.')[0] : 'Browser';
}

function createRequestId() {
  if (self.crypto && typeof self.crypto.randomUUID === 'function') {
    return self.crypto.randomUUID();
  }
  if (self.crypto && typeof self.crypto.getRandomValues === 'function') {
    const bytes = new Uint32Array(2);
    self.crypto.getRandomValues(bytes);
    return 'share-' + bytes[0].toString(36) + '-' + bytes[1].toString(36);
  }
  return 'share-unavailable';
}

function diagnosticPage(details) {
  const safeDetails = {};
  Object.keys(details).forEach(function (key) {
    safeDetails[key] = String(details[key] === undefined || details[key] === null ? 'unknown' : details[key]);
  });
  const json = JSON.stringify(safeDetails, null, 2)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return new Response(
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>Share forwarding failed - Med List</title>' +
    '<style>body{font-family:system-ui,sans-serif;max-width:680px;margin:40px auto;padding:20px;line-height:1.5;color:#172033}' +
    'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f9;padding:16px;border-radius:10px}</style>' +
    '<h1>Share forwarding failed</h1><p>No private file content or filenames are shown.</p><pre>' + json + '</pre>',
    { status: 502, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}

async function forwardSharedDocument(request) {
  const requestId = createRequestId();
  const contentType = headerValue(request.headers, 'Content-Type', 'missing');
  const contentLength = headerValue(request.headers, 'Content-Length', 'unknown');
  const client = clientSummary(request.headers.get('User-Agent'));
  let data;
  let parseState = 'parsed';
  let parseError = 'none';
  try {
    data = await request.clone().formData();
  } catch (error) {
    parseState = 'failed';
    parseError = error && error.name ? error.name : 'FormDataError';
    return diagnosticPage({
      'Request ID': requestId,
      'Failure stage': 'Service worker parse',
      'Likely cause': 'The service worker could not parse the incoming share request.',
      'PWA receiver': SHARE_WORKER_VERSION,
      'Client': client,
      'Incoming content type': contentType,
      'Incoming body size': contentLength,
      'FormData parse': parseState,
      'Parse error': parseError
    });
  }

  const body = new FormData();
  let files = 0;
  let fields = 0;
  let hasTitle = false;
  let hasText = false;
  let hasUrl = false;
  for (const [key, value] of data.entries()) {
    if (typeof value === 'string') {
      body.append(key, value);
      fields++;
      if (key === 'title') hasTitle = true;
      if (key === 'text') hasText = true;
      if (key === 'url') hasUrl = true;
    } else {
      body.append('shared_file', value, value.name || 'shared_file');
      files++;
    }
  }

  const payloadState = files > 0 ? 'file' : (hasText ? 'text-only' : (hasTitle || fields > 0 ? 'metadata-only' : 'empty'));
  const failureStage = files > 0 ? 'none' : 'source-share-sheet';
  const forwardHeaders = new Headers({
    'X-Medlist-Share-Worker': SHARE_WORKER_VERSION,
    'X-Medlist-Share-Request-Id': requestId,
    'X-Medlist-Share-Client': client,
    'X-Medlist-Share-Incoming-Type': contentType,
    'X-Medlist-Share-Incoming-Length': contentLength,
    'X-Medlist-Share-Incoming-Files': String(files),
    'X-Medlist-Share-Incoming-Fields': String(fields),
    'X-Medlist-Share-Has-Title': String(hasTitle),
    'X-Medlist-Share-Has-Text': String(hasText),
    'X-Medlist-Share-Has-Url': String(hasUrl),
    'X-Medlist-Share-Parse-State': parseState,
    'X-Medlist-Share-Outgoing-Files': String(files),
    'X-Medlist-Share-Outgoing-Fields': String(fields),
    'X-Medlist-Share-Payload': payloadState,
    'X-Medlist-Share-Failure-Stage': failureStage
  });

  let response;
  try {
    // Fetch creates a matching multipart boundary and serializes the File bytes.
    // No document data is stored in caches or sent to any other origin.
    response = await fetch(new URL('/share-target', self.location.origin).href, {
      method: 'POST', body: body, credentials: 'same-origin', cache: 'no-store',
      headers: forwardHeaders
    });
  } catch (error) {
    return diagnosticPage({
      'Request ID': requestId,
      'Failure stage': 'Service worker to server',
      'Likely cause': 'The service worker could not forward the share request to Flask.',
      'PWA receiver': SHARE_WORKER_VERSION,
      'Client': client,
      'Incoming content type': contentType,
      'Incoming body size': contentLength,
      'Incoming files': String(files),
      'Incoming fields': String(fields),
      'Payload state': payloadState,
      'Outgoing files': String(files),
      'Outgoing fields': String(fields),
      'Forward error': error && error.name ? error.name : 'FetchError'
    });
  }

  const responseHeaders = new Headers(response.headers);
  responseHeaders.set('X-Medlist-Share-Response-Status', String(response.status));
  responseHeaders.set('X-Medlist-Share-Response-Ok', String(response.ok));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders
  });
}
