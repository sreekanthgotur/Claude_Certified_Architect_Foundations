import { useEffect, useRef } from "react";
import type { Message } from "@/types/message";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

interface ChatWindowProps {
  messages: Message[];
  isStreaming: boolean;
  streamingText?: string;
}

export function ChatWindow({ messages, isStreaming, streamingText }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingText]);

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center max-w-md">
          <div className="text-5xl mb-4" aria-hidden="true">
            &#x1F4AC;
          </div>
          <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
            How can I help you today?
          </h2>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            I can help with orders, account questions, returns, and more.
            Type your question below to get started.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto scrollbar-thin py-4"
      role="list"
      aria-label="Chat messages"
    >
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {isStreaming && streamingText && (
        <MessageBubble
          message={{
            id: "streaming",
            role: "assistant",
            content: streamingText,
            timestamp: Date.now(),
            isStreaming: true,
          }}
        />
      )}

      {isStreaming && !streamingText && <TypingIndicator />}

      <div ref={bottomRef} />
    </div>
  );
}
