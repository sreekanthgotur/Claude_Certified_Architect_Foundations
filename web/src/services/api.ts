import type { ChatSession } from "@/types/chat";

const BASE_URL = "/api";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "Unknown error");
    throw new ApiError(response.status, body);
  }

  return response.json() as Promise<T>;
}

export async function createSession(): Promise<ChatSession> {
  return request<ChatSession>("/sessions", { method: "POST" });
}

export async function getSessionHistory(sessionId: string): Promise<ChatSession> {
  return request<ChatSession>(`/sessions/${encodeURIComponent(sessionId)}`);
}

export async function exportConversation(sessionId: string): Promise<Blob> {
  const response = await fetch(
    `${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/export`,
  );
  if (!response.ok) {
    throw new ApiError(response.status, "Failed to export conversation");
  }
  return response.blob();
}

export interface UploadUrlResponse {
  uploadUrl: string;
  fileKey: string;
}

export async function getUploadUrl(
  filename: string,
  contentType: string,
): Promise<UploadUrlResponse> {
  return request<UploadUrlResponse>("/uploads/presign", {
    method: "POST",
    body: JSON.stringify({ filename, contentType }),
  });
}
