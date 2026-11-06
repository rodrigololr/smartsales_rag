import { SSEEventName } from "@/types/chat";

export interface ParsedSSEEvent {
  event: SSEEventName;
  data: any;
}

export class SSEBufferParser {
  private buffer: string = "";

  /**
   * Alimenta o parser com novos caracteres do ReadableStream.
   * Retorna array de eventos completamente formados neste ciclo.
   */
  public feed(chunk: string): ParsedSSEEvent[] {
    this.buffer += chunk;
    const events: ParsedSSEEvent[] = [];

    // Normaliza quebras de linha
    const normalized = this.buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const blocks = normalized.split("\n\n");

    // O último bloco pode estar incompleto
    this.buffer = blocks.pop() || "";

    for (const block of blocks) {
      if (!block.trim()) continue;

      let eventName: SSEEventName = "token";
      let dataStr = "";

      const lines = block.split("\n");
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.substring(6).trim() as SSEEventName;
        } else if (line.startsWith("data:")) {
          const content = line.substring(5).trim();
          dataStr = dataStr ? `${dataStr}\n${content}` : content;
        }
      }

      if (dataStr) {
        try {
          const parsedData = JSON.parse(dataStr);
          events.push({ event: eventName, data: parsedData });
        } catch {
          // Se não for JSON válido (ex: texto bruto), encapsula
          events.push({ event: eventName, data: { delta: dataStr } });
        }
      }
    }

    return events;
  }

  public reset(): void {
    this.buffer = "";
  }
}
