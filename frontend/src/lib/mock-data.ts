import type {
  FeedbackReasonCategory,
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

export const CATALOG_PRODUCTS: Product[] = [
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
    image_url: "/images/airfryer-4l.jpg",
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
    image_url: "/images/airfryer-55l.jpg",
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
    image_url: "/images/cafeteira.jpg",
    description:
      "Bomba de 15 bar, bico vaporizador para leite e reservatório removível de 1.5 Litros.",
    features: ["Bomba de 15 bar", "Vaporizador de leite", "Reservatório removível"],
    rating: 4.7,
    reviews_count: 318,
  },
];

/** Catálogo estendido usado apenas pelo motor de recomendação mockado. */
export const RECOMMENDATION_PRODUCTS: Product[] = [
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
    image_url: "/images/airfryer-8l.jpg",
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
    image_url: "/images/kit-silicone.jpg",
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
    image_url: "/images/cafeteira-2l.jpg",
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
    image_url: "/images/kit-cafeteira.jpg",
    description: "Solução descalcificante e escova de limpeza para cafeteiras expresso.",
    features: ["2 aplicações", "Compatível com Aroma Pro", "Fórmula biodegradável"],
    rating: 4.5,
    reviews_count: 63,
  },
];

const ALL_PRODUCTS = [...CATALOG_PRODUCTS, ...RECOMMENDATION_PRODUCTS];

export const findProduct = (sku: string): Product | undefined =>
  ALL_PRODUCTS.find((product) => product.sku === sku);

export const marketplaceOf = (product: Product): MarketplaceType =>
  marketplaceForSku[product.sku] ?? "LOJA_OFICIAL";

export const checkoutUrlOf = (product: Product): string =>
  checkoutUrl(marketplaceOf(product), product.name);

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

const isCafeteira = (product: Product) => product.subcategory === "Cafeteiras";

export const buildRecommendations = (base: Product): ProductCardData[] => {
  const primary = toPrimaryCard(base);
  if (isCafeteira(base)) {
    const upsell = findProduct("CF-20B-127V");
    const cross = findProduct("KIT-CAF-01");
    return [
      primary,
      ...(upsell
        ? [
            toCard(
              upsell,
              "UPSELL",
              "Upgrade Recomendado — Maior Capacidade",
              "Reservatório de 2L e moedor integrado para quem prepara mais cafés por dia."
            ),
          ]
        : []),
      ...(cross
        ? [
            toCard(
              cross,
              "CROSS_SELL",
              "Compre Junto Compatível",
              "Mantém a pressão e o sabor com a descalcificação recomendada pelo fabricante."
            ),
          ]
        : []),
    ];
  }

  const upsell = findProduct("AF-800-220V");
  const cross = findProduct("KIT-SIL-01");
  return [
    primary,
    ...(upsell
      ? [
          toCard(
            upsell,
            "UPSELL",
            "Upgrade Recomendado — Maior Capacidade",
            "Atende famílias maiores com cesto duplo de 8L e painel touch."
          ),
        ]
      : []),
    ...(cross
      ? [
          toCard(
            cross,
            "CROSS_SELL",
            "Compre Junto Compatível",
            "Formas de silicone que preservam o cesto antiaderente no uso diário."
          ),
        ]
      : []),
  ];
};

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
      {
        chunk_id: `c-05-${product.sku}`,
        sku: product.sku,
        manual_title: `Manual ${product.name}`,
        page_number: 5,
        section_title: "Especificações elétricas",
        similarity_score: 0.87,
        excerpt: `Este modelo opera exclusivamente em ${product.voltage} / 60 Hz, com potência nominal de ${product.power_watts ?? 1050} W.`,
      },
    ];
  }

  if (product.capacity_liters && product.capacity_liters >= 5) {
    return [
      {
        chunk_id: `c-18-${product.sku}`,
        sku: product.sku,
        manual_title: `Manual ${product.name}`,
        page_number: 18,
        section_title: "Capacidade e porções",
        similarity_score: 0.92,
        excerpt:
          "O cesto de 5,5 litros comporta até 1,8 kg de batatas pré-preparadas, atendendo de 5 a 6 pessoas com uma única fornada.",
      },
      {
        chunk_id: `c-07-${product.sku}`,
        sku: product.sku,
        manual_title: `Manual ${product.name}`,
        page_number: 7,
        section_title: "Especificações elétricas",
        similarity_score: 0.89,
        excerpt: `Este modelo opera exclusivamente em ${product.voltage} / 60 Hz, com potência nominal de ${product.power_watts ?? 1800} W.`,
      },
    ];
  }

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
    {
      chunk_id: `c-06-${product.sku}`,
      sku: product.sku,
      manual_title: `Manual ${product.name}`,
      page_number: 6,
      section_title: "Especificações elétricas",
      similarity_score: 0.9,
      excerpt: `Este modelo opera exclusivamente em ${product.voltage} / 60 Hz, com potência nominal de ${product.power_watts ?? 1500} W. Não utilize extensões ou adaptadores.`,
    },
  ];
};

export const feedbackReasons: {
  value: FeedbackReasonCategory;
  label: string;
}[] = [
  { value: "HALLUCINATION", label: "Informação imprecisa" },
  { value: "WRONG_VOLTAGE", label: "Voltagem/medida incorreta" },
  { value: "SLOW", label: "Demorou a responder" },
  { value: "OTHER", label: "Outro" },
];

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
