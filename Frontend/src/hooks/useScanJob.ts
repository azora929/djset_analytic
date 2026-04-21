import { useEffect, useRef, useState } from "react";
import { getActiveScans, getStatusWebSocketUrl, uploadAndStartScan } from "../services/api";
import { ScanJobResult, ScanJobStatus } from "../types/scan";

interface UseScanJobState {
  isUploading: boolean;
  currentJobId: string | null;
  activeLimit: number;
  activeScans: ScanJobStatus[];
  status: ScanJobStatus | null;
  result: ScanJobResult | null;
  error: string | null;
}

export function useScanJob() {
  const keyPrefix = "scan-idempotency:";
  const hashSampleSize = 256 * 1024;
  const [state, setState] = useState<UseScanJobState>({
    isUploading: false,
    currentJobId: null,
    activeLimit: 2,
    activeScans: [],
    status: null,
    result: null,
    error: null
  });

  const socketRef = useRef<WebSocket | null>(null);
  const currentFingerprintRef = useRef<string | null>(null);

  const fingerprintForFile = async (file: File): Promise<string> => {
    const headBuffer = await file.slice(0, hashSampleSize).arrayBuffer();
    const tailStart = Math.max(0, file.size - hashSampleSize);
    const tailBuffer = await file.slice(tailStart, file.size).arrayBuffer();

    const encoder = new TextEncoder();
    const metaBytes = encoder.encode(`${file.name}|${file.type}|${file.size}|${file.lastModified}`);
    const combined = new Uint8Array(metaBytes.length + headBuffer.byteLength + tailBuffer.byteLength);

    combined.set(metaBytes, 0);
    combined.set(new Uint8Array(headBuffer), metaBytes.length);
    combined.set(new Uint8Array(tailBuffer), metaBytes.length + headBuffer.byteLength);

    const digest = await crypto.subtle.digest("SHA-256", combined);
    return Array.from(new Uint8Array(digest))
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
  };

  const getOrCreateIdempotencyKey = (fingerprint: string): string => {
    const storageKey = `${keyPrefix}${fingerprint}`;
    const existing = sessionStorage.getItem(storageKey);
    if (existing) {
      return existing;
    }
    const generated = crypto.randomUUID();
    sessionStorage.setItem(storageKey, generated);
    return generated;
  };

  const clearIdempotencyKey = (fingerprint: string | null): void => {
    if (!fingerprint) {
      return;
    }
    sessionStorage.removeItem(`${keyPrefix}${fingerprint}`);
  };

  const closeSocket = () => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
  };

  const startScan = async (file: File) => {
    closeSocket();
    const fingerprint = await fingerprintForFile(file);
    const idempotencyKey = getOrCreateIdempotencyKey(fingerprint);
    currentFingerprintRef.current = fingerprint;
    setState((prev) => ({
      ...prev,
      isUploading: true,
      currentJobId: null,
      status: null,
      result: null,
      error: null
    }));

    try {
      const created = await uploadAndStartScan(file, idempotencyKey);
      setState((prev) => ({
        ...prev,
        isUploading: false,
        currentJobId: created.job_id
      }));
    } catch (error) {
      clearIdempotencyKey(fingerprint);
      const message = error instanceof Error ? error.message : "Ошибка запуска задачи";
      setState((prev) => ({ ...prev, isUploading: false, error: message }));
    }
  };

  useEffect(() => {
    if (!state.currentJobId) {
      return;
    }
    const jobId = state.currentJobId;
    const socket = new WebSocket(getStatusWebSocketUrl(jobId));
    socketRef.current = socket;

    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as {
          status?: ScanJobStatus;
          result?: { payload?: ScanJobResult["payload"] };
          error?: string;
        };
        if (data.status) {
          setState((prev) => ({
            ...prev,
            status: data.status!,
            activeScans: (() => {
              const rest = prev.activeScans.filter((item) => item.job_id !== data.status!.job_id);
              if (data.status!.status === "queued" || data.status!.status === "running") {
                return [data.status!, ...rest].slice(0, 2);
              }
              return rest;
            })(),
            error: null
          }));
          if (data.status.is_done) {
            clearIdempotencyKey(currentFingerprintRef.current);
          }
        }
        if (data.result) {
          setState((prev) => ({
            ...prev,
            result: {
              status:
                data.status ??
                prev.status ?? {
                  job_id: jobId,
                  status: "running",
                  created_at: new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                  source_file: "",
                  source_size_bytes: 0,
                  progress_pct: 0,
                  total_windows: 0,
                  processed_windows: 0,
                  found_titles: 0
                },
              payload: data.result?.payload ?? null
            }
          }));
        }
        if (data.error) {
          setState((prev) => ({ ...prev, error: data.error! }));
        }
      } catch {
        setState((prev) => ({ ...prev, error: "Некорректный ответ WebSocket" }));
      }
    };

    socket.onerror = () => {
      setState((prev) => ({ ...prev, error: "Ошибка соединения WebSocket" }));
    };

    socket.onclose = () => {
      socketRef.current = null;
    };

    return () => closeSocket();
  }, [state.currentJobId]);

  useEffect(() => () => closeSocket(), []);

  useEffect(() => {
    const syncActive = async () => {
      const { active, limit } = await getActiveScans();
      setState((prev) => {
        const nextCurrentJobId = prev.currentJobId ?? active[0]?.job_id ?? null;
        const nextStatus =
          prev.status && nextCurrentJobId === prev.status.job_id
            ? prev.status
            : active.find((item) => item.job_id === nextCurrentJobId) ?? prev.status;
        return {
          ...prev,
          activeLimit: limit,
          activeScans: active,
          currentJobId: nextCurrentJobId,
          status: nextStatus,
        };
      });
    };

    void syncActive();
    const timer = window.setInterval(() => {
      void syncActive();
    }, 3000);
    return () => window.clearInterval(timer);
  }, []);

  return {
    ...state,
    startScan
  };
}
