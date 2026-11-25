import type { StreamEvent } from "@/types/chat";

type StreamEventName = StreamEvent["event"];

/** Field each public event must carry; anything else is a protocol violation. */
const REQUIRED_FIELD: Record<StreamEventName, string> = {
  metadata: "message_id",
  token: "delta",
  correction: "content",
  citations: "citations",
  recommendations: "products",
  error: "fallback_message",
  done: "finish_reason",
};

export class SSEProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SSEProtocolError";
  }
}

const isStreamEventName = (name: string): name is StreamEventName =>
  Object.hasOwn(REQUIRED_FIELD, name);

/**
 * Incremental text/event-stream parser (WHATWG rules): LF, CRLF and CR line
 * endings, comments, multi-line data and frames split across chunks.
 * Only the closed SmartSales event set is accepted.
 */
export class SSEParser {
  private buffer = "";
  private eventName = "";
  private dataLines: string[] = [];

  feed(chunk: string): StreamEvent[] {
    this.buffer += chunk;
    const events: StreamEvent[] = [];
    const lineBreak = /\r\n|\r|\n/g;
    let lineStart = 0;
    for (let match = lineBreak.exec(this.buffer); match; match = lineBreak.exec(this.buffer)) {
      // A trailing "\r" may be the first half of a "\r\n" still in flight.
      if (match[0] === "\r" && match.index === this.buffer.length - 1) break;
      this.processLine(this.buffer.slice(lineStart, match.index), events);
      lineStart = lineBreak.lastIndex;
    }
    this.buffer = this.buffer.slice(lineStart);
    return events;
  }

  /** Call at EOF: dispatches a last frame that arrived without its blank line. */
  flush(): StreamEvent[] {
    const events: StreamEvent[] = [];
    if (this.buffer) this.processLine(this.buffer, events);
    this.buffer = "";
    this.processLine("", events);
    return events;
  }

  private processLine(line: string, events: StreamEvent[]): void {
    if (line === "") {
      this.dispatch(events);
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

  private dispatch(events: StreamEvent[]): void {
    const name = this.eventName;
    const data = this.dataLines.join("\n");
    this.eventName = "";
    this.dataLines = [];
    if (!name && !data) return;
    if (!isStreamEventName(name)) throw new SSEProtocolError(`Evento SSE fora do contrato: "${name}"`);

    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      throw new SSEProtocolError(`Payload inválido no evento "${name}"`);
    }
    if (typeof payload !== "object" || payload === null || !(REQUIRED_FIELD[name] in payload)) {
      throw new SSEProtocolError(`Evento "${name}" sem o campo "${REQUIRED_FIELD[name]}"`);
    }
    events.push({ event: name, data: payload } as StreamEvent);
  }
}
