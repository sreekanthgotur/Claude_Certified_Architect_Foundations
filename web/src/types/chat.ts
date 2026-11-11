import type { Message } from "./message";

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export interface ChatSession {
  id: string;
  createdAt: number;
  messages: Message[];
}

export interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  currentStreamingMessage: Message | null;
  connectionStatus: ConnectionStatus;
  error: string | null;
}

export interface SendMessagePayload {
  sessionId: string;
  content: string;
  attachments?: string[];
}

export enum MessageType {
  TEXT_CHUNK = "text_chunk",
  MESSAGE_COMPLETE = "message_complete",
  TOOL_USE_START = "tool_use_start",
  TOOL_USE_END = "tool_use_end",
  ESCALATION = "escalation",
  APPROVAL_REQUEST = "approval_request",
  APPROVAL_RESPONSE = "approval_response",
  ERROR = "error",
  HEARTBEAT = "heartbeat",
  USER_MESSAGE = "user_message",
}

export interface WebSocketMessage {
  type: MessageType;
  payload: Record<string, unknown>;
  sequenceId: number;
}

export interface EscalationData {
  summary: string;
  estimatedWait?: string;
  agentName?: string;
}

export interface ApprovalRequestData {
  requestId: string;
  action: string;
  description: string;
  amount?: string;
  consequences?: string;
}
