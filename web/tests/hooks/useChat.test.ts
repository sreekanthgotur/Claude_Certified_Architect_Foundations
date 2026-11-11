import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useChat } from "@/hooks/useChat";

describe("useChat", () => {
  it("initializes with empty messages", () => {
    const { result } = renderHook(() => useChat("ws://localhost/ws"));
    expect(result.current.messages).toEqual([]);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("adds a user message on send", () => {
    const { result } = renderHook(() => useChat("ws://localhost/ws"));
    act(() => {
      result.current.sendMessage("Hello");
    });
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.messages[0].content).toBe("Hello");
  });

  it("clears messages", () => {
    const { result } = renderHook(() => useChat("ws://localhost/ws"));
    act(() => {
      result.current.sendMessage("Hello");
    });
    expect(result.current.messages).toHaveLength(1);
    act(() => {
      result.current.clearMessages();
    });
    expect(result.current.messages).toEqual([]);
  });

  it("clears escalation", () => {
    const { result } = renderHook(() => useChat("ws://localhost/ws"));
    expect(result.current.escalation).toBeNull();
    act(() => {
      result.current.clearEscalation();
    });
    expect(result.current.escalation).toBeNull();
  });
});
