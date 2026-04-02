"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { LoginStatsData } from "@/lib/types";

interface TrafficChartProps {
  data: LoginStatsData[];
}

export function TrafficChart({ data }: TrafficChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
        暂无流量数据
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h3 className="mb-4 text-sm font-medium text-zinc-700">
        登录流量
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data}>
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
          <Line
            type="monotone"
            dataKey="success"
            stroke="#16a34a"
            strokeWidth={2}
            dot={false}
            name="成功"
          />
          <Line
            type="monotone"
            dataKey="failure"
            stroke="#dc2626"
            strokeWidth={2}
            dot={false}
            name="失败"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
