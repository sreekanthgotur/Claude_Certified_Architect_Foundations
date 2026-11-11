import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatWindow } from "@/components/ChatWindow";
import type { Message } from "@/types/message";

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    role: "assistant",
    content: "Hello, how can I help?",
    timestamp: Date.now(),
    ...overrides,
  };
}

describe("ChatWindow", () => {
  it("renders welcome message when empty", () => {
    render(<ChatWindow messages={[]} isStreaming={false} />);
    expect(screen.getByText("How can I help you today?")).toBeInTheDocument();
  });

  it("renders message list", () => {
    const messages: Message[] = [
      makeMessage({ id: "1", role: "user", content: "I need help with my order" }),
      makeMessage({ id: "2", role: "assistant", content: "I can help with that!" }),
    ];
    render(<ChatWindow messages={messages} isStreaming={false} />);
    expect(screen.getByText(/I need help with my order/)).toBeInTheDocument();
    expect(screen.getByText(/I can help with that!/)).toBeInTheDocument();
  });

  it("shows typing indicator when streaming without text", () => {
    render(<ChatWindow messages={[]} isStreaming={true} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows streaming message when streaming with text", () => {
    render(<ChatWindow messages={[]} isStreaming={true} streamingText="Thinking about..." />);
    expect(screen.getByText(/Thinking about.../)).toBeInTheDocument();
  });
});
