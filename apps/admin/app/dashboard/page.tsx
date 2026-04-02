"use client";

import { AdminHeader } from "@/components/layout/AdminHeader";
import { MetricCard } from "@/components/analytics/MetricCard";
import { ActiveUsersChart } from "@/components/analytics/ActiveUsersChart";
import {
  useAnalyticsOverview,
  useActiveUsers,
  useProviders,
} from "@/lib/hooks/useAnalytics";
import { Users, Activity, UserPlus, Monitor } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export default function DashboardPage() {
  const { overview, isLoading: overviewLoading } = useAnalyticsOverview();
  const { activeUsers } = useActiveUsers("30d");
  const { providers } = useProviders();

  return (
    <div>
      <AdminHeader title="仪表盘" />
      <div className="p-6 space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {overviewLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-28 animate-pulse rounded-lg border border-zinc-200 bg-zinc-100"
              />
            ))
          ) : (
            <>
              <MetricCard
                label="总用户数"
                value={overview?.total_users ?? 0}
                icon={Users}
              />
              <MetricCard
                label="活跃用户 (24h)"
                value={overview?.active_24h ?? 0}
                icon={Activity}
              />
              <MetricCard
                label="新注册 (24h)"
                value={overview?.new_signups_today ?? 0}
                icon={UserPlus}
              />
              <MetricCard
                label="总会话数"
                value={overview?.total_sessions ?? 0}
                icon={Monitor}
              />
            </>
          )}
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ActiveUsersChart data={activeUsers} />
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-5">
            <h3 className="mb-4 text-sm font-medium text-zinc-700">
              认证方式
            </h3>
            {providers.length === 0 ? (
              <p className="text-sm text-zinc-500">暂无数据</p>
            ) : (
              <div className="space-y-3">
                {providers.map((p) => (
                  <div
                    key={p.provider}
                    className="flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="capitalize">
                        {p.provider}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-zinc-900">
                        {p.count.toLocaleString()}
                      </span>
                      <span className="text-xs text-zinc-400">
                        ({p.percentage.toFixed(1)}%)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
