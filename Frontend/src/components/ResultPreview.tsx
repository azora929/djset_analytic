import { ScanJobResult } from "../types/scan";
import "./ResultPreview.scss";

interface ResultPreviewProps {
  result: ScanJobResult | null;
}

export function ResultPreview({ result }: ResultPreviewProps) {
  const tracks = result?.payload?.tracks ?? [];
  if (!tracks.length) {
    return null;
  }

  return (
    <section className="result-preview">
      <h2>Найденные треки ({tracks.length})</h2>
      <pre>{tracks.join("\n")}</pre>
    </section>
  );
}
