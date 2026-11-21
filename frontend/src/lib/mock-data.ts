import type {
  ManualCitation,
  MarketplaceType,
  MetricsSummary,
  ProductCardData,
} from "@/types/chat";
import type { Product } from "@/types/catalog";

const marketplaceForSku: Record<string, MarketplaceType> = {
  "AF-400-220V": "AMAZON",
  "AF-550-220V": "MERCADO_LIVRE",
  "AF-800-220V": "AMAZON",
  "KIT-SIL-01": "SHOPEE",
  "CF-15B-127V": "LOJA_OFICIAL",
  "CF-20B-127V": "MERCADO_LIVRE",
  "KIT-CAF-01": "SHOPEE",
};

const checkoutUrl = (marketplace: MarketplaceType, name: string): string => {
  const query = encodeURIComponent(name);
  if (marketplace === "AMAZON") return `https://www.amazon.com.br/s?k=${query}`;
  if (marketplace === "MERCADO_LIVRE") return `https://lista.mercadolivre.com.br/${query}`;
  if (marketplace === "SHOPEE") return `https://shopee.com.br/search?keyword=${query}`;
  return `https://smartsales.example.com/produto/${query}`;
};

/** Mock products carry their marketplace link like gateway products do. */
const withStoreLinks = (product: Product): Product => {
  const marketplace = marketplaceForSku[product.sku] ?? "LOJA_OFICIAL";
  return { ...product, marketplace, checkout_url: checkoutUrl(marketplace, product.name) };
};

export const CATALOG_PRODUCTS: Product[] = ([
  {
    sku: "AF-400-220V",
    name: "Airfryer SmartChef 4L",
    brand: "SmartChef",
    category: "Eletroportáteis",
    subcategory: "Fritadeiras Elétricas",
    price: 499.9,
    stock_quantity: 15,
    voltage: "220V",
    capacity_liters: 4.0,
    power_watts: 1500,
    specs_json: { temperatura_min_c: 80, temperatura_max_c: 200, timer_max_min: 60, frequencia_hz: 60 }, // data/catalog.json
    image_url: "/images/airfryer-4l.svg",
    gallery: ["/images/airfryer-4l-painel.svg"],
    description:
      "Fritadeira sem óleo com controle digital de temperatura e cesto antiaderente removível de 4 Litros.",
    features: ["Controle digital", "Cesto antiaderente", "Timer de 60 min"],
    rating: 4.8,
    reviews_count: 1284,
  },
  {
    sku: "AF-550-220V",
    name: "Airfryer SmartChef 5.5L Family",
    brand: "SmartChef",
    category: "Eletroportáteis",
    subcategory: "Fritadeiras Elétricas",
    price: 629.9,
    stock_quantity: 8,
    voltage: "220V",
    capacity_liters: 5.5,
    power_watts: 1800,
    specs_json: { temperatura_min_c: 80, temperatura_max_c: 200, timer_max_min: 60, frequencia_hz: 60 }, // data/catalog.json
    image_url: "/images/airfryer-55l.svg",
    gallery: ["/images/airfryer-55l-painel.svg"],
    description:
      "Capacidade expandida para famílias de até 6 pessoas, timer de 60 minutos e cesto quadrado.",
    features: ["Cesto quadrado", "Capacidade familiar", "Timer de 60 min"],
    rating: 4.9,
    reviews_count: 642,
  },
  {
    sku: "CF-15B-127V",
    name: "Cafeteira Expresso Aroma Pro",
    brand: "AromaTech",
    category: "Eletroportáteis",
    subcategory: "Cafeteiras",
    price: 389.0,
    stock_quantity: 22,
    voltage: "127V",
    capacity_liters: 1.5,
    power_watts: 1050,
    specs_json: { pressao_bar: 15, frequencia_hz: 60 }, // data/catalog.json
    image_url: "/images/cafeteira.svg",
    gallery: ["/images/cafeteira-detalhe.svg"],
    description:
      "Bomba de 15 bar, bico vaporizador para leite e reservatório removível de 1.5 Litros.",
    features: ["Bomba de 15 bar", "Vaporizador de leite", "Reservatório removível"],
    rating: 4.7,
    reviews_count: 318,
  },
] satisfies Product[]).map(withStoreLinks);

