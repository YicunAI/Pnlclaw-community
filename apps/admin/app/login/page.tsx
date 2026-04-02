"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { mutate } from "swr";
import { useAuthContext } from "@/components/auth/AuthProvider";
import { LoginButton } from "@/components/auth/LoginButton";
import { TOTPVerifyDialog } from "@/components/auth/TOTPVerifyDialog";
import { handleCallback } from "@/lib/auth";

export default function LoginPage() {
  const { isAuthenticated, isLoading } = useAuthContext();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [totpOpen, setTotpOpen] = useState(false);
  const [partialToken, setPartialToken] = useState<string | null>(null);

  // Handle OAuth callback
  useEffect(() => {
    const provider = searchParams.get("callback");
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (provider && code) {
      handleCallback(provider, code, state ?? undefined).then((result) => {
        if (result.status === "ok") {
          void mutate("/auth/me");
          router.replace("/dashboard");
        } else if (result.status === "totp") {
          setPartialToken(result.partialToken);
          setTotpOpen(true);
        }
      });
    }
  }, [searchParams, router]);

  // Redirect if already authenticated
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, isLoading, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo / Title */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-zinc-900">
            <span className="text-xl font-bold text-white">P</span>
          </div>
          <h1 className="text-2xl font-bold text-zinc-900">PnLClaw 管理后台</h1>
          <p className="mt-1 text-sm text-zinc-500">
            登录以访问管理控制台
          </p>
        </div>

        {/* Login card */}
        <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
          <LoginButton />
        </div>

        <p className="text-center text-xs text-zinc-400">
          仅授权管理员账号可访问此控制台
        </p>
      </div>

      <TOTPVerifyDialog
        open={totpOpen}
        onOpenChange={(open) => {
          setTotpOpen(open);
          if (!open) {
            setPartialToken(null);
          }
        }}
        partialToken={partialToken ?? undefined}
        onVerified={() => {
          void mutate("/auth/me");
          router.replace("/dashboard");
          setPartialToken(null);
        }}
      />
    </div>
  );
}
