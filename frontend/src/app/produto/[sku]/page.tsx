import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CATALOG_PRODUCTS, findProduct } from "@/lib/mock-data";
import { ProductPageView } from "@/components/shop/ProductPageView";

interface ProductPageProps {
  params: Promise<{ sku: string }>;
}

export function generateStaticParams(): { sku: string }[] {
  return CATALOG_PRODUCTS.map((product) => ({ sku: product.sku }));
}

export async function generateMetadata({ params }: ProductPageProps): Promise<Metadata> {
  const product = findProduct((await params).sku);
  return { title: product ? `${product.name} — SmartSales RAG` : "Produto não encontrado" };
}

export default async function ProductPage({ params }: ProductPageProps) {
  const product = findProduct((await params).sku);
  if (!product) notFound();
  return <ProductPageView product={product} />;
}
