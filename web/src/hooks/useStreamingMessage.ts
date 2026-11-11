import { useCallback, useRef, useState } from "react";

interface UseStreamingMessageReturn {
  text: string;
  isComplete: boolean;
  append: (chunk: string) => void;
  complete: () => string;
  reset: () => void;
}

export function useStreamingMessage(): UseStreamingMessageReturn {
  const [text, setText] = useState("");
  const [isComplete, setIsComplete] = useState(false);
  const bufferRef = useRef("");

  const append = useCallback((chunk: string) => {
    bufferRef.current += chunk;
    setText(bufferRef.current);
    setIsComplete(false);
  }, []);

  const complete = useCallback((): string => {
    const finalText = bufferRef.current;
    setIsComplete(true);
    return finalText;
  }, []);

  const reset = useCallback(() => {
    bufferRef.current = "";
    setText("");
    setIsComplete(false);
  }, []);

  return { text, isComplete, append, complete, reset };
}
