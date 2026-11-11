import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InputBar } from "@/components/InputBar";

describe("InputBar", () => {
  it("sends on Enter", async () => {
    const onSend = vi.fn();
    render(<InputBar onSend={onSend} />);
    const input = screen.getByLabelText("Message input");
    await userEvent.type(input, "Hello{Enter}");
    expect(onSend).toHaveBeenCalledWith("Hello");
  });

  it("allows newline on Shift+Enter", async () => {
    const onSend = vi.fn();
    render(<InputBar onSend={onSend} />);
    const input = screen.getByLabelText("Message input");
    await userEvent.type(input, "Line 1{Shift>}{Enter}{/Shift}Line 2");
    expect(onSend).not.toHaveBeenCalled();
    expect(input).toHaveValue("Line 1\nLine 2");
  });

  it("disables during streaming", () => {
    render(<InputBar onSend={vi.fn()} disabled={true} />);
    const input = screen.getByLabelText("Message input");
    expect(input).toBeDisabled();
    expect(screen.getByLabelText("Send message")).toBeDisabled();
  });

  it("does not send empty messages", async () => {
    const onSend = vi.fn();
    render(<InputBar onSend={onSend} />);
    await userEvent.click(screen.getByLabelText("Send message"));
    expect(onSend).not.toHaveBeenCalled();
  });
});
