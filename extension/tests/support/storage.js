/**
 * Minimal `browser.storage.*` area double.
 *
 * @param {Record<string, unknown>} [initial]
 * @returns {{
 *   data: Record<string, unknown>,
 *   get: (keys?: string | string[] | null) => Promise<Record<string, unknown>>,
 *   set: (items: Record<string, unknown>) => Promise<void>,
 *   remove: (keys: string | string[]) => Promise<void>,
 *   clear: () => Promise<void>,
 * }}
 */
export function fakeStorageArea(initial = {}) {
  const data = structuredClone(initial);
  return {
    data,
    async get(keys) {
      if (keys === undefined || keys === null) return structuredClone(data);
      const requested = Array.isArray(keys) ? keys : [keys];
      /** @type {Record<string, unknown>} */
      const result = {};
      for (const key of requested) {
        if (Object.hasOwn(data, key)) result[key] = structuredClone(data[key]);
      }
      return result;
    },
    async set(items) {
      Object.assign(data, structuredClone(items));
    },
    async remove(keys) {
      for (const key of Array.isArray(keys) ? keys : [keys]) delete data[key];
    },
    async clear() {
      for (const key of Object.keys(data)) delete data[key];
    },
  };
}

/** @param {number} index */
export const uuid = (index) =>
  `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
