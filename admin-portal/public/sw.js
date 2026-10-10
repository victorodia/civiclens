// Service-worker removal shim.
//
// These portals previously shipped a vite-plugin-pwa (workbox) service
// worker. It has been removed: a stale copy already installed in a browser
// would keep serving DELETED app bundles (users ran old, buggy builds and
// fresh deploys never reached them — the browser update check is throttled).
// This shim replaces it: on activation it drops every cache the old worker
// created, unregisters itself, and reloads open pages so the new bundle
// loads directly from the network on the next visit.
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', () => {
    caches.keys()
        .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
        .then(() => self.registration.unregister())
        .then(() => self.clients.matchAll({ includeUncontrolled: true }))
        .then((clients) => clients.forEach((c) => c.navigate(c.url)));
});
