import { describe, expect, it } from "vitest";
import { SSEParser, SSEProtocolError } from "@/lib/sse-parser";

const done = { finish_reason: "stop", total_latency_ms: 10, tokens_used: 3 };

describe("SSEParser", () => {
  it("parses LF frames and keeps an incomplete frame for the next chunk", () => {
    const parser = new SSEParser();
    expect(parser.feed('event: token\ndata: {"delta":"Ol')).toEqual([]);
    expect(parser.feed('á"}\n\nevent: done\n')).toEqual([
      { event: "token", data: { delta: "Olá" } },
    ]);
    expect(parser.feed(`data: ${JSON.stringify(done)}\n\n`)).toEqual([
      { event: "done", data: done },
    ]);
  });

  it("keeps the event name when a CRLF is split across chunks", () => {
    const parser = new SSEParser();
    expect(parser.feed("event: done\r")).toEqual([]);
    expect(parser.feed(`\ndata: ${JSON.stringify(done)}\r\n\r\n`)).toEqual([
      { event: "done", data: done },
    ]);
  });

  it("accepts CR-only line endings, comments, data without space and multi-line data", () => {
    const parser = new SSEParser();
    // The last "\r" could still become "\r\n", so the frame is only closed at EOF.
    const frames = [
      ...parser.feed(': keep-alive\revent:token\rdata:{"delta":\rdata: "a"}\r\r'),
      ...parser.flush(),
    ];
    expect(frames).toEqual([{ event: "token", data: { delta: "a" } }]);
  });

  it("flushes a final frame that arrives without the trailing blank line", () => {
    const parser = new SSEParser();
    expect(parser.feed(`event: done\ndata: ${JSON.stringify(done)}`)).toEqual([]);
    expect(parser.flush()).toEqual([{ event: "done", data: done }]);
  });

  it("rejects events outside the closed contract set", () => {
    expect(() => new SSEParser().feed('event: ping\ndata: {}\n\n')).toThrow(SSEProtocolError);
    expect(() => new SSEParser().feed('data: {"delta":"x"}\n\n')).toThrow(SSEProtocolError);
  });

  it("rejects payloads that are not JSON or miss the required field", () => {
    expect(() => new SSEParser().feed("event: token\ndata: texto cru\n\n")).toThrow(
      SSEProtocolError
    );
    expect(() => new SSEParser().feed('event: token\ndata: {"text":"x"}\n\n')).toThrow(
      SSEProtocolError
    );
  });
});
