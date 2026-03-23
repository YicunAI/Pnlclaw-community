"use client"

import React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  BarChart3,
  FlaskConical,
  Wallet,
  ArrowRightLeft,
  Settings,
  Activity,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: BarChart3 },
  { href: "/backtests", label: "Backtests", icon: FlaskConical },
  { href: "/paper", label: "Paper Trading", icon: Wallet },
  { href: "/trading", label: "Trading", icon: ArrowRightLeft },
  { href: "/settings", label: "Settings", icon: Settings },
]

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <aside className="w-[240px] shrink-0 border-r border-border flex flex-col bg-card">
        <div className="flex items-center gap-2 px-6 h-14">
          <Activity className="h-5 w-5 text-primary" />
          <span className="font-semibold text-sm tracking-tight">PnLClaw</span>
          <span className="text-xs text-muted-foreground ml-auto">v0.1.0</span>
        </div>
        <Separator />
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname?.startsWith(item.href))
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="px-4 py-3 text-xs text-muted-foreground border-t border-border">
          Community Edition &middot; AGPLv3
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  )
}
