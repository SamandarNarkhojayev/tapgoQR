const CACHE_NAME = 'video-cache-v1';
const FILES_TO_CACHE = [
    '/static/videos/reklama_800kbps.mp4',
    '/static/videos/reklama_300kbps.mp4',

    '/static/videos/reklama2_800kbps.mp4',
    '/static/videos/reklama2_300kbps.mp4',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Кэширование видео...');
                return cache.addAll(FILES_TO_CACHE);
            })
            .catch((error) => console.error('Ошибка кэширования:', error))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        })
    );
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse;
                }
                return fetch(event.request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        return caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, networkResponse.clone());
                            return networkResponse;
                        });
                    }
                    return networkResponse;
                });
            })
    );
});