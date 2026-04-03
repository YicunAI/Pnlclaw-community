"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  clearAccessToken,
  getAccessToken,
  getTokenPayload,
  getUserId,
  getUserRole,
  isAuthEnabled,
  refreshToken,
  logout as doLogout,
} from "@/lib/auth";

interface AuthState {
  isReady: boolean;
  isAuthenticated: boolean;
  authEnabled: boolean;
  userId: string;
  role: string;
  displayName: string;
  avatarUrl: string;
  logout: () => void;
  /** Re-read token from localStorage and update context immediately. */
  syncAuth: () => void;
}

const AuthContext = createContext<AuthState>({
  isReady: false,
  isAuthenticated: false,
  authEnabled: false,
  userId: "local",
  role: "admin",
  displayName: "",
  avatarUrl: "",
  logout: () => {},
  syncAuth: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

function isTokenExpired(): boolean {
  const payload = getTokenPayload();
  if (!payload) return true;
  const exp = payload.exp as number;
  if (!exp) return false;
  return exp * 1000 < Date.now();
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isReady, setIsReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userId, setUserId] = useState("local");
  const [role, setRole] = useState("admin");
  const [displayName, setDisplayName] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");

  const updateFromToken = useCallback(() => {
    const token = getAccessToken();
    if (token && !isTokenExpired()) {
      setIsAuthenticated(true);
      const payload = getTokenPayload();
      setUserId(getUserId());
      setRole(getUserRole());
      setDisplayName((payload?.name as string) ?? (payload?.display_name as string) ?? "");
      setAvatarUrl((payload?.avatar_url as string) ?? "");
    } else {
      if (token && isTokenExpired()) {
        clearAccessToken();
      }
      setIsAuthenticated(false);
      setUserId("local");
      setRole("admin");
      setDisplayName("");
      setAvatarUrl("");
    }
  }, []);

  useEffect(() => {
    if (!isAuthEnabled()) {
      setIsReady(true);
      setIsAuthenticated(true);
      setUserId("local");
      setRole("admin");
      return;
    }

    updateFromToken();

    if (!getAccessToken()) {
      refreshToken().then((ok) => {
        if (ok) updateFromToken();
        setIsReady(true);
      });
    } else {
      setIsReady(true);
    }

    const interval = setInterval(() => {
      const payload = getTokenPayload();
      const exp = (payload?.exp as number) ?? 0;
      const nowSec = Math.floor(Date.now() / 1000);
      const needsRefresh = isTokenExpired() || (exp > 0 && exp - nowSec < 300);

      if (needsRefresh) {
        refreshToken().then((ok) => {
          if (ok) {
            updateFromToken();
          } else if (isTokenExpired()) {
            clearAccessToken();
            setIsAuthenticated(false);
          }
        });
      }
    }, 30 * 1000);

    return () => clearInterval(interval);
  }, [updateFromToken]);

  const syncAuth = useCallback(() => {
    updateFromToken();
    if (!isReady) setIsReady(true);
  }, [updateFromToken, isReady]);

  const logout = useCallback(() => {
    doLogout();
    setIsAuthenticated(false);
    setDisplayName("");
    setAvatarUrl("");
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isReady,
        isAuthenticated,
        authEnabled: isAuthEnabled(),
        userId,
        role,
        displayName,
        avatarUrl,
        logout,
        syncAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
