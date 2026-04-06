"use client"

import React, { useCallback } from "react"
import { usePathname, useRouter } from "next/navigation"
import {
  LayoutDashboard,
  BarChart3,
  FlaskConical,
  Wallet,
  ArrowRightLeft,
  Settings,
  Plug,
  Sparkles,
  TrendingUp,
  Percent,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"
import { useI18n } from "@/components/i18n/use-i18n"

const navItems = [
  { href: "/dashboard", key: "nav.dashboard", icon: LayoutDashboard },
  { href: "/markets", key: "nav.markets", icon: BarChart3 },
  { href: "/strategies", key: "nav.strategies", icon: FlaskConical },
  { href: "/paper", key: "nav.paper", icon: Wallet },
  { href: "/trading", key: "nav.trading", icon: ArrowRightLeft },
  { href: "/tactical", key: "nav.funding", icon: Percent },
  { href: "/polymarket", key: "nav.polymarket", icon: TrendingUp },
  { href: "/mcp", key: "nav.mcp", icon: Plug },
  { href: "/skills", key: "nav.skills", icon: Sparkles },
  { href: "/settings", key: "nav.settings", icon: Settings },
] as const

function NavLink({
  href,
  isActive,
  icon: Icon,
  label,
}: {
  href: string
  isActive: boolean
  icon: React.ElementType
  label: string
}) {
  const router = useRouter()

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault()
      try {
        router.push(href)
      } catch {
        window.location.href = href
      }
    },
    [href, router],
  )

  return (
    <a
      href={href}
      onClick={handleClick}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
        isActive
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </a>
  )
}

export const Sidebar = React.memo(function Sidebar() {
  const pathname = usePathname()
  const { t } = useI18n()

  return (
    <aside className="w-[240px] shrink-0 border-r border-border flex flex-col bg-card">
      <div className="flex items-center gap-2 px-6 h-14">
        <img src="/logo2.svg" alt="Logo" className="h-6 w-6 brightness-0 invert" />
        <span className="font-semibold text-sm tracking-tight">PnLClaw</span>
        <span className="text-xs text-muted-foreground ml-auto">v0.1.0</span>
      </div>
      <Separator />
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            pathname === item.href + "/" ||
            (item.href !== "/dashboard" && pathname?.startsWith(item.href))
          return (
            <NavLink
              key={item.href}
              href={item.href}
              isActive={isActive}
              icon={item.icon}
              label={t(item.key)}
            />
          )
        })}
      </nav>
      <div className="px-4 py-3 text-xs text-muted-foreground border-t border-border">
        {t("nav.edition")}
      </div>
    </aside>
  )
})
