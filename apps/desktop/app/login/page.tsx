"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { handleCallback, isAuthEnabled, login } from "@/lib/auth";
import { useAuth } from "@/components/auth/AuthProvider";

const AUTH_API = process.env.NEXT_PUBLIC_AUTH_API_URL || "";

interface ProviderDef {
  id: string;
  label: string;
  bgClass: string;
}

const ALL_PROVIDERS: ProviderDef[] = [
  { id: "github", label: "使用 GitHub 登录", bgClass: "bg-zinc-800 hover:bg-zinc-900" },
  { id: "google", label: "使用 Google 登录", bgClass: "bg-red-600 hover:bg-red-700" },
  { id: "twitter", label: "使用 X 登录", bgClass: "bg-black hover:bg-zinc-900" },
];

function LoginContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { isReady, isAuthenticated, syncAuth } = useAuth();
  const [providers, setProviders] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);
  const callbackAttempted = useRef(false);

  useEffect(() => {
    if (!AUTH_API) return;
    fetch(`${AUTH_API}/providers`)
      .then((r) => r.json())
      .then((json) => {
        const list = json?.data?.providers ?? json?.providers ?? [];
        setProviders(list);
      })
      .catch(() => setProviders(["github"]));
  }, []);

  useEffect(() => {
    if (isReady && isAuthenticated) {
      const returnTo = params.get("return") || "/dashboard";
      router.replace(returnTo);
    }
  }, [isReady, isAuthenticated, router, params]);

  useEffect(() => {
    const callback = params.get("callback");
    const code = params.get("code");
    const state = params.get("state");
    if (callback && code && !callbackAttempted.current) {
      callbackAttempted.current = true;
      setProcessing(true);
      handleCallback(callback, code, state ?? undefined).then((result) => {
        if (result.status === "ok") {
          syncAuth();
          const returnTo = params.get("return") || "/dashboard";
          router.replace(returnTo);
        } else {
          setError("登录失败，请重试");
          setProcessing(false);
        }
      });
    }
  }, [params, router, syncAuth]);

  if (!isAuthEnabled()) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
        <p>Community 模式无需登录</p>
      </div>
    );
  }

  if (processing) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
        <p>正在处理登录...</p>
      </div>
    );
  }

  const visible = ALL_PROVIDERS.filter((p) => providers.includes(p.id));

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <div className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900 p-8 shadow-2xl">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-zinc-100">PnLClaw</h1>
          <p className="mt-1 text-sm text-zinc-400">
            登录以访问量化交易平台
          </p>
        </div>

        {error && (
          <div className="mb-4 rounded bg-red-900/30 border border-red-700 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="flex flex-col gap-3">
          {visible.length === 0 && (
            <p className="text-center text-zinc-500 text-sm">
              加载登录方式中...
            </p>
          )}
          {visible.map((p) => (
            <button
              key={p.id}
              onClick={() => void login(p.id)}
              className={`${p.bgClass} text-white w-full h-11 rounded-md text-sm font-medium transition-colors`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <p className="mt-6 text-center text-xs text-zinc-500">
          仅限授权用户登录
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
          <p>加载中...</p>
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
