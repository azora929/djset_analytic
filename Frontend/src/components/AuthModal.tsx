import { FormEvent, useState } from "react";
import "./AuthModal.scss";

interface AuthModalProps {
  loading?: boolean;
  error?: string | null;
  onSubmit: (username: string, password: string) => Promise<void>;
}

export function AuthModal({ loading = false, error = null, onSubmit }: AuthModalProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onSubmit(username.trim(), password);
  };

  return (
    <div className="auth-modal">
      <form className="auth-modal__card" onSubmit={submit}>
        <h2>Вход</h2>
        <p>Введите логин и пароль для доступа к обработкам.</p>
        <label>
          <span>Логин</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} required />
        </label>
        <label>
          <span>Пароль</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </label>
        <button className="primary-btn" type="submit" disabled={loading}>
          {loading ? "Проверка..." : "Войти"}
        </button>
        {error ? <p className="error">{error}</p> : null}
      </form>
    </div>
  );
}
