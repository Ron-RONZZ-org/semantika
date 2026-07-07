// Polyfill requestAnimationFrame for happy-dom (used by tabStore and popupStore)
if (typeof globalThis.requestAnimationFrame === "undefined") {
  globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 0);
}
