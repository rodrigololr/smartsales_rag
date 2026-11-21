import { cache } from "react";
import { connection } from "next/server";
import type { ApiProduct, Catalog, Product } from "@/types/catalog";
import { API_BASE_URL, USE_REAL_API, toApiError } from "@/lib/chat-api";
import { CATALOG_PRODUCTS, findProduct } from "@/lib/mock-data";

const MAX_PAGE_SIZE = 100;

/**
 * Server-side gateway origin. NEXT_PUBLIC_API_BASE_URL is what the browser reaches
 * (e.g. localhost:8000); inside docker the Next server needs the service name instead.
 */
const serverBaseUrl = (): string => process.env.API_INTERNAL_BASE_URL || API_BASE_URL;

/** GET /api/v1/products, every page. Price/stock always fresh from SQL (R09). */
export async function fetchCatalog(): Promise<ApiProduct[]> {
  const products: ApiProduct[] = [];
  for (let page = 1; ; page++) {
    const query = new URLSearchParams({ page: String(page), page_size: String(MAX_PAGE_SIZE) });
    const response = await fetch(`${serverBaseUrl()}/api/v1/products?${query}`, { cache: "no-store" });
    if (!response.ok) throw await toApiError(response);
    const catalog = (await response.json()) as Catalog;
    products.push(...catalog.items);
    if (!catalog.items.length || products.length >= catalog.total) return products;
  }
}

/** GET /api/v1/products/{sku}; `null` on 404. Sold-out products still come back (R03). */
export async function fetchProduct(sku: string): Promise<ApiProduct | null> {
  const response = await fetch(`${serverBaseUrl()}/api/v1/products/${encodeURIComponent(sku)}`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as ApiProduct;
}

/** Store catalog: the gateway when configured, the local mock otherwise. */
export async function loadCatalog(): Promise<Product[]> {
  if (!USE_REAL_API) return CATALOG_PRODUCTS;
  await connection(); // render per request: never fetch the gateway at build time
  return fetchCatalog();
}

/** Deduplicated per request, so generateMetadata and the page share one call. */
export const loadProduct = cache(async (sku: string): Promise<Product | null> => {
  if (!USE_REAL_API) return findProduct(sku) ?? null;
  await connection();
  return fetchProduct(sku);
});
