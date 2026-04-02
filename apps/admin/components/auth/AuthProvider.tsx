"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { refreshToken, logout as doLogout } from "@/lib/auth";
import { getAccessToken } from "@/lib/api";
import { useAuth } from "@/lib/hooks/useAuth";
import type { User } from "@/lib/types";

interface AuthContextValue {
  user: User | undefined;
  isLoading: boolean;
  isAuthenticated: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: undefined,
  isLoading: true,
  isAuthenticated: false,
  logout: () => {},
});

export function useAuthContext() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initializing, setInitializing] = useState(true);
  const router = useRouter();

  // Attempt token refresh on mount
  useEffect(() => {
    async function init() {
      if (!getAccessToken()) {
        await refreshToken();
      }
      setInitializing(false);
    }
    init();
  }, []);

  const { user, isLoading, isError } = useAuth();

  const isAuthenticated = !!user && !isError;

  const handleLogout = () => {
    doLogout();
    router.push("/login");
  };

  if (initializing) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-zinc-300 border-t-zinc-900" />
      </div>
    );
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated,
        logout: handleLogout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
