import type { Product } from "@/types/catalog";
import type {
  Checkout,
  CheckoutConflict,
  CheckoutCreate,
  FeedbackCreate,
  FeedbackRecorded,
  ManualCitation,
  MetricsSummary,
  ProductCardData,
  StreamErrorCode,
  StreamEvent,
} from "@/types/chat";
import { createId, marketplaceLabel } from "./format";
import {
  buildRecommendations,
  citationsForProduct,
  checkoutUrlOf,
  findProduct,
  marketplaceOf,
  MOCK_METRICS,
} from "./mock-data";

export const ADMIN_DEMO_TOKEN = "admin-demo";

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(createAbortError());
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(createAbortError());
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });

const createAbortError = () => {
  const error = new Error("Requisição cancelada");
  error.name = "AbortError";
  return error;
};

export class MockApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
    this.name = "MockApiError";
  }
}

type MockPlan = {
  answer: string;
  citations: ManualCitation[];
  recommendations: ProductCardData[];
  fallback?: {
    code: StreamErrorCode;
    message: string;
  };
};

const isCafeteira = (product: Product) => product.subcategory === "Cafeteiras";

const planResponse = (product: Product, message: string): MockPlan => {
  const citations = citationsForProduct(product);
  const allCards = buildRecommendations(product);
  const primaryOnly = allCards.slice(0, 1);
  const normalized = message.toLowerCase();

  if (
    /ignore (todas|as) instru|jailbreak|prompt injection|desconsidere|finja que|custa r\$ ?1,00/.test(
      normalized
    )
  ) {
    return {
      answer: "",
      citations: [],
      recommendations: allCards.slice(0, 2),
      fallback: {
        code: "GUARDRAIL_BLOCKED",
        message:
          "Não posso alterar preços, ignorar regras ou responder fora do escopo dos manuais oficiais. Posso ajudar com especificações técnicas, compatibilidade e recomendações de produtos.",
      },
    };
  }

  if (
    /garantia|frete|entrega|prazo|devolu|pol[ií]tica|concorrente|desconto/.test(
      normalized
    )
  ) {
    return {
      answer: "",
      citations: [],
      recommendations: allProductsFallback(product),
      fallback: {
        code: "LOW_SIMILARITY_FALLBACK",
        message:
          "Não encontrei essa informação nos manuais técnicos indexados. Para não arriscar uma resposta imprecisa, recomendo confirmar prazo, garantia ou condições diretamente com o marketplace.",
      },
    };
  }

  if (/pessoa|fam[ií]lia|capacidade|litro|atende|por[cç][oõ]es/.test(normalized)) {
    const answer = isCafeteira(product)
      ? `O reservatório de ${product.capacity_liters ?? 1.5}L rende aproximadamente 12 cafés expresso por envase. Para um uso mais intenso, o modelo de 2L com moedor integrado reduz o número de reabastecimentos ao longo do dia.\n\nTodos os itens sugeridos abaixo estão em estoque e são compatíveis com a voltagem ${product.voltage}.`
      : product.capacity_liters && product.capacity_liters <= 4.5
        ? `O cesto de ${product.capacity_liters}L atende confortavelmente 3 a 4 pessoas. Para famílias de 5 ou 6 pessoas, o upgrade de 5,5L permite uma única fornada com até 1,8 kg de batatas pré-preparadas.\n\nSeparei abaixo o item consultado, um upgrade de maior capacidade e um acessório compatível — todos com estoque disponível.`
        : `O cesto de ${product.capacity_liters}L comporta até 1,8 kg de batatas pré-preparadas e atende de 5 a 6 pessoas em uma única fornada. Para uma rotina com poucas pessoas, o modelo de 4L pode ser suficiente e mais econômico.\n\nVeja abaixo as opções em estoque que selecionei para o seu contexto.`;

    return {
      answer,
      citations: [citations.find((c) => /capacidade|porç|por[cç]/.test(c.section_title ?? "")) ?? citations[0]].filter(Boolean),
      recommendations: allCards,
    };
  }

  if (/alum[ií]nio|forma|assadeira|material|utens[ií]lio|limpar|limpeza|descalc/.test(normalized)) {
    const answer = isCafeteira(product)
      ? `A limpeza diária deve ser feita com pano úmido e a descalcificação a cada 2 meses ou 60 ciclos de extração, usando a solução original diluída em 500 ml de água. Evite vinagre puro para não comprometer as vedações internas.\n\nO kit de limpeza abaixo é compatível com o modelo ${product.name}.`
      : `Pode usar formas de alumínio de até 20 cm de diâmetro no cesto, desde que fique uma folga mínima de 2 cm em relação à resistência superior. Evite utensílios metálicos para não riscar o revestimento antiaderente.\n\nO kit de silicone abaixo é a opção mais segura para o uso diário.`;

    return {
      answer,
      citations: [citations.find((c) => /materiais|limpeza/.test(c.section_title ?? "")) ?? citations[0]].filter(Boolean),
      recommendations: allCards,
    };
  }

  if (/voltagem|tens[aã]o|127|220|bivolt/.test(normalized)) {
    const voltageCitation =
      citations.find((c) => /el[eé]tric/.test(c.section_title ?? "")) ?? citations[0];
    return {
      answer: `A ${product.name} opera exclusivamente em ${product.voltage} / 60 Hz, com potência nominal de ${product.power_watts ?? "N/A"} W. Não utilize extensões ou adaptadores, e confirme a tensão da tomada antes de ligar.\n\nSe precisar de um modelo em outra tensão, posso comparar as opções disponíveis no catálogo.`,
      citations: [voltageCitation].filter(Boolean),
      recommendations: primaryOnly,
    };
  }

  const specs = [
    `Voltagem: ${product.voltage}`,
    product.capacity_liters ? `Capacidade: ${product.capacity_liters}L` : null,
    product.power_watts ? `Potência: ${product.power_watts} W` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return {
    answer: `Sobre a ${product.name}: ${product.description}\n\nEspecificações do manual — ${specs}. O item está em estoque com ${product.stock_quantity} unidades e pode ser adquirido no canal oficial exibido abaixo.`,
    citations: citations.slice(0, 1),
    recommendations: allCards,
  };
};

const allProductsFallback = (product: Product): ProductCardData[] =>
  buildRecommendations(product).slice(0, 2);

const chunkText = (text: string): string[] =>
  text.match(/(?:\S+\s*){1,4}/g) ?? [text];

const seenQuestions = new Set<string>();

export interface MockChatInput {
  sessionId: string;
  message: string;
  product: Product;
}

export async function* streamMockChat(
  input: MockChatInput,
  signal?: AbortSignal
): AsyncGenerator<StreamEvent> {
  const messageId = createId();
  const plan = planResponse(input.product, input.message);
  const cacheKey = `${input.product.sku}:${input.message.trim().toLowerCase()}`;
  const cacheHit = seenQuestions.has(cacheKey);
  seenQuestions.add(cacheKey);
  const startedAt = Date.now();

  await sleep(260, signal);
  yield {
    event: "metadata",
    data: {
      message_id: messageId,
      session_id: input.sessionId,
      cache_hit: cacheHit,
      ttft_ms: 420,
    },
  };

  if (plan.fallback) {
    await sleep(420, signal);
    yield {
      event: "error",
      data: {
        code: plan.fallback.code,
        recoverable: true,
        fallback_message: plan.fallback.message,
      },
    };
    if (plan.recommendations.length) {
      await sleep(140, signal);
      yield {
        event: "recommendations",
        data: { products: plan.recommendations },
      };
    }
    await sleep(100, signal);
    yield {
      event: "done",
      data: {
        finish_reason: "fallback",
        total_latency_ms: Date.now() - startedAt,
        tokens_used: 0,
      },
    };
    return;
  }

  let tokens = 0;
  for (const delta of chunkText(plan.answer)) {
    await sleep(16, signal);
    tokens += delta.split(/\s+/).filter(Boolean).length;
    yield { event: "token", data: { delta } };
  }

  if (plan.citations.length) {
    await sleep(120, signal);
    yield {
      event: "citations",
      data: { citations: plan.citations },
    };
  }

  if (plan.recommendations.length) {
    await sleep(120, signal);
    yield {
      event: "recommendations",
      data: { products: plan.recommendations },
    };
  }

  await sleep(80, signal);
  yield {
    event: "done",
    data: {
      finish_reason: "stop",
      total_latency_ms: Date.now() - startedAt,
      tokens_used: tokens,
    },
  };
}

export async function mockCheckout(
  request: CheckoutCreate,
  signal?: AbortSignal
): Promise<Checkout | CheckoutConflict> {
  await sleep(550, signal);
  const product = findProduct(request.sku);
  if (!product) {
    throw new MockApiError(404, "PRODUCT_NOT_FOUND", "Produto não encontrado no catálogo.");
  }

  const marketplace = marketplaceOf(product);
  const checkoutEventId = createId();

  if (product.stock_quantity <= 0) {
    return {
      checkout_event_id: checkoutEventId,
      status: "OUT_OF_STOCK",
      sku: product.sku,
      current_price: product.price,
      current_stock: 0,
      redirect_checkout_url: null,
      message: "Este item acabou de esgotar. O consultor pode sugerir um substituto em estoque.",
    };
  }

  if (Math.abs(product.price - request.displayed_price) > 0.001) {
    return {
      checkout_event_id: checkoutEventId,
      status: "PRICE_CHANGED",
      sku: product.sku,
      current_price: product.price,
      current_stock: product.stock_quantity,
      redirect_checkout_url: null,
      message: "O preço deste item foi atualizado. Revise o valor antes de concluir.",
    };
  }

  return {
    checkout_event_id: checkoutEventId,
    status: "CONFIRMED",
    sku: product.sku,
    product_name: product.name,
    voltage: product.voltage,
    marketplace,
    redirect_checkout_url: checkoutUrlOf(product),
    quantity: request.quantity,
    confirmed_unit_price: product.price,
    total_amount: Number((product.price * request.quantity).toFixed(2)),
    remaining_stock: Math.max(product.stock_quantity - request.quantity, 0),
    message: `Estoque validado. Abrindo ${marketplaceLabel(marketplace)} em uma nova aba.`,
  };
}

export async function mockFeedback(
  request: FeedbackCreate,
  signal?: AbortSignal
): Promise<FeedbackRecorded> {
  await sleep(280, signal);
  return {
    feedback_id: createId(),
    status: "RECORDED",
    recorded_at: new Date().toISOString(),
  };
}

export async function mockGetMetrics(
  token: string,
  signal?: AbortSignal
): Promise<MetricsSummary> {
  await sleep(450, signal);
  if (!token.trim() || token.trim() !== ADMIN_DEMO_TOKEN) {
    throw new MockApiError(
      401,
      "UNAUTHORIZED",
      "Token administrativo inválido. Use admin-demo no ambiente de demonstração."
    );
  }
  return MOCK_METRICS;
}
