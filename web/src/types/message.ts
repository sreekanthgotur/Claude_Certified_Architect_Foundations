export interface Citation {
  citedText: string;
  documentIndex: number;
  sourceLocation: string;
}

export type ToolUseStatus = "running" | "complete" | "error";

export interface ToolUseIndicator {
  toolName: string;
  status: ToolUseStatus;
  result?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  toolUse?: ToolUseIndicator;
  timestamp: number;
  isStreaming?: boolean;
}
