// Incrementar em cada release: o activate apaga todas as caches com outro nome.
const CACHE_VERSION = "financas-v4";
const PRECACHE = ["./", "./index.html", "./manifest.json", "./icons/icon-192.png", "./icons/icon-512.png"];
// Ficheiros que têm de estar sempre na versão mais recente quando há rede.
const NETWORK_FIRST = ["/", "/index.html", "/manifest.json", "/sw.js"];

self.addEventListener("install", (e) => {
  // cache: "reload" evita que o precache venha da cache HTTP do browser
  e.waitUntil(
    caches.open(CACHE_VERSION).then((c) => c.addAll(PRECACHE.map((u) => new Request(u, { cache: "reload" }))))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function putInCache(request, response) {
  if (response && response.ok && response.type === "basic") {
    const copy = response.clone();
    caches.open(CACHE_VERSION).then((c) => c.put(request, copy));
  }
  return response;
}

// Com rede: sempre a versão mais recente (e atualiza a cache). Sem rede: a cache, para abrir offline.
async function networkFirst(request) {
  try {
    return putInCache(request, await fetch(request, { cache: "no-cache" }));
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") {
      return (await caches.match("./index.html")) || (await caches.match("./"));
    }
    throw err;
  }
}

// Responde já com a cache e atualiza-a em segundo plano.
async function staleWhileRevalidate(event) {
  const cached = await caches.match(event.request);
  const network = fetch(event.request).then((res) => putInCache(event.request, res));
  if (cached) {
    event.waitUntil(network.catch(() => {}));
    return cached;
  }
  return network;
}

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // API nunca vai a cache

  if (e.request.mode === "navigate" || NETWORK_FIRST.includes(url.pathname)) {
    e.respondWith(networkFirst(e.request));
  } else {
    e.respondWith(staleWhileRevalidate(e));
  }
});
