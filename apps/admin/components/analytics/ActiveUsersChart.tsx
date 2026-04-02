"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { ActiveUsersData } from "@/lib/types";

interface ActiveUsersChartProps {
  data: ActiveUsersData[];
}

export function ActiveUsersChart({ data }: ActiveUsersChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
        暂无活跃用户数据
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h3 className="mb-4 text-sm font-medium text-zinc-700">
        活跃用户趋势
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
          <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#a1a1aa" />
          <YAxis tick={{ fontSize: 12 }} stroke="#a1a1aa" />
          <Tooltip
            contentStyle={{
              borderRadius: 8,
              border: "1px solid #e4e4e7",
              fontSize: 12,
            }}
          />
          <Area
            type="monotone"
            dataKey="count"
            stroke="#18181b"
            fill="#18181b"
            fillOpacity={0.1}
            strokeWidth={2}
            name="活跃用户"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
