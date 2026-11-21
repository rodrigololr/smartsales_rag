import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ApiProduct } from "@/types/catalog";

vi.mock("next/server", () => ({ connection: vi.fn(async () => undefined) }));
const notFound = vi.hoisted(() =>
  vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  })
);
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  notFound,
}));

const API = "http://middleend.test";

const apiProduct = (sku: string, overrides: Partial<ApiProduct> = {}): ApiProduct => ({
  sku,
  name: `Produto ${sku}`,
  price: 499.9,
  stock_quantity: 5,
  voltage: "220V",
  capacity_liters: 4,
  power_watts: 1500,
  image_url: "/images/airfryer-4l.svg",
  marketplace: "AMAZON",
  checkout_url: `https://www.amazon.com.br/s?k=${sku}`,
  category: "Eletroportáteis",
  subcategory: "Fritadeiras Elétricas",
  brand: "SmartChef",
  specs_json: {},
  updated_at: "2026-11-20T10:00:00Z",
  ...overrides,
});

const apiError = (status: number, code: string): Response =>
  Response.json({ error: { code, message: code, trace_id: "t", details: {} } }, { status });

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", API);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("UT-F04-04: catálogo dinâmico do GET /api/v1/products", () => {
  it("percorre todas as páginas com page_size 100", async () => {
    const all = Array.from({ length: 150 }, (_, index) => apiProduct(`SKU-${index}`));
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void init;
      const page = Number(new URL(url).searchParams.get("page"));
      return Response.json({ items: all.slice((page - 1) * 100, page * 100), page, page_size: 100, total: 150 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchCatalog } = await import("@/lib/catalog-api");
    const products = await fetchCatalog();

    expect(products).toHaveLength(150);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      `${API}/api/v1/products?page=1&page_size=100`,
      `${API}/api/v1/products?page=2&page_size=100`,
    ]);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
  });

  it("para depois de ceil(total/page_size) páginas mesmo se o gateway continuar devolvendo itens", async () => {
    let calls = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void init;
      if (++calls > 100) throw new Error("loop sem fim");
      const page = Number(new URL(url).searchParams.get("page"));
      return Response.json({ items: [apiProduct(`SKU-${page}`)], page, page_size: 100, total: 250 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchCatalog } = await import("@/lib/catalog-api");

    expect(await fetchCatalog()).toHaveLength(3);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("tem limite rígido de páginas quando o gateway não informa total", async () => {
    let calls = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void init;
      if (++calls > 1000) throw new Error("loop sem fim");
      const page = Number(new URL(url).searchParams.get("page"));
      return Response.json({ items: [apiProduct(`SKU-${page}`)], page, page_size: 100 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchCatalog } = await import("@/lib/catalog-api");
    await fetchCatalog();

    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(50);
  });

  it("prefere API_INTERNAL_BASE_URL no servidor", async () => {
    vi.stubEnv("API_INTERNAL_BASE_URL", "http://middleend:8000");
    const fetchMock = vi.fn(async () => Response.json({ items: [], page: 1, page_size: 100, total: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    const { fetchCatalog } = await import("@/lib/catalog-api");
    await fetchCatalog();

    expect(fetchMock).toHaveBeenCalledWith("http://middleend:8000/api/v1/products?page=1&page_size=100", expect.anything());
  });

  it("falha do gateway vira ChatApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => apiError(503, "CATALOG_NOT_READY")));

    const { fetchCatalog } = await import("@/lib/catalog-api");
    const { ChatApiError } = await import("@/lib/chat-api");

    await expect(fetchCatalog()).rejects.toBeInstanceOf(ChatApiError);
  });

  it("a vitrine renderiza os produtos do gateway", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ items: [apiProduct("AF-999-220V")], page: 1, page_size: 100, total: 1 }))
    );

    const { default: SmartSalesPage } = await import("@/app/page");
    render(await SmartSalesPage());

    expect(screen.getByTestId("product-card-AF-999-220V")).toHaveAttribute("href", "/produto/AF-999-220V");
  });

  it("a vitrine mostra aviso quando o gateway não responde", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => apiError(503, "CATALOG_NOT_READY")));

    const { default: SmartSalesPage } = await import("@/app/page");
    render(await SmartSalesPage());

    expect(screen.getByTestId("catalog-error")).toHaveTextContent(/catálogo.*indisponível/i);
  });
});

describe("UT-F04-05: produto do GET /api/v1/products/{sku}", () => {
  it("404 vira notFound() do Next", async () => {
    const fetchMock = vi.fn(async () => apiError(404, "PRODUCT_NOT_FOUND"));
    vi.stubGlobal("fetch", fetchMock);

    const { default: ProductPage } = await import("@/app/produto/[sku]/page");

    await expect(ProductPage({ params: Promise.resolve({ sku: "NOPE 1" }) })).rejects.toThrow("NEXT_NOT_FOUND");
    expect(fetchMock).toHaveBeenCalledWith(`${API}/api/v1/products/NOPE%201`, expect.objectContaining({ cache: "no-store" }));
  });

  it("produto esgotado aparece como indisponível, sem compra (R03)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json(apiProduct("AF-000-220V", { stock_quantity: 0 }))));

    const { default: ProductPage } = await import("@/app/produto/[sku]/page");
    render(await ProductPage({ params: Promise.resolve({ sku: "AF-000-220V" }) }));

    expect(screen.getByText("Esgotado")).toBeInTheDocument();
    expect(screen.queryByTestId("buy-btn-AF-000-220V")).not.toBeInTheDocument();
  });

  it("o buy box leva direto ao checkout_url do marketplace, sem mock checkout", async () => {
    const fetchMock = vi.fn(async () => Response.json(apiProduct("AF-777-220V", { marketplace: "SHOPEE" })));
    vi.stubGlobal("fetch", fetchMock);

    const { default: ProductPage } = await import("@/app/produto/[sku]/page");
    render(await ProductPage({ params: Promise.resolve({ sku: "AF-777-220V" }) }));

    const buy = screen.getByTestId("buy-btn-AF-777-220V");
    expect(buy).toHaveTextContent("Comprar na Shopee");
    expect(buy).toHaveAttribute("href", "https://www.amazon.com.br/s?k=AF-777-220V");
    expect(buy).toHaveAttribute("target", "_blank");
    expect(buy.getAttribute("rel")).toContain("noopener");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
