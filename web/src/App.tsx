import { useCallback, useState } from "react";
import { Header } from "@/components/Header";
import { ChatWindow } from "@/components/ChatWindow";
import { InputBar } from "@/components/InputBar";
import { EscalationBanner } from "@/components/EscalationBanner";
import { ApprovalCard } from "@/components/ApprovalCard";
import { FileUpload } from "@/components/FileUpload";
import { useChat } from "@/hooks/useChat";
import { useStreamingMessage } from "@/hooks/useStreamingMessage";
import { exportConversation } from "@/services/api";

function buildWsUrl(sessionId: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/chat/${sessionId}`;
}

export function App() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const wsUrl = buildWsUrl(sessionId);

  const {
    messages,
    isStreaming,
    connectionStatus,
    escalation,
    approvalRequest,
    error,
    sendMessage,
    respondToApproval,
    clearEscalation,
    clearMessages,
  } = useChat(wsUrl);

  const streaming = useStreamingMessage();
  const [showUpload, setShowUpload] = useState(false);

  const handleNewChat = useCallback(() => {
    clearMessages();
    streaming.reset();
  }, [clearMessages, streaming]);

  const handleExport = useCallback(async () => {
    try {
      const blob = await exportConversation(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `conversation-${sessionId.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // export not available in stub mode
    }
  }, [sessionId]);

  const handleAttach = useCallback(() => {
    setShowUpload((prev) => !prev);
  }, []);

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto bg-white dark:bg-gray-900">
      <Header onNewChat={handleNewChat} onExport={handleExport} />

      {connectionStatus === "error" && (
        <div className="px-4 py-2 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm text-center">
          Connection error. Reconnecting...
        </div>
      )}

      {connectionStatus === "disconnected" && (
        <div className="px-4 py-2 bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 text-sm text-center">
          Disconnected. Reconnecting...
        </div>
      )}

      {error && (
        <div className="px-4 py-2 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm text-center" role="alert">
          {error}
        </div>
      )}

      {escalation && (
        <EscalationBanner data={escalation} onContinueWithAI={clearEscalation} />
      )}

      {approvalRequest && (
        <ApprovalCard data={approvalRequest} onRespond={respondToApproval} />
      )}

      <ChatWindow
        messages={messages}
        isStreaming={isStreaming}
        streamingText={streaming.text || undefined}
      />

      {showUpload && (
        <div className="px-4 pb-2">
          <FileUpload
            onFileUploaded={(file) => {
              sendMessage(`[Attached: ${file.name}]`, [file.key]);
              setShowUpload(false);
            }}
          />
        </div>
      )}

      <InputBar
        onSend={sendMessage}
        onAttach={handleAttach}
        disabled={isStreaming || connectionStatus !== "connected"}
      />
    </div>
  );
}
