"use client"

import React, { Component } from "react";
import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

const SplineSceneBasic = dynamic(
  () => import("@/components/ui/demo").then((mod) => mod.SplineSceneBasic),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-screen w-full items-center justify-center bg-[#0a0a0a]">
        <Skeleton className="h-[80vh] w-[90vw] rounded-xl border border-border bg-card" />
      </div>
    ),
  }
);

const LandingSections = dynamic(
  () => import("@/components/landing/sections").then((mod) => mod.LandingSections),
  { ssr: false }
);

class PageErrorBoundary extends Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen w-full items-center justify-center bg-[#0a0a0a]">
          <div className="text-center">
            <h1 className="text-5xl md:text-8xl font-bold bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 to-neutral-400 tracking-tight">
              PnLClaw
            </h1>
            <p className="mt-6 text-lg text-neutral-400">
              加密量化研究 · 策略回测 · 模拟交易
            </p>
            <div className="mt-10 flex gap-4 justify-center">
              <a
                href="/dashboard"
                className="px-8 py-3 rounded-full bg-white text-black font-semibold hover:bg-neutral-200 transition-colors"
              >
                进入平台
              </a>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function Home() {
  return (
    <PageErrorBoundary>
      <main className="min-h-screen bg-[#0a0a0a]">
        <div className="w-full mx-auto">
          <SplineSceneBasic />
        </div>
        <LandingSections />
      </main>
    </PageErrorBoundary>
  );
}
