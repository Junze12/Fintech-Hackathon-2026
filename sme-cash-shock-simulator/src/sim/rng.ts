// Seeded randomness. All draws in the engine go through this file (no Math.random).

/** FNV-1a 32-bit hash of a string. */
export function fnv1a32(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** mulberry32: returns a generator of uniforms in [0, 1). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Same as `uniform` but takes the already-hashed stream key, so hot loops hash
 * each key once instead of on every draw.
 */
export function uniformHashed(seed: number, run: number, keyHash: number, day: number): number {
  const s =
    (seed ^ Math.imul(run + 1, 0x9e3779b1) ^ keyHash ^ Math.imul(day + 1, 0x85ebca77)) >>> 0;
  return mulberry32(s)();
}

/** u = uniform(seed, run, streamKey, day): the first output of mulberry32 seeded from the four inputs. */
export function uniform(seed: number, run: number, streamKey: string, day: number): number {
  return uniformHashed(seed, run, fnv1a32(streamKey), day);
}

// ---- Beta helpers (acceptance probabilities are stored as Beta(a, b)) ----

/** Prior mean of Beta(alpha, beta). */
export function betaMean(alpha: number, beta: number): number {
  return alpha / (alpha + beta);
}

/** Posterior mean after k acceptances in n past offers: (a + k) / (a + b + n). */
export function betaUpdatedMean(alpha: number, beta: number, k: number, n: number): number {
  return (alpha + k) / (alpha + beta + n);
}