/** Catálogo estendido usado apenas pelo motor de recomendação mockado. */
export const RECOMMENDATION_PRODUCTS: Product[] = ([
  {
    sku: "AF-800-220V",
    name: "Airfryer SmartChef 8L Family Plus",
    brand: "SmartChef",
    category: "Eletroportáteis",
    subcategory: "Fritadeiras Elétricas",
    price: 674.9,
    stock_quantity: 6,
    voltage: "220V",
    capacity_liters: 8.0,
    power_watts: 2000,
    image_url: "/images/airfryer-8l.svg",
    description: "Modelo superior com cesto duplo e capacidade para até 8 pessoas.",
    features: ["Cesto duplo", "8 litros", "Painel touch"],
    rating: 4.9,
    reviews_count: 211,
  },
  {
    sku: "KIT-SIL-01",
    name: "Kit de Formas de Silicone 20 cm",
    brand: "SmartChef",
    category: "Acessórios",
    subcategory: "Acessórios para Airfryer",
    price: 79.9,
    stock_quantity: 34,
    voltage: "N/A",
    capacity_liters: null,
    power_watts: null,
    image_url: "/images/kit-silicone.svg",
    description: "Conjunto com 3 formas de silicone compatíveis com airfryers de 4L a 8L.",
    features: ["3 formatos", "Silicone food grade", "Lavável na lava-louças"],
    rating: 4.6,
    reviews_count: 97,
  },
  {
    sku: "CF-20B-127V",
    name: "Cafeteira Expresso Aroma Pro 2L",
    brand: "AromaTech",
    category: "Eletroportáteis",
    subcategory: "Cafeteiras",
    price: 519.0,
    stock_quantity: 9,
    voltage: "127V",
    capacity_liters: 2.0,
    power_watts: 1350,
    specs_json: { pressao_bar: 19 }, // data/catalog.json
    image_url: "/images/cafeteira-2l.svg",
    description: "Versão superior com reservatório de 2L e moedor integrado.",
    features: ["Moedor integrado", "Reservatório 2L", "Pressão de 19 bar"],
    rating: 4.8,
    reviews_count: 144,
  },
  {
    sku: "KIT-CAF-01",
    name: "Kit de Limpeza e Descalcificação",
    brand: "AromaTech",
    category: "Acessórios",
    subcategory: "Acessórios para Cafeteira",
    price: 49.9,
    stock_quantity: 41,
    voltage: "N/A",
    capacity_liters: null,
    power_watts: null,
    image_url: "/images/kit-cafeteira.svg",
    description: "Solução descalcificante e escova de limpeza para cafeteiras expresso.",
    features: ["2 aplicações", "Compatível com Aroma Pro", "Fórmula biodegradável"],
    rating: 4.5,
    reviews_count: 63,
  },
] satisfies Product[]).map(withStoreLinks);

const ALL_PRODUCTS = [...CATALOG_PRODUCTS, ...RECOMMENDATION_PRODUCTS];

export const findProduct = (sku: string): Product | undefined =>
  ALL_PRODUCTS.find((product) => product.sku === sku);

export const marketplaceOf = (product: Product): MarketplaceType =>
  product.marketplace ?? marketplaceForSku[product.sku] ?? "LOJA_OFICIAL";

export const checkoutUrlOf = (product: Product): string =>
  product.checkout_url ?? checkoutUrl(marketplaceOf(product), product.name);

export const toCard = (
  product: Product,
  recommendationType: ProductCardData["recommendation_type"],
  badgeLabel: string,
  justification: string
): ProductCardData => {
  return {
    sku: product.sku,
    name: product.name,
    price: product.price,
    stock_quantity: product.stock_quantity,
    voltage: product.voltage,
    capacity_liters: product.capacity_liters,
    power_watts: product.power_watts,
    image_url: product.image_url,
    marketplace: marketplaceOf(product),
    checkout_url: checkoutUrlOf(product),
    recommendation_type: recommendationType,
    badge_label: badgeLabel,
    justification,
  };
};

export const toPrimaryCard = (product: Product): ProductCardData =>
  toCard(
    product,
    "PRIMARY",
    "Produto Consultado",
    "Item que originou esta conversa e está ancorado no manual oficial."
  );

/** Same ceiling as the backend rule (CLAUDE.md §7: UPSELL_MAX_PRICE_RATIO). */
const UPSELL_MAX_PRICE_RATIO = 1.35;

/** Subcategories the mock can answer about, with their compatible accessory line. */
const MOCK_KNOWLEDGE: Record<string, { accessorySubcategory: string; crossJustification: string }> = {
  "Fritadeiras Elétricas": {
    accessorySubcategory: "Acessórios para Airfryer",
    crossJustification: "Formas de silicone que preservam o cesto antiaderente no uso diário.",
  },
  Cafeteiras: {
    accessorySubcategory: "Acessórios para Cafeteira",
    crossJustification: "Mantém a pressão e o sabor com a descalcificação recomendada pelo fabricante.",
  },
};

export const mockKnowsSubcategory = (product: Product): boolean => product.subcategory in MOCK_KNOWLEDGE;

/** Next tier up in the same subcategory (bigger capacity, pricier, within +35%), in stock. */
const upsellFor = (base: Product): Product | undefined =>
  ALL_PRODUCTS.filter(
    (candidate) =>
      candidate.sku !== base.sku &&
      candidate.subcategory === base.subcategory &&
      candidate.stock_quantity > 0 &&
      (candidate.capacity_liters ?? 0) > (base.capacity_liters ?? 0) &&
      candidate.price > base.price &&
      candidate.price <= base.price * UPSELL_MAX_PRICE_RATIO
  ).sort((a, b) => a.price - b.price)[0];

