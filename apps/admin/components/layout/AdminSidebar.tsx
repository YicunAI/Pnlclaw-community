"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  BarChart3,
  Tag,
  Mail,
  Settings,
  ChevronLeft,
  Menu,
} from "lucide-react";
import { useState } from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: Parameters<typeof clsx>) {
  return twMerge(clsx(inputs));
}

const navItems = [
  { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
  { href: "/dashboard/users", label: "用户管理", icon: Users },
  { href: "/dashboard/analytics", label: "数据分析", icon: BarChart3 },
  { href: "/dashboard/tags", label: "标签", icon: Tag },
  { href: "/dashboard/invitations", label: "邀请码", icon: Mail },
  { href: "/dashboard/settings", label: "设置", icon: Settings },
];

export function AdminSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  function isActive(href: string) {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  }

  const sidebar = (
    <aside
      className={cn(
        "flex flex-col bg-zinc-900 text-white transition-all duration-200",
        collapsed ? "w-16" : "w-60",
        "h-full"
      )}
    >
      {/* Logo area */}
      <div className="flex h-14 items-center justify-between px-4 border-b border-zinc-800">
        {!collapsed && (
          <span className="text-lg font-bold tracking-tight">PnLClaw</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden lg:flex items-center justify-center rounded p-1 hover:bg-zinc-800"
        >
          <ChevronLeft
            className={cn(
              "h-4 w-4 transition-transform",
              collapsed && "rotate-180"
            )}
          />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-800 hover:text-white"
              )}
            >
              <Icon className="h-5 w-5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-zinc-800 p-4">
        {!collapsed && (
          <p className="text-xs text-zinc-500">PnLClaw Admin v0.1</p>
        )}
      </div>
    </aside>
  );

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-4 top-3 z-50 rounded-md bg-zinc-900 p-2 text-white lg:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile sidebar */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 lg:hidden transition-transform duration-200",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {sidebar}
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:flex h-screen sticky top-0">{sidebar}</div>
    </>
  );
}
