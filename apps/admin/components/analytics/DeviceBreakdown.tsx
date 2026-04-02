"use client";

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import type { DeviceData } from "@/lib/types";

interface DeviceBreakdownProps {
  data: DeviceData | undefined;
}

const COLORS = [
  "#18181b",
  "#3f3f46",
  "#71717a",
  "#a1a1aa",
  "#d4d4d8",
  "#e4e4e7",
];

function DonutChart({
  title,
  items,
}: {
  title: string;
  items: { name: string; count: number; percentage: number }[];
}) {
  return (
    <div>
      <h4 className="mb-2 text-center text-sm font-medium text-zinc-500">
        {title}
      </h4>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={items}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={2}
            dataKey="count"
            nameKey="name"
          >
            {items.map((_, index) => (
              <Cell
                key={`cell-${index}`}
                fill={COLORS[index % COLORS.length]}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number, name: string) => [
              `${value} (${items.find((i) => i.name === name)?.percentage.toFixed(1) ?? 0}%)`,
              name,
            ]}
            contentStyle={{
              borderRadius: 8,
              border: "1px solid #e4e4e7",
              fontSize: 12,
            }}
          />
          <Legend
            formatter={(value) => (
              <span className="text-xs text-zinc-600">{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DeviceBreakdown({ data }: DeviceBreakdownProps) {
  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
        暂无设备数据
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h3 className="mb-4 text-sm font-medium text-zinc-700">
        设备分布
      </h3>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <DonutChart title="设备类型" items={data.devices} />
        <DonutChart title="操作系统" items={data.os} />
        <DonutChart title="浏览器" items={data.browsers} />
      </div>
    </div>
  );
}
