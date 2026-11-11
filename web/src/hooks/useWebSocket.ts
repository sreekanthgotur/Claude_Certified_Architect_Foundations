import { useCallback, useEffect, useRef, useState } from "react";
import { WebSocketClient } from "@/services/websocket";
import { MessageType, type ConnectionStatus, type WebSocketMessage } from "@/types/chat";

interface UseWebSocketOptions {
  url: string;
  onMessage: (message: WebSocketMessage) => void;
  autoConnect?: boolean;
}

interface UseWebSocketReturn {
  connectionStatus: ConnectionStatus;
  send: (type: MessageType, payload: Record<string, unknown>) => void;
  connect: () => void;
  disconnect: () => void;
}

export function useWebSocket({
  url,
  onMessage,
  autoConnect = true,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected");
  const clientRef = useRef<WebSocketClient | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    const client = new WebSocketClient({
      url,
      onMessage: (msg) => onMessageRef.current(msg),
      onStatusChange: setConnectionStatus,
    });
    clientRef.current = client;

    if (autoConnect) {
      client.connect();
    }

    return () => {
      client.disconnect();
    };
  }, [url, autoConnect]);

  const send = useCallback((type: MessageType, payload: Record<string, unknown>) => {
    clientRef.current?.send(type, payload);
  }, []);

  const connect = useCallback(() => {
    clientRef.current?.connect();
  }, []);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
  }, []);

  return { connectionStatus, send, connect, disconnect };
}
