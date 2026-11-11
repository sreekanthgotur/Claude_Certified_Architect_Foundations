import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageBubble } from "@/components/MessageBubble";
import type { Message } from "@/types/message";

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    role: "assistant",
    content: "Hello there!",
    timestamp: Date.now(),
    ...overrides,
  };
}

describe("MessageBubble", () => {
  it("renders user message", () => {
    render(<MessageBubble message={makeMessage({ role: "user", content: "Hi" })} />);
    expect(screen.getByText("Hi")).toBeInTheDocument();
  });

  it("renders assistant message", () => {
    render(<MessageBubble message={makeMessage({ content: "How can I help?" })} />);
    expect(screen.getByText(/How can I help?/)).toBeInTheDocument();
  });

  it("renders bold markdown", () => {
    render(<MessageBubble message={makeMessage({ content: "This is **bold** text" })} />);
    const strong = document.querySelector("strong");
    expect(strong).toBeInTheDocument();
    expect(strong?.textContent).toBe("bold");
  });

  it("shows citations when present", () => {
    render(
      <MessageBubble
        message={makeMessage({
          citations: [{ citedText: "Some fact", documentIndex: 0, sourceLocation: "doc.pdf" }],
        })}
      />,
    );
    expect(screen.getByLabelText(/Citation 1/)).toBeInTheDocument();
  });

  it("shows tool-use indicator", () => {
    render(
      <MessageBubble
        message={makeMessage({
          toolUse: { toolName: "lookup_order", status: "running" },
        })}
      />,
    );
    expect(screen.getByText(/lookup_order/)).toBeInTheDocument();
  });
});
