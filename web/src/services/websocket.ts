import { MessageType, type WebSocketMessage } from "@/types/chat";

export type MessageHandler = (message: WebSocketMessage) => void;
export type StatusHandler = (status: "connecting" | "connected" | "disconnected" | "error") => void;

export interface WebSocketClientOptions {
  url: string;
  onMessage: MessageHandler;
  onStatusChange: StatusHandler;
}

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private onMessage: MessageHandler;
  private onStatusChange: StatusHandler;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private maxReconnectDelay = 30_000;
  private sequenceCounter = 0;
  private intentionallyClosed = false;

  constructor(options: WebSocketClientOptions) {
    this.url = options.url;
    this.onMessage = options.onMessage;
    this.onStatusChange = options.onStatusChange;
  }

  connect(): void {
    this.intentionallyClosed = false;
    this.onStatusChange("connecting");

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.onStatusChange("error");
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.onStatusChange("connected");
      this.startHeartbeat();
    };

    this.ws.onmessage = (event: globalThis.MessageEvent) => {
      try {
        const message = JSON.parse(String(event.data)) as WebSocketMessage;
        if (message.type === MessageType.HEARTBEAT) return;
        this.onMessage(message);
      } catch {
        // ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      this.onStatusChange("disconnected");
      if (!this.intentionallyClosed) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      this.onStatusChange("error");
    };
  }

  send(type: MessageType, payload: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    const message: WebSocketMessage = {
      type,
      payload,
      sequenceId: this.sequenceCounter++,
    };

    this.ws.send(JSON.stringify(message));
  }

  disconnect(): void {
    this.intentionallyClosed = true;
    this.stopHeartbeat();
    this.clearReconnectTimer();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send(MessageType.HEARTBEAT, {});
    }, 30_000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private scheduleReconnect(): void {
    this.clearReconnectTimer();
    const baseDelay = 1000;
    const delay = Math.min(baseDelay * 2 ** this.reconnectAttempt, this.maxReconnectDelay);
    this.reconnectAttempt++;

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
