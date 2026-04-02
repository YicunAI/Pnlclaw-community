"use client"

import React from "react"
import dynamic from "next/dynamic"
import { Sidebar } from "@/components/sidebar"
import { LocaleSwitcherCompact } from "@/components/i18n/locale-switcher"
import { UserMenu } from "@/components/auth/user-menu"
import { DashboardRealtimeProvider } from "@/components/providers/dashboard-realtime-provider"

const AgentChat = dynamic(
  () => import("@/components/agent-chat").then((m) => ({ default: m.AgentChat })),
  { ssr: false, loading: () => null },
)

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <DashboardRealtimeProvider>
      <div className="flex h-screen bg-background text-foreground overflow-hidden">
        <Sidebar />

        <main className="flex-1 overflow-auto hover-scrollbar">
          <div className="flex items-center justify-end gap-3 px-6 h-14 border-b border-border shrink-0">
            <LocaleSwitcherCompact />
            <UserMenu />
          </div>
          <div className="p-6">{children}</div>
        </main>

        <AgentChat />
      </div>
    </DashboardRealtimeProvider>
  )
}
