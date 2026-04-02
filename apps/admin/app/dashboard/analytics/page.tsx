"use client";

import { AdminHeader } from "@/components/layout/AdminHeader";
import { MetricCard } from "@/components/analytics/MetricCard";
import { ActiveUsersChart } from "@/components/analytics/ActiveUsersChart";
import { TrafficChart } from "@/components/analytics/TrafficChart";
import { GeoDistributionMap } from "@/components/analytics/GeoDistributionMap";
import { DeviceBreakdown } from "@/components/analytics/DeviceBreakdown";
import { RetentionChart } from "@/components/analytics/RetentionChart";
import {
  useAnalyticsOverview,
  useActiveUsers,
  useGeoDistribution,
  useDeviceDistribution,
  useRetention,
  useLoginStats,
} from "@/lib/hooks/useAnalytics";
import { Users, Activity, UserPlus, Monitor } from "lucide-react";

export default function AnalyticsPage() {
  const { overview, isLoading } = useAnalyticsOverview();
  const { activeUsers } = useActiveUsers("30d");
  const { geoData } = useGeoDistribution();
  const { deviceData } = useDeviceDistribution();
  const { retention } = useRetention();
  const { loginStats } = useLoginStats("7d");

  return (
    <div>
      <AdminHeader title="数据分析" />
      <div className="p-6 space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {isLoading ? (
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

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ActiveUsersChart data={activeUsers} />
          <TrafficChart data={loginStats} />
        </div>

        <GeoDistributionMap data={geoData} />
        <DeviceBreakdown data={deviceData} />
        <RetentionChart data={retention} />
      </div>
    </div>
  );
}
