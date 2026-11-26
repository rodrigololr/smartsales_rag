/**
 * Closed SSE protocol of `POST /api/v1/chat/stream`
 * (specs/architecture/03_openapi_and_sse_contracts.md, CLAUDE.md §5).
 *
 * The parser is transport-agnostic: it accepts decoded text chunks and yields
 * validated `StreamEvent` objects. It never renders or stores state.
 *
 * @typedef {"metadata" | "token" | "correction" | "citations" | "recommendations" | "error" | "done"} StreamEventName
 * @typedef {Object} ManualCitation
 * @property {string} chunk_id
 * @property {string} sku
 * @property {string} manual_title
 * @property {number} page_number
 * @property {string} [section_title]
 * @property {number} similarity_score
 * @property {string} excerpt
 * @typedef {"PRIMARY" | "UPSELL" | "CROSS_SELL" | "OPTION"} RecommendationType
 * @typedef {"AMAZON" | "MERCADO_LIVRE" | "SHOPEE" | "LOJA_OFICIAL"} MarketplaceType
 * @typedef {"127V" | "220V" | "BIVOLT" | "N/A"} VoltageType
 * @typedef {Object} ProductCardData
 * @property {string} sku
 * @property {string} name
 * @property {number} price
 * @property {number} stock_quantity
 * @property {VoltageType} voltage
 * @property {number | null} [capacity_liters]
 * @property {number | null} [power_watts]
 * @property {string} image_url
 * @property {MarketplaceType} marketplace
 * @property {string} checkout_url
 * @property {RecommendationType} recommendation_type
 * @property {string} badge_label
 * @property {string} justification
 * @typedef {"GUARDRAIL_BLOCKED" | "LOW_SIMILARITY_FALLBACK" | "LLM_UNAVAILABLE" | "INTERNAL_ERROR"} StreamErrorCode
 * @typedef {(
 *   { event: "metadata", data: { message_id: string, session_id: string, cache_hit: boolean, ttft_ms: number } } |
 *   { event: "token", data: { delta: string } } |
 *   { event: "correction", data: { violation_code: "STREAM_INTERRUPTED", content: string } } |
 *   { event: "citations", data: { citations: ManualCitation[] } } |
 *   { event: "recommendations", data: { products: ProductCardData[] } } |
 *   { event: "error", data: { code: StreamErrorCode, recoverable: boolean, fallback_message: string } } |
 *   { event: "done", data: { finish_reason: "stop" | "fallback" | "error", total_latency_ms: number, tokens_used: number } }
 * )} StreamEvent
 */

/** @type {readonly StreamEventName[]} */
export const STREAM_EVENT_NAMES = Object.freeze([
  "metadata",
  "token",
  "correction",
  "citations",
  "recommendations",
  "error",
  "done",
]);

/** Field each public event must carry; anything else is a protocol violation. */
const REQUIRED_FIELD = Object.freeze({
  metadata: "message_id",
  token: "delta",
  correction: "content",
  citations: "citations",
  recommendations: "products",
  error: "fallback_message",
  done: "finish_reason",
});

export class SSEProtocolError extends Error {
  /**
   * @param {string} message
   */
  constructor(message) {
    super(message);
    this.name = "SSEProtocolError";
  }
}

/**
 * @param {string} name
 * @returns {name is StreamEventName}
 */
export const isStreamEventName = (name) =>
  Object.hasOwn(REQUIRED_FIELD, name);

/**
 * Incremental text/event-stream parser (WHATWG rules): LF, CRLF and CR line
 * endings, comments, multi-line data and frames split across chunks.
 * Only the SmartSales closed event set is accepted.
 */
export class SSEParser {
  constructor() {
    /** @type {string} */
    this.buffer = "";
    /** @type {string} */
    this.eventName = "";
    /** @type {string[]} */
    this.dataLines = [];
  }

  /**
   * @param {string} chunk
   * @returns {StreamEvent[]}
   */
  feed(chunk) {
    this.buffer += chunk;
    /** @type {StreamEvent[]} */
    const events = [];
    const lineBreak = /\r\n|\r|\n/g;
    let lineStart = 0;
    for (let match = lineBreak.exec(this.buffer); match; match = lineBreak.exec(this.buffer)) {
      // A trailing "\r" may be the first half of a "\r\n" still in flight.
      if (match[0] === "\r" && match.index === this.buffer.length - 1) break;
      this.#processLine(this.buffer.slice(lineStart, match.index), events);
      lineStart = lineBreak.lastIndex;
    }
    this.buffer = this.buffer.slice(lineStart);
    return events;
  }

  /** Call at EOF: dispatches a last frame that arrived without its blank line. */
  flush() {
    /** @type {StreamEvent[]} */
    const events = [];
    if (this.buffer) this.#processLine(this.buffer, events);
    this.buffer = "";
    this.#processLine("", events);
    return events;
  }

  /**
   * @param {string} line
   * @param {StreamEvent[]} events
   */
  #processLine(line, events) {
    if (line === "") {
      this.#dispatch(events);
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    const rawValue = colon < 0 ? "" : line.slice(colon + 1);
    const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
    if (field === "event") this.eventName = value;
    else if (field === "data") this.dataLines.push(value);
  }

  /**
   * @param {StreamEvent[]} events
   */
  #dispatch(events) {
    const name = this.eventName;
    const data = this.dataLines.join("\n");
    this.eventName = "";
    this.dataLines = [];
    if (!name && !data) return;
    if (!isStreamEventName(name)) {
      throw new SSEProtocolError(`Evento SSE fora do contrato: "${name}"`);
    }

    /** @type {unknown} */
    let payload;
    try {
      payload = JSON.parse(data);
    } catch {
      throw new SSEProtocolError(`Payload inválido no evento "${name}"`);
    }
    if (
      typeof payload !== "object" ||
      payload === null ||
      Array.isArray(payload) ||
      !(REQUIRED_FIELD[name] in payload)
    ) {
      throw new SSEProtocolError(`Evento "${name}" sem o campo "${REQUIRED_FIELD[name]}"`);
    }
    events.push(/** @type {StreamEvent} */ ({ event: name, data: payload }));
  }
}
