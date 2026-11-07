export type VoltageType = "127V" | "220V" | "BIVOLT" | "N/A";
export type RecommendationType = "PRIMARY" | "UPSELL" | "CROSS_SELL";
export type MarketplaceType = "AMAZON" | "MERCADO_LIVRE" | "SHOPEE" | "LOJA_OFICIAL";
export type FeedbackRating = "LIKE" | "DISLIKE";

export interface ManualCitation {
  chunk_id: string;
  sku: string;
  manual_title: string;
  page_number: number;
  section_title?: string;
  similarity_score: number;
  excerpt: string;
}

export interface ProductCardData {
  sku: string;
  name: string;
  price: number;
  stock_quantity: number;
  voltage: VoltageType;
  capacity_liters?: number | null;
  power_watts?: number | null;
  image_url: string;
  marketplace: MarketplaceType;
  checkout_url: string;
  recommendation_type: RecommendationType;
  badge_label: string;
  justification: string;
}

export type SSEEventName =
  | "metadata"
  | "token"
  | "correction"
  | "citations"
  | "recommendations"
  | "error"
  | "done";

export type StreamErrorCode =
  | "GUARDRAIL_BLOCKED"
  | "LOW_SIMILARITY_FALLBACK"
  | "LLM_UNAVAILABLE"
  | "INTERNAL_ERROR";

export type FeedbackReasonCategory = "HALLUCINATION" | "WRONG_VOLTAGE" | "SLOW" | "OTHER";

export interface MetricsSummary {
  window: { from: string; to: string };
  turns: number;
  ttft_p50_ms: number;
  ttft_p95_ms: number;
  total_latency_p95_ms: number;
  cache_hit_ratio: number;
  error_5xx_rate: number;
  like_ratio: number;
  card_ctr: number;
  confirmed_checkouts: number;
  top_questions: { question: string; count: number }[];
}

export interface FeedbackCreate {
  session_id: string;
  message_id: string;
  rating: FeedbackRating;
  reason_category?: FeedbackReasonCategory;
}

export interface FeedbackRecorded {
  feedback_id: string;
  status: "RECORDED";
  recorded_at: string;
}

export interface CheckoutCreate {
  session_id: string;
  message_id: string;
  sku: string;
  recommendation_type: RecommendationType;
  quantity: number;
  displayed_price: number;
}

export interface Checkout {
  checkout_event_id: string;
  status: "CONFIRMED";
  sku: string;
  product_name: string;
  voltage: string;
  marketplace: MarketplaceType;
  redirect_checkout_url: string;
  quantity: number;
  confirmed_unit_price: number;
  total_amount: number;
  remaining_stock: number;
  message: string;
}

export interface CheckoutConflict {
  checkout_event_id: string;
  status: "OUT_OF_STOCK" | "PRICE_CHANGED";
  sku: string;
  current_price: number;
  current_stock: number;
  redirect_checkout_url: null;
  message: string;
}

export type StreamEvent =
  | {
      event: "metadata";
      data: {
        message_id: string;
        session_id: string;
        cache_hit: boolean;
        ttft_ms: number;
      };
    }
  | { event: "token"; data: { delta: string } }
  | {
      event: "correction";
      data: { violation_code: "STREAM_INTERRUPTED"; content: string };
    }
  | { event: "citations"; data: { citations: ManualCitation[] } }
  | { event: "recommendations"; data: { products: ProductCardData[] } }
  | {
      event: "error";
      data: {
        code: StreamErrorCode;
        recoverable: boolean;
        fallback_message: string;
      };
    }
  | {
      event: "done";
      data: {
        finish_reason: "stop" | "fallback" | "error";
        total_latency_ms: number;
        tokens_used: number;
      };
    };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming: boolean;
  ttftMs?: number;
  cacheHit?: boolean;
  citations: ManualCitation[];
  recommendations: ProductCardData[];
  feedback?: FeedbackRating | null;
  feedbackReason?: FeedbackReasonCategory | null;
  errorFallback?: string | null;
  errorCode?: StreamErrorCode | null;
  wasCorrected?: boolean;
}
