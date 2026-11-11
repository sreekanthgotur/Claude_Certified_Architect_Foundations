import type { ApprovalRequestData } from "@/types/chat";

interface ApprovalCardProps {
  data: ApprovalRequestData;
  onRespond: (requestId: string, approved: boolean) => void;
}

export function ApprovalCard({ data, onRespond }: ApprovalCardProps) {
  return (
    <div
      className="mx-4 my-2 p-4 bg-white dark:bg-gray-800 border-2 border-brand-primary
                 rounded-lg shadow-sm"
      role="dialog"
      aria-label={`Approval required: ${data.action}`}
    >
      <h3 className="font-semibold text-gray-900 dark:text-gray-100">Approval Required</h3>
      <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{data.description}</p>

      {data.amount && (
        <p className="mt-2 text-lg font-bold text-gray-900 dark:text-gray-100">
          Amount: {data.amount}
        </p>
      )}

      {data.consequences && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{data.consequences}</p>
      )}

      <div className="mt-4 flex gap-3">
        <button
          onClick={() => onRespond(data.requestId, true)}
          className="flex-1 px-4 py-2 text-sm font-medium text-white bg-green-600
                     hover:bg-green-700 rounded-md transition-colors
                     focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
        >
          Approve
        </button>
        <button
          onClick={() => onRespond(data.requestId, false)}
          className="flex-1 px-4 py-2 text-sm font-medium text-white bg-red-600
                     hover:bg-red-700 rounded-md transition-colors
                     focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
