"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError, getStoredToken, setStoredToken } from "@/lib/api";

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  email_verified: boolean;
};

type TokenResponse = { access_token: string; token_type: string; user: User };
type RegisterResponse = { message: string; email: string };
type MessageResponse = { message: string };

type AuthContextValue = {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<RegisterResponse>;
  resendVerification: (email: string) => Promise<MessageResponse>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setIsLoading(false);
      return;
    }
    api
      .get<User>("/api/v1/auth/me")
      .then(setUser)
      .catch(() => {
        setStoredToken(null);
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<TokenResponse>("/api/v1/auth/login", { email, password });
    setStoredToken(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(async (email: string, password: string, fullName?: string) => {
    // Registration no longer logs the user in — the account starts
    // unverified and login is blocked until the emailed link is clicked.
    return api.post<RegisterResponse>("/api/v1/auth/register", {
      email,
      password,
      full_name: fullName || null,
    });
  }, []);

  const resendVerification = useCallback(async (email: string) => {
    return api.post<MessageResponse>("/api/v1/auth/resend-verification", { email });
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, register, resendVerification, logout }),
    [user, isLoading, login, register, resendVerification, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

export { ApiError };
