import { useEffect, useState } from "react";
import { AuthModal } from "./components/AuthModal";
import { FileDropzone } from "./components/FileDropzone";
import { HistoryPanel } from "./components/HistoryPanel";
import { useAuth } from "./hooks/useAuth";
import { useScanJob } from "./hooks/useScanJob";
import { listHistory } from "./services/api";
import { JobHistoryItem } from "./types/scan";
import "./styles/App.scss";

export default function App() {
  const { username, loading: authLoading, error: authError, signIn, signOut } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const { startScan, isUploading, activeScans, activeLimit, status, error } = useScanJob();
  const [history, setHistory] = useState<JobHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const activeSummary = activeScans.slice(0, activeLimit);
  const activeSignature = activeScans
    .map((item) => `${item.job_id}:${item.status}:${item.stage}:${item.processed_windows}`)
    .join("|");

  const refreshHistory = async () => {
    setHistoryLoading(true);
    try {
      const data = await listHistory();
      setHistory(data);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (username) {
      void refreshHistory();
    }
  }, [username]);

  useEffect(() => {
    if (username && status?.is_done) {
      void refreshHistory();
    }
  }, [username, status?.is_done]);

  useEffect(() => {
    if (username) {
      void refreshHistory();
    }
  }, [username, activeSignature]);

  useEffect(() => {
    if (!username) {
      setHistory([]);
      return;
    }
    const timer = window.setInterval(() => {
      void refreshHistory();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [username]);

  const busy = isUploading || activeScans.length >= activeLimit;

  return (
    <main className="page">
      {!authLoading && !username ? <AuthModal error={authError} onSubmit={signIn} /> : null}
      <section className="card">
        <div className="header-row">
          <h1>DJSet AudioTag Analyzer</h1>
          {username ? (
            <button className="primary-btn" onClick={() => void signOut()}>
              Выйти
            </button>
          ) : null}
        </div>
        <p className="lead">
          Загрузи большой аудиофайл, сервер порежет его на окна, прогонит через AudioTag с автопереключением API-ключей и
          сохранит результаты.
        </p>

        <FileDropzone file={selectedFile} disabled={busy} onFileSelect={setSelectedFile} />

        <button
          className="primary-btn"
          disabled={!selectedFile || busy || !username}
          onClick={() => {
            if (selectedFile) {
              void startScan(selectedFile);
              void refreshHistory();
            }
          }}
        >
          {isUploading ? "Загрузка файла..." : "Запустить обработку"}
        </button>

        <div className="status-inline">
          <p>
            <strong>Сводка:</strong> активных задач {activeSummary.length}/{activeLimit}
          </p>
          {activeSummary.map((item) => (
            <p key={item.job_id}>
              {item.source_file}: {item.progress_pct}% ({item.processed_windows}/{item.total_windows}),{" "}
              {item.stage_label || item.status}
            </p>
          ))}
          {!activeSummary.length ? <p>Активных задач сейчас нет.</p> : null}
        </div>

        {error ? <p className="error">{error}</p> : null}
      </section>
      {username ? <HistoryPanel items={history} loading={historyLoading} onRefresh={refreshHistory} /> : null}
    </main>
  );
}
