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
            <div className="history-item-head">
              <p className="history-file">
                <strong>{item.source_file}</strong>
              </p>
              <span className={`history-status history-status--${item.status}`}>{item.status}</span>
            </div>
            <p className="history-message">{item.message || "Результат готов к скачиванию"}</p>
            <a className="download-link" href={getDownloadUrl(item.job_id)} target="_blank" rel="noreferrer">
              Скачать DOCX
            </a>
          </article>
        ))}
        {!items.length ? <p>Пока нет обработок.</p> : null}
      </div>
    </section>
  );
}
