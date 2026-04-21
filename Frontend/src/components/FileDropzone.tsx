import { DragEvent, useRef, useState } from "react";
import "./FileDropzone.scss";

interface FileDropzoneProps {
  file: File | null;
  disabled?: boolean;
  onFileSelect: (file: File) => void;
}

const ACCEPT = ".wav,.mp3,.m4a,.flac,.aac,.ogg";

export function FileDropzone({ file, disabled = false, onFileSelect }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragActive(false);
    if (disabled) {
      return;
    }
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) {
      onFileSelect(dropped);
    }
  };

  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!disabled) {
      setIsDragActive(true);
    }
  };

  const onDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragActive(false);
  };

  return (
    <div
      className={`file-dropzone ${isDragActive ? "file-dropzone--active" : ""} ${disabled ? "file-dropzone--disabled" : ""}`}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" && !disabled) {
          inputRef.current?.click();
        }
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        disabled={disabled}
        onChange={(event) => {
          const selected = event.target.files?.[0];
          if (selected) {
            onFileSelect(selected);
          }
        }}
      />

      <p className="file-dropzone__title">Перетащи файл сюда или нажми для выбора</p>
      <p className="file-dropzone__subtitle">Подходит большой WAV/аудио, загрузка идет напрямую на сервер.</p>
      {file ? (
        <p className="file-dropzone__meta">
          Выбран: <strong>{file.name}</strong> ({Math.round(file.size / 1024 / 1024)} MB)
        </p>
      ) : null}
    </div>
  );
}
