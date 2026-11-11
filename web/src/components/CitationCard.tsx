import { useState } from "react";
import type { Citation } from "@/types/message";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

export function CitationCard({ citation, index }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <span className="inline-block">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="inline-flex items-center justify-center h-5 min-w-[1.25rem] px-1 text-xs font-medium
                   text-brand-primary bg-blue-100 dark:bg-blue-900 dark:text-blue-300
                   rounded hover:bg-blue-200 dark:hover:bg-blue-800 transition-colors"
        aria-label={`Citation ${index + 1}: ${citation.sourceLocation}`}
        aria-expanded={expanded}
      >
        {index + 1}
      </button>

      {expanded && (
        <span
          className="block mt-1 p-2 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200
                     dark:border-gray-700 rounded-md"
        >
          <span className="block text-gray-600 dark:text-gray-300 italic">
            &ldquo;{citation.citedText}&rdquo;
          </span>
          <span className="block mt-1 text-xs text-gray-500 dark:text-gray-400">
            Source: {citation.sourceLocation}
          </span>
        </span>
      )}
    </span>
  );
}
