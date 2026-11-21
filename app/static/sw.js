// Minimal service worker: makes QuizDeck installable and shows a page when the server is
// unreachable. API calls and pages are never cached: answers are judged live and the
// session is private.
var OFFLINE = '/static/offline.html';

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open('quizdeck-offline-v1').then(function (cache) {
    return cache.addAll([OFFLINE, '/static/style.css']);
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).catch(function () { return caches.match(OFFLINE); }));
});
