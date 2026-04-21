import { JobHistoryItem } from "../types/scan";
import { getDownloadUrl } from "../services/api";
import "./HistoryPanel.scss";

interface HistoryPanelProps {
  items: JobHistoryItem[];
  loading?: boolean;
  onRefresh: () => Promise<void>;
}

export function HistoryPanel({ items, loading = false, onRefresh }: HistoryPanelProps) {
  return (
    <section className="card">
      <div className="history-head">
        <h2>Личный кабинет</h2>
        <button className="primary-btn" onClick={() => void onRefresh()} disabled={loading}>
          {loading ? "Обновление..." : "Обновить"}
        </button>
      </div>
      <div className="history-list">
        {items.map((item) => (
          <article key={item.job_id} className="history-item">
            <p>
              <strong>{item.source_file}</strong>
            </p>
            <p>Размер: {Math.round(item.source_size_bytes / 1024 / 1024)} MB</p>
            <p>Статус: {item.status}</p>
            <p>Дата: {item.completed_at || item.created_at || "-"}</p>
            <p>Треков: {item.tracks_found}</p>
            <a href={getDownloadUrl(item.job_id)} target="_blank" rel="noreferrer">
              Скачать результат
            </a>
          </article>
        ))}
        {!items.length ? <p>Пока нет обработок.</p> : null}
      </div>
    </section>
  );
}