const crossSellFor = (base: Product): Product | undefined => {
  const knowledge = MOCK_KNOWLEDGE[base.subcategory];
  return ALL_PRODUCTS.find(
    (candidate) =>
      candidate.subcategory === knowledge?.accessorySubcategory && candidate.stock_quantity > 0
  );
};

export const upsellCardOf = (cards: ProductCardData[]): ProductCardData | undefined =>
  cards.find((card) => card.recommendation_type === "UPSELL");

export const buildRecommendations = (base: Product): ProductCardData[] => {
  const upsell = upsellFor(base);
  const cross = crossSellFor(base);
  return [
    toPrimaryCard(base),
    ...(upsell
      ? [
          toCard(
            upsell,
            "UPSELL",
            "Upgrade Recomendado — Maior Capacidade",
            `Capacidade de ${formatLiters(upsell.capacity_liters)}, acima dos ${formatLiters(base.capacity_liters)} deste modelo.`
          ),
        ]
      : []),
    ...(cross
      ? [toCard(cross, "CROSS_SELL", "Compre Junto Compatível", MOCK_KNOWLEDGE[base.subcategory].crossJustification)]
      : []),
  ];
};

const formatLiters = (liters: number | null | undefined): string =>
  `${(liters ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}L`;

/** Demo portions per basket size; only used by the mock answers and their citation. */
export const airfryerServings = (liters: number): string =>
  liters <= 4.5 ? "3 a 4 pessoas" : liters <= 6 ? "5 a 6 pessoas" : "até 8 pessoas";

const electricalCitation = (product: Product, page: number, score: number): ManualCitation => ({
  chunk_id: `c-${String(page).padStart(2, "0")}-${product.sku}`,
  sku: product.sku,
  manual_title: `Manual ${product.name}`,
  page_number: page,
  section_title: "Especificações elétricas",
  similarity_score: score,
  excerpt: `Este modelo opera exclusivamente em ${product.voltage} / 60 Hz, com potência nominal de ${product.power_watts ?? "N/A"} W. Não utilize extensões ou adaptadores.`,
});

/** Mock manual chunks; empty for subcategories the mock does not know (answered with a fallback). */
export const citationsForProduct = (product: Product): ManualCitation[] => {
  if (product.subcategory === "Cafeteiras") {
    return [
      {
        chunk_id: `c-09-${product.sku}`,
        sku: product.sku,
        manual_title: `Manual ${product.name}`,
        page_number: 9,
        section_title: "Limpeza e descalcificação",
        similarity_score: 0.9,
        excerpt:
          "Execute a descalcificação a cada 2 meses ou após 60 ciclos de extração. Utilize apenas a solução descalcificante original diluída em 500 ml de água.",
      },
      electricalCitation(product, 5, 0.87),
    ];
  }
  if (product.subcategory !== "Fritadeiras Elétricas") return [];

  const liters = product.capacity_liters ?? 0;
  return [
    {
      chunk_id: `c-14-${product.sku}`,
      sku: product.sku,
      manual_title: `Manual ${product.name}`,
      page_number: 14,
      section_title: "Materiais e utensílios",
      similarity_score: 0.93,
      excerpt:
        "Formas de alumínio com diâmetro de até 20 cm podem ser utilizadas no cesto, desde que mantida uma folga mínima de 2 cm em relação à resistência superior.",
    },
    electricalCitation(product, 6, 0.9),
    {
      chunk_id: `c-18-${product.sku}`,
      sku: product.sku,
      manual_title: `Manual ${product.name}`,
      page_number: 18,
      section_title: "Capacidade e porções",
      similarity_score: 0.92,
      excerpt: `O cesto de ${formatLiters(liters)} atende ${airfryerServings(liters)} em uma única fornada.`,
    },
  ];
};

export const MOCK_METRICS: MetricsSummary = {
  window: {
    from: "2026-11-01T00:00:00Z",
    to: "2026-11-06T23:59:59Z",
  },
  turns: 247,
  ttft_p50_ms: 780,
  ttft_p95_ms: 1460,
  total_latency_p95_ms: 6120,
  cache_hit_ratio: 0.42,
  error_5xx_rate: 0.004,
  like_ratio: 0.86,
  card_ctr: 0.17,
  confirmed_checkouts: 38,
  top_questions: [
    { question: "A forma de alumínio pode ir na airfryer?", count: 41 },
    { question: "A capacidade de 4L atende 5 pessoas?", count: 33 },
    { question: "Qual a voltagem da cafeteira?", count: 28 },
    { question: "Como limpar o cesto antiaderente?", count: 22 },
    { question: "Qual o prazo de entrega para Maceió?", count: 14 },
  ],
};
