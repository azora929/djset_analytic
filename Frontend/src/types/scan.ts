export type JobStatusType = "queued" | "running" | "completed" | "failed";

export interface ScanCreateResponse {
  job_id: string;
  status: JobStatusType;
}

export interface AuthMeResponse {
  username: string;
}

export interface ScanJobStatus {
  job_id: string;
  status: JobStatusType;
  stage?: string | null;
  stage_label?: string | null;
  raw_state?: string | null;
  created_at: string;
  updated_at: string;
  source_file: string;
  source_size_bytes: number;
  message?: string | null;
  progress_pct: number;
  total_windows: number;
  processed_windows: number;
  output_titles?: string | null;
  is_done?: boolean;
}

export interface JobHistoryItem {
  job_id: string;
  owner?: string | null;
  source_file: string;
  source_size_bytes: number;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  output_titles?: string | null;
  message?: string | null;
}
