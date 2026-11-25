import type { MarketplaceType, VoltageType } from "./chat";

/** openapi.yaml `Product` (GET /api/v1/products, /products/{sku}). */
export interface ApiProduct {
  sku: string;
  name: string;
  price: number;
  stock_quantity: number;
  voltage: VoltageType;
  capacity_liters: number | null;
  power_watts: number | null;
  image_url: string;
  marketplace: MarketplaceType;
  checkout_url: string;
  category: string;
  subcategory: string;
  brand: string;
  specs_json: Record<string, unknown>;
  updated_at: string;
  /** Optional free text from the catalog, shown in "Sobre este item". */
  description?: string | null;
}

/** openapi.yaml `Catalog`. */
export interface Catalog {
  items: ApiProduct[];
  page: number;
  page_size: number;
  total: number;
}

/** What the store renders: an `ApiProduct`, or a mock product with display-only extras. */
export interface Product {
  sku: string;
  name: string;
  brand: string;
  category: string;
  subcategory: string;
  price: number;
  stock_quantity: number;
  voltage: VoltageType;
  capacity_liters?: number | null;
  power_watts?: number | null;
  image_url: string;
  /** Present on gateway products; mock products derive them in mock-data. */
  marketplace?: MarketplaceType;
  checkout_url?: string;
  /** Technical sheet from the catalog (`specs_json`); shown as-is, never inferred (R01). */
  specs_json?: Record<string, unknown>;
  /** Extra product photos for the product page gallery (frontend only). */
  gallery?: string[];
  description?: string | null;
  features?: string[];
  rating?: number;
  reviews_count?: number;
}
