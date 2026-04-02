"use client";

import { useState, useRef, useEffect } from "react";
import { LogIn, LogOut, User, ChevronDown, Shield } from "lucide-react";
import { useAuth } from "./AuthProvider";
import { useRouter } from "next/navigation";
import { useI18n } from "@/components/i18n/use-i18n";

export function UserMenu() {
  const { isReady, isAuthenticated, authEnabled, displayName, avatarUrl, role, logout } = useAuth();
  const router = useRouter();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (!authEnabled) return null;
  if (!isReady) return <div className="h-8 w-8 rounded-full bg-muted animate-pulse" />;

  if (!isAuthenticated) {
    return (
      <button
        onClick={() => router.push("/login")}
        className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <LogIn className="h-4 w-4" />
        <span>{t("auth.login")}</span>
      </button>
    );
  }

  const initial = (displayName || "U")[0].toUpperCase();

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-muted transition-colors"
      >
        {avatarUrl ? (
          <img src={avatarUrl} alt="" className="h-7 w-7 rounded-full object-cover border border-border" />
        ) : (
          <div className="h-7 w-7 rounded-full bg-primary/15 text-primary text-xs font-bold flex items-center justify-center border border-primary/20">
            {initial}
          </div>
        )}
        <span className="text-sm font-medium max-w-[120px] truncate hidden sm:inline">{displayName || "User"}</span>
        <ChevronDown className="h-3 w-3 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 rounded-xl border border-border bg-card shadow-xl z-50 py-1 animate-in fade-in slide-in-from-top-1 duration-150">
          <div className="px-3 py-2.5 border-b border-border">
            <div className="flex items-center gap-2">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="h-8 w-8 rounded-full object-cover border border-border" />
              ) : (
                <div className="h-8 w-8 rounded-full bg-primary/15 text-primary text-sm font-bold flex items-center justify-center border border-primary/20">
                  {initial}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold truncate">{displayName || "User"}</p>
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  {role === "admin" && <Shield className="h-3 w-3 text-amber-500" />}
                  {role}
                </p>
              </div>
            </div>
          </div>
          <button
            onClick={() => { setOpen(false); logout(); }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <LogOut className="h-4 w-4" />
            {t("auth.logout")}
          </button>
        </div>
      )}
    </div>
  );
}
