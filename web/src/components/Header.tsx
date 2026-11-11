import { useCallback, useEffect, useState } from "react";

interface HeaderProps {
  onNewChat: () => void;
  onExport: () => void;
}

export function Header({ onNewChat, onExport }: HeaderProps) {
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("theme") === "dark";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      // storage unavailable
    }
  }, [dark]);

  const toggleDark = useCallback(() => setDark((prev) => !prev), []);

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      <div className="flex items-center gap-2">
        <span className="text-xl" aria-hidden="true">&#x1F916;</span>
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Support Agent
        </h1>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onNewChat}
          className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300
                     bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200
                     dark:hover:bg-gray-700 transition-colors focus:outline-none
                     focus:ring-2 focus:ring-brand-primary"
        >
          New Chat
        </button>

        <button
          onClick={onExport}
          className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300
                     bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200
                     dark:hover:bg-gray-700 transition-colors focus:outline-none
                     focus:ring-2 focus:ring-brand-primary"
        >
          Export
        </button>

        <button
          onClick={toggleDark}
          className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700
                     dark:hover:text-gray-200 rounded-lg hover:bg-gray-100
                     dark:hover:bg-gray-800 transition-colors focus:outline-none
                     focus:ring-2 focus:ring-brand-primary"
          aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
        >
          {dark ? (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
              <path d="M10 2a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0v-1.5A.75.75 0 0 1 10 2ZM10 15a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0v-1.5A.75.75 0 0 1 10 15ZM10 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM15.657 5.404a.75.75 0 1 0-1.06-1.06l-1.061 1.06a.75.75 0 0 0 1.06 1.06l1.06-1.06ZM6.464 14.596a.75.75 0 1 0-1.06-1.06l-1.06 1.06a.75.75 0 0 0 1.06 1.06l1.06-1.06ZM18 10a.75.75 0 0 1-.75.75h-1.5a.75.75 0 0 1 0-1.5h1.5A.75.75 0 0 1 18 10ZM5 10a.75.75 0 0 1-.75.75h-1.5a.75.75 0 0 1 0-1.5h1.5A.75.75 0 0 1 5 10ZM14.596 15.657a.75.75 0 0 0 1.06-1.06l-1.06-1.061a.75.75 0 1 0-1.06 1.06l1.06 1.06ZM5.404 6.464a.75.75 0 0 0 1.06-1.06l-1.06-1.06a.75.75 0 1 0-1.06 1.06l1.06 1.06Z" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
              <path fillRule="evenodd" d="M7.455 2.004a.75.75 0 0 1 .26.77 7 7 0 0 0 9.958 7.967.75.75 0 0 1 1.067.853A8.5 8.5 0 1 1 6.647 1.921a.75.75 0 0 1 .808.083Z" clipRule="evenodd" />
            </svg>
          )}
        </button>
      </div>
    </header>
  );
}
