import { memo } from "react";
import type { Message } from "@/types/message";
import { CitationCard } from "./CitationCard";

interface MessageBubbleProps {
  message: Message;
}

function formatTimestamp(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-sm">$1</code>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-brand-primary underline">$1</a>');

  html = html.replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>');
  html = html.replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal">$2</li>');

  html = html.replace(/\n/g, "<br />");

  return html;
}

function MessageBubbleInner({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3 px-4`}
      role="listitem"
    >
      <div
        className={`max-w-[80%] md:max-w-[70%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-brand-primary text-white rounded-br-md"
            : "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-bl-md"
        }`}
      >
        {message.toolUse && (
          <div className="flex items-center gap-2 mb-2 text-xs opacity-75">
            {message.toolUse.status === "running" && (
              <span className="inline-block h-3 w-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
            )}
            <span>
              {message.toolUse.status === "running" ? "Using" : "Used"} {message.toolUse.toolName}
            </span>
          </div>
        )}

        <div
          className="prose prose-sm dark:prose-invert max-w-none break-words"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
        />

        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.citations.map((citation, i) => (
              <CitationCard key={`${citation.documentIndex}-${i}`} citation={citation} index={i} />
            ))}
          </div>
        )}

        {message.isStreaming && (
          <span className="inline-block h-4 w-1 ml-0.5 bg-current animate-pulse" aria-hidden="true" />
        )}

        <div
          className={`mt-1 text-xs ${isUser ? "text-blue-100" : "text-gray-400 dark:text-gray-500"}`}
        >
          {formatTimestamp(message.timestamp)}
        </div>
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleInner);
