import "@testing-library/jest-dom/vitest";

// jsdom lacks these browser APIs used by recharts / framer-motion / theme
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
window.matchMedia = window.matchMedia || ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false }) as unknown as MediaQueryList);
window.scrollTo = (() => {}) as typeof window.scrollTo;
class IO { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } root = null; rootMargin = ""; thresholds = []; }
(globalThis as unknown as { IntersectionObserver: typeof IO }).IntersectionObserver = IO;
