import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { loadProduct } from "@/lib/catalog-api";
import { ProductPageView } from "@/components/shop/ProductPageView";

interface ProductPageProps {
  params: Promise<{ sku: string }>;
}

export async function generateMetadata({ params }: ProductPageProps): Promise<Metadata> {
  const product = await loadProduct((await params).sku);
  return { title: product ? `${product.name} — SmartSales RAG` : "Produto não encontrado" };
}

export default async function ProductPage({ params }: ProductPageProps) {
  const product = await loadProduct((await params).sku);
  if (!product) notFound();
  return <ProductPageView product={product} />;
}
