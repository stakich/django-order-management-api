import { createContext } from "react";
import type { AuthUser } from "../api/auth";

export type AuthContextValue = {
  user: AuthUser | null;
  isInitializing: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
