
import { useEffect, useState, type ReactNode } from "react";
import {
  ApiError,
  clearTokens,
  getMe,
  hasSession,
  login,
  saveTokens,
  SESSION_ENDED_EVENT,
} from "../api/auth";
import type { AuthUser } from "../api/auth";
import { AuthContext } from "./AuthContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isInitializing, setIsInitializing] = useState(hasSession);

  useEffect(() => {
    const controller = new AbortController();

    function handleSessionEnded() {
      controller.abort();
      setUser(null);
      setIsInitializing(false);
    }

    window.addEventListener(SESSION_ENDED_EVENT, handleSessionEnded);

    if (hasSession()) {
      getMe(controller.signal)
        .then((currentUser) => {
          if (!controller.signal.aborted) {
            setUser(currentUser);
          }
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;

          if (error instanceof ApiError && error.status === 401) {
            clearTokens();
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setIsInitializing(false);
          }
        });
    }

    return () => {
      controller.abort();
      window.removeEventListener(
        SESSION_ENDED_EVENT,
        handleSessionEnded
      );
    };
  }, []);

  async function signIn(username: string, password: string) {
    const tokens = await login(username, password);

    saveTokens(tokens);

    try {
      const currentUser = await getMe();
      setUser(currentUser);
    } catch (error) {
      clearTokens();
      throw error;
    }
  }

  function signOut() {
    clearTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, isInitializing, signIn, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}
