import { useCallback, useRef, useState } from "react";

interface InputBarProps {
  onSend: (text: string) => void;
  onAttach?: () => void;
  disabled?: boolean;
}

const MAX_CHARS = 4000;

export function InputBar({ onSend, onAttach, disabled = false }: InputBarProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value;
      if (value.length <= MAX_CHARS) {
        setText(value);
        adjustHeight();
      }
    },
    [adjustHeight],
  );

  const charCount = text.length;
  const nearLimit = charCount > MAX_CHARS * 0.9;

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="max-w-3xl mx-auto flex items-end gap-2">
        {onAttach && (
          <button
            onClick={onAttach}
            disabled={disabled}
            className="flex-shrink-0 p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400
                       dark:hover:text-gray-200 disabled:opacity-50 rounded-lg
                       hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors
                       focus:outline-none focus:ring-2 focus:ring-brand-primary"
            aria-label="Attach file"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
              <path fillRule="evenodd" d="M15.621 4.379a3 3 0 0 0-4.242 0l-7 7a3 3 0 0 0 4.241 4.243h.001l.497-.5a.75.75 0 0 1 1.064 1.057l-.498.501a4.5 4.5 0 0 1-6.364-6.364l7-7a4.5 4.5 0 0 1 6.368 6.36l-3.455 3.553A2.625 2.625 0 1 1 9.52 9.52l3.45-3.451a.75.75 0 1 1 1.061 1.06l-3.45 3.451a1.125 1.125 0 0 0 1.587 1.595l3.454-3.553a3 3 0 0 0 0-4.242Z" clipRule="evenodd" />
            </svg>
          </button>
        )}

        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={disabled ? "Waiting for response..." : "Type a message..."}
            rows={1}
            className="w-full resize-none rounded-xl border border-gray-300 dark:border-gray-600
                       bg-gray-50 dark:bg-gray-800 px-4 py-3 pr-12 text-sm
                       placeholder:text-gray-400 dark:placeholder:text-gray-500
                       focus:outline-none focus:ring-2 focus:ring-brand-primary focus:border-transparent
                       disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Message input"
          />
          {nearLimit && (
            <span
              className={`absolute bottom-1 right-14 text-xs ${
                charCount >= MAX_CHARS ? "text-red-500" : "text-gray-400"
              }`}
            >
              {charCount}/{MAX_CHARS}
            </span>
          )}
        </div>

        <button
          onClick={handleSend}
          disabled={disabled || text.trim().length === 0}
          className="flex-shrink-0 p-3 bg-brand-primary text-white rounded-xl
                     hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors focus:outline-none focus:ring-2
                     focus:ring-brand-primary focus:ring-offset-2"
          aria-label="Send message"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
            <path d="M3.105 2.288a.75.75 0 0 0-.826.95l1.414 4.926A1.5 1.5 0 0 0 5.135 9.25h6.115a.75.75 0 0 1 0 1.5H5.135a1.5 1.5 0 0 0-1.442 1.086l-1.414 4.926a.75.75 0 0 0 .826.95 28.897 28.897 0 0 0 15.293-7.155.75.75 0 0 0 0-1.114A28.897 28.897 0 0 0 3.105 2.288Z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
