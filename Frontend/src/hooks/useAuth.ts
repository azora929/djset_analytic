import { useEffect, useState } from "react";
import { login, logout, me } from "../services/api";

export function useAuth() {
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void me()
      .then((data) => {
        setUsername(data.username);
        setError(null);
      })
      .catch(() => {
        setUsername(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const signIn = async (user: string, pass: string) => {
    setError(null);
    try {
      const data = await login(user, pass);
      setUsername(data.username);
    } catch {
      setError("Неверный логин или пароль");
    }
  };

  const signOut = async () => {
    await logout();
    setUsername(null);
  };

  return { username, loading, error, signIn, signOut };
}
