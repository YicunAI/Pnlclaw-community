"use client";

import { useAuth } from "./AuthProvider";
import { usePathname } from "next/navigation";
import { LogIn } from "lucide-react";
import { useI18n } from "@/components/i18n/use-i18n";

interface RequireAuthProps {
  children: React.ReactNode;
  /** What to show while auth state is loading */
  fallback?: React.ReactNode;
}

export function RequireAuth({ children, fallback }: RequireAuthProps) {
  const { isReady, isAuthenticated, authEnabled } = useAuth();
  const pathname = usePathname();
  const { t } = useI18n();

  if (!authEnabled) return <>{children}</>;

  if (!isReady) {
    return fallback ?? (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-6">
        <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
          <LogIn className="h-7 w-7 text-muted-foreground" />
        </div>
        <div className="text-center space-y-2">
          <h2 className="text-xl font-semibold">{t("auth.loginRequired")}</h2>
          <p className="text-sm text-muted-foreground max-w-sm">
            {t("auth.loginRequiredDesc")}
          </p>
        </div>
        <a
          href={`/login?return=${encodeURIComponent(pathname || "/dashboard")}`}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <LogIn className="h-4 w-4" />
          {t("auth.login")}
        </a>
      </div>
    );
  }

  return <>{children}</>;
}
