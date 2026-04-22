import { useEffect, useRef, useState } from "react";
import { getActiveScans, getStatusWebSocketUrl, uploadAndStartScan } from "../services/api";
import { ScanJobStatus } from "../types/scan";

interface UseScanJobState {
  isUploading: boolean;
  currentJobId: string | null;
  activeLimit: number;
  activeScans: ScanJobStatus[];
  status: ScanJobStatus | null;
  error: string | null;
}

export function useScanJob() {
  const [state, setState] = useState<UseScanJobState>({
    isUploading: false,
    currentJobId: null,
    activeLimit: 2,
    activeScans: [],
    status: null,
    error: null
  });

  const socketRef = useRef<WebSocket | null>(null);

  const closeSocket = () => {
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
  };

  const startScan = async (file: File) => {
    closeSocket();
    const idempotencyKey = crypto.randomUUID();
    setState((prev) => ({
      ...prev,
      isUploading: true,
      currentJobId: null,
      status: null,
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
