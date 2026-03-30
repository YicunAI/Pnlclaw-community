"use client"

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

const SplineSceneBasic = dynamic(
  () => import("@/components/ui/demo").then((mod) => mod.SplineSceneBasic),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-screen w-full items-center justify-center">
        <Skeleton className="h-[80vh] w-[90vw] rounded-xl border border-border bg-card" />
      </div>
    ),
  }
);

const LandingSections = dynamic(
  () => import("@/components/landing/sections").then((mod) => mod.LandingSections),
  { ssr: false }
);

export default function Home() {
  return (
    <main className="min-h-screen bg-[#0a0a0a]">
      <div className="w-full mx-auto">
        <SplineSceneBasic />
      </div>
      <LandingSections />
    </main>
  );
}
