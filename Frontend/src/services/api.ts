import { AuthMeResponse, JobHistoryItem, ScanCreateResponse, ScanJobStatus } from "../types/scan";

const API_BASE = "/api/scans";
const AUTH_BASE = "/api/auth";

function assertOk(response: Response): void {
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

export async function uploadAndStartScan(file: File, idempotencyKey: string): Promise<ScanCreateResponse> {
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(API_BASE, {
    method: "POST",
    body,
    credentials: "include",
    headers: {
      "Idempotency-Key": idempotencyKey
    }
  });
  assertOk(response);
  return (await response.json()) as ScanCreateResponse;
}

export function getStatusWebSocketUrl(jobId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${API_BASE}/ws/${jobId}`;
}

export async function login(username: string, password: string): Promise<AuthMeResponse> {
  const response = await fetch(`${AUTH_BASE}/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  assertOk(response);
  return (await response.json()) as AuthMeResponse;
}

export async function me(): Promise<AuthMeResponse> {
  const response = await fetch(`${AUTH_BASE}/me`, { credentials: "include" });
  assertOk(response);
  return (await response.json()) as AuthMeResponse;
}

export async function logout(): Promise<void> {
  const response = await fetch(`${AUTH_BASE}/logout`, { method: "POST", credentials: "include" });
  assertOk(response);
}

export async function listHistory(): Promise<JobHistoryItem[]> {
  const response = await fetch(`${API_BASE}/history`, { credentials: "include" });
  assertOk(response);
  return (await response.json()) as JobHistoryItem[];
}

export function getDownloadUrl(jobId: string): string {
  return `${API_BASE}/${jobId}/download`;
}

export async function getActiveScans(): Promise<{ active: ScanJobStatus[]; limit: number }> {
  const response = await fetch(`${API_BASE}/active`, { credentials: "include" });
  if (response.status === 401) {
    return { active: [], limit: 3 };
  }
  assertOk(response);
  const data = (await response.json()) as { active: ScanJobStatus[]; limit: number };
  return { active: data.active ?? [], limit: data.limit ?? 3 };
}
