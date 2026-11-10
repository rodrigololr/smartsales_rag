import type { StreamEvent } from "@/types/chat";
import { SSEParser } from "@/lib/sse-parser";

/** Middle-end origin. Empty means the UI runs on the local mock API. */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

const MAX_TURN_IN_PROGRESS_WAITS = 3;
const DEFAULT_RETRY_AFTER_SECONDS = 1;

/** Non-retryable HTTP failure, carrying the contract `error.code`. */
export class ChatApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string
  ) {
    super(message);
    this.name = "ChatApiError";
  }
}

/** Connection lost before `done`: the same client_request_id may be resent once. */
export class StreamInterruptedError extends Error {
  constructor() {
    super("A conexão com o consultor caiu antes do fim da resposta.");
    this.name = "StreamInterruptedError";
  }
}

export interface ChatStreamInput {
  sessionId: string;
  clientRequestId: string;
  message: string;
  currentProductSku: string;
}

const isAbort = (error: unknown): boolean =>
  error instanceof Error && error.name === "AbortError";

async function toApiError(response: Response): Promise<ChatApiError> {
  let code = `HTTP_${response.status}`;
  let message = response.statusText;
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string } };
    code = body.error?.code ?? code;
    message = body.error?.message ?? message;
  } catch {
    // Body is not the JSON Error contract (e.g. proxy HTML); keep the HTTP status code.
  }
  return new ChatApiError(response.status, code, message);
}

const waitFor = (milliseconds: number, signal?: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true }
    );
  });

async function fetchOrInterrupt(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new StreamInterruptedError();
  }
}

export async function createSession(
  currentProductSku: string,
  signal?: AbortSignal
): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_product_sku: currentProductSku }),
    signal,
  });
  if (!response.ok) throw await toApiError(response);
  const session = (await response.json()) as { session_id: string };
  return session.session_id;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 404) throw await toApiError(response);
}

async function openChatStream(input: ChatStreamInput, signal?: AbortSignal): Promise<Response> {
  const init: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      session_id: input.sessionId,
      client_request_id: input.clientRequestId,
      message: input.message,
      context_filters: { current_product_sku: input.currentProductSku },
    }),
    signal,
  };
  for (let waits = 0; ; waits++) {
    const response = await fetchOrInterrupt(`${API_BASE_URL}/api/v1/chat/stream`, init);
    if (response.ok) return response;
    const error = await toApiError(response);
    if (error.code !== "TURN_IN_PROGRESS" || waits >= MAX_TURN_IN_PROGRESS_WAITS) throw error;
    const retryAfter = Number(response.headers.get("Retry-After") ?? DEFAULT_RETRY_AFTER_SECONDS);
    await waitFor(1000 * (Number.isFinite(retryAfter) ? retryAfter : DEFAULT_RETRY_AFTER_SECONDS), signal);
  }
}

/** POST /api/v1/chat/stream consumed with fetch + ReadableStream (never EventSource). */
export async function* streamChat(
  input: ChatStreamInput,
  signal?: AbortSignal
): AsyncGenerator<StreamEvent> {
  const response = await openChatStream(input, signal);
  if (!response.body) throw new StreamInterruptedError();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();
  let receivedDone = false;
  try {
    while (!receivedDone) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (error) {
        if (isAbort(error)) throw error;
        throw new StreamInterruptedError();
      }
      const events = chunk.done
        ? [...parser.feed(decoder.decode()), ...parser.flush()]
        : parser.feed(decoder.decode(chunk.value, { stream: true }));
      for (const event of events) {
        yield event;
        if (event.event === "done") receivedDone = true;
      }
      if (chunk.done) break;
    }
  } finally {
    await reader.cancel().catch((error: unknown) => {
      if (!isAbort(error)) console.warn("chat_stream_cancel_failed", error);
    });
  }
  if (!receivedDone) throw new StreamInterruptedError();
}
