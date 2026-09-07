"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { authApi, USER_ID_KEY, clearStoredToken, getStoredToken, setStoredToken } from "@/lib/api";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (userId: string, password: string, remember?: boolean) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => clearStoredToken())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (userId: string, password: string, remember = true) => {
    const result = await authApi.login(userId, password, remember);
    setStoredToken(result.access_token, remember);
    window.localStorage.setItem(USER_ID_KEY, userId);
    setUser(result.user);
    return result.user;
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
    router.replace("/login");
  }, [router]);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth 는 AuthProvider 내부에서만 사용할 수 있습니다.");
  return context;
}

export const ROLE_LABELS: Record<User["role_level"], string> = {
  ADMIN: "관리자",
  LEADER: "조직장",
  MEMBER: "구성원",
};
