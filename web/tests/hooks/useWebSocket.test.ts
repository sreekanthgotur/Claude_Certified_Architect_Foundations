import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useWebSocket } from "@/hooks/useWebSocket";

describe("useWebSocket", () => {
  it("starts in disconnected state before connecting", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useWebSocket({ url: "ws://localhost/ws", onMessage, autoConnect: false }),
    );
    expect(result.current.connectionStatus).toBe("disconnected");
  });

  it("provides send, connect, and disconnect functions", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      useWebSocket({ url: "ws://localhost/ws", onMessage, autoConnect: false }),
    );
    expect(typeof result.current.send).toBe("function");
    expect(typeof result.current.connect).toBe("function");
    expect(typeof result.current.disconnect).toBe("function");
  });
});
