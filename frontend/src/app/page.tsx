import { unstable_rethrow } from "next/navigation";
import { CatalogView } from "@/components/catalog/CatalogView";
import { loadCatalog } from "@/lib/catalog-api";
import type { Product } from "@/types/catalog";

export default async function SmartSalesPage() {
  let products: Product[];
  try {
    products = await loadCatalog();
  } catch (error) {
    unstable_rethrow(error); // Next's own control-flow errors (dynamic render) must propagate
    console.error("catalog_load_failed", error);
    return <CatalogView products={[]} unavailable />;
  }
  return <CatalogView products={products} />;
}
