interface TypingIndicatorProps {
  label?: string;
}

export function TypingIndicator({ label }: TypingIndicatorProps) {
  return (
    <div className="flex items-center gap-2 px-4 py-3" role="status" aria-label={label ?? "Agent is typing"}>
      <div className="flex gap-1">
        <span
          className="h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce-dot"
          style={{ animationDelay: "0s" }}
        />
        <span
          className="h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce-dot"
          style={{ animationDelay: "0.16s" }}
        />
        <span
          className="h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce-dot"
          style={{ animationDelay: "0.32s" }}
        />
      </div>
      {label && <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>}
    </div>
  );
}
