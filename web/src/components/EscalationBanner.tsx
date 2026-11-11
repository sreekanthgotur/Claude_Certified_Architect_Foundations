import type { EscalationData } from "@/types/chat";

interface EscalationBannerProps {
  data: EscalationData;
  onContinueWithAI: () => void;
}

export function EscalationBanner({ data, onContinueWithAI }: EscalationBannerProps) {
  return (
    <div
      className="mx-4 my-2 p-4 bg-amber-50 dark:bg-amber-900/30 border border-amber-300
                 dark:border-amber-700 rounded-lg"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl flex-shrink-0" aria-hidden="true">
          &#x1F4DE;
        </span>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-amber-800 dark:text-amber-200">
            Connecting you with a human agent
          </h3>
          <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">{data.summary}</p>
          {data.estimatedWait && (
            <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
              Estimated wait: {data.estimatedWait}
            </p>
          )}
          {data.agentName && (
            <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
              Agent: {data.agentName}
            </p>
          )}
          <button
            onClick={onContinueWithAI}
            className="mt-3 text-sm font-medium text-amber-800 dark:text-amber-200
                       underline hover:no-underline focus:outline-none focus:ring-2
                       focus:ring-amber-500 rounded"
          >
            Continue with AI instead
          </button>
        </div>
      </div>
    </div>
  );
}
