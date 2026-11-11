import { useCallback, useState } from "react";
import { useWebSocket } from "./useWebSocket";
import { useStreamingMessage } from "./useStreamingMessage";
import {
  MessageType,
  type ApprovalRequestData,
  type ConnectionStatus,
  type EscalationData,
  type WebSocketMessage,
} from "@/types/chat";
import type { Message, ToolUseIndicator } from "@/types/message";

interface UseChatReturn {
  messages: Message[];
  isStreaming: boolean;
  connectionStatus: ConnectionStatus;
  escalation: EscalationData | null;
  approvalRequest: ApprovalRequestData | null;
  error: string | null;
  sendMessage: (content: string, attachments?: string[]) => void;
  respondToApproval: (requestId: string, approved: boolean) => void;
  clearEscalation: () => void;
  clearMessages: () => void;
}

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function useChat(wsUrl: string): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [escalation, setEscalation] = useState<EscalationData | null>(null);
  const [approvalRequest, setApprovalRequest] = useState<ApprovalRequestData | null>(null);
  const [activeToolUse, setActiveToolUse] = useState<ToolUseIndicator | null>(null);
  const streaming = useStreamingMessage();
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  const handleMessage = useCallback(
    (wsMessage: WebSocketMessage) => {
      const { type, payload } = wsMessage;

      switch (type) {
        case MessageType.TEXT_CHUNK: {
          const chunk = payload.text as string;
          if (!streamingMessageId) {
            const id = makeId();
            setStreamingMessageId(id);
            streaming.reset();
            setIsStreaming(true);
          }
          streaming.append(chunk);
          break;
        }

        case MessageType.MESSAGE_COMPLETE: {
          const finalContent = streaming.complete();
          const citations = (payload.citations ?? []) as Message["citations"];
          const id = streamingMessageId ?? makeId();

          setMessages((prev) => [
            ...prev,
            {
              id,
              role: "assistant",
              content: finalContent || (payload.text as string) || "",
              citations,
              toolUse: activeToolUse ?? undefined,
              timestamp: Date.now(),
            },
          ]);

          setIsStreaming(false);
          setStreamingMessageId(null);
          setActiveToolUse(null);
          streaming.reset();
          break;
        }

        case MessageType.TOOL_USE_START: {
          const toolName = payload.toolName as string;
          setActiveToolUse({ toolName, status: "running" });
          break;
        }

        case MessageType.TOOL_USE_END: {
          const toolName = payload.toolName as string;
          const result = payload.result as string | undefined;
          const status = payload.error ? "error" : "complete";
          setActiveToolUse({ toolName, status, result });
          break;
        }

        case MessageType.ESCALATION: {
          setEscalation(payload as unknown as EscalationData);
          break;
        }

        case MessageType.APPROVAL_REQUEST: {
          setApprovalRequest(payload as unknown as ApprovalRequestData);
          break;
        }

        case MessageType.ERROR: {
          const errorMsg = (payload.message as string) || "An error occurred";
          setError(errorMsg);
          setIsStreaming(false);
          streaming.reset();
          setStreamingMessageId(null);
          break;
        }

        default:
          break;
      }
    },
    [streaming, streamingMessageId, activeToolUse],
  );

  const { connectionStatus, send } = useWebSocket({
    url: wsUrl,
    onMessage: handleMessage,
  });

  const sendMessage = useCallback(
    (content: string, attachments?: string[]) => {
      const userMessage: Message = {
        id: makeId(),
        role: "user",
        content,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMessage]);
      setError(null);

      send(MessageType.USER_MESSAGE, { content, attachments });
    },
    [send],
  );

  const respondToApproval = useCallback(
    (requestId: string, approved: boolean) => {
      send(MessageType.APPROVAL_RESPONSE, { requestId, approved });
      setApprovalRequest(null);
    },
    [send],
  );

  const clearEscalation = useCallback(() => setEscalation(null), []);
  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
    setEscalation(null);
    setApprovalRequest(null);
  }, []);

  return {
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
  };
}
