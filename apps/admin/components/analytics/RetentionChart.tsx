"use client";

import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { RetentionData } from "@/lib/types";

interface RetentionChartProps {
  data: RetentionData[];
}

export function RetentionChart({ data }: RetentionChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
        暂无留存数据
      </div>
    );
  }

  const maxWeeks = Math.max(...data.map((d) => d.retention.length));

  function getCellColor(value: number): string {
    if (value >= 80) return "bg-zinc-900 text-white";
    if (value >= 60) return "bg-zinc-700 text-white";
    if (value >= 40) return "bg-zinc-500 text-white";
    if (value >= 20) return "bg-zinc-300 text-zinc-900";
    return "bg-zinc-100 text-zinc-600";
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h3 className="mb-4 text-sm font-medium text-zinc-700">
        留存分析
      </h3>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>群组</TableHead>
              <TableHead className="text-right">规模</TableHead>
              {Array.from({ length: maxWeeks }, (_, i) => (
                <TableHead key={i} className="text-center">
                  W{i}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row) => (
              <TableRow key={row.cohort}>
                <TableCell className="font-medium whitespace-nowrap">
                  {row.cohort}
                </TableCell>
                <TableCell className="text-right">{row.size}</TableCell>
                {row.retention.map((val, idx) => (
                  <TableCell key={idx} className="text-center p-1">
                    <div
                      className={`rounded px-2 py-1 text-xs font-medium ${getCellColor(val)}`}
                    >
                      {val.toFixed(0)}%
                    </div>
                  </TableCell>
                ))}
                {/* Pad empty cells */}
                {Array.from(
                  { length: maxWeeks - row.retention.length },
                  (_, i) => (
                    <TableCell key={`empty-${i}`} />
                  )
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
