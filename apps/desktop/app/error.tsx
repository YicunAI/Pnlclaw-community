"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a]">
      <div className="text-center max-w-md px-4">
        <h1 className="text-4xl font-bold tracking-tight text-white mb-4">
          PnLClaw
        </h1>
        <p className="text-neutral-400 mb-8">
          页面加载时发生错误，请重试。
        </p>
        <div className="flex gap-4 justify-center">
          <button
            onClick={() => reset()}
            className="px-6 py-2.5 rounded-full bg-white text-black font-medium hover:bg-neutral-200 transition-colors"
          >
            重试
          </button>
          <a
            href="/dashboard"
            className="px-6 py-2.5 rounded-full border border-neutral-700 text-white hover:bg-neutral-800 transition-colors"
          >
            进入平台
          </a>
        </div>
      </div>
    </div>
  );
}
