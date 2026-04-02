"use client";

import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { GeoData } from "@/lib/types";

interface GeoDistributionMapProps {
  data: GeoData[];
}

export function GeoDistributionMap({ data }: GeoDistributionMapProps) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
        暂无地域分布数据
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <h3 className="mb-4 text-sm font-medium text-zinc-700">
        地域分布
      </h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>国家/地区</TableHead>
            <TableHead className="text-right">用户数</TableHead>
            <TableHead className="text-right">占比</TableHead>
            <TableHead>分布</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row) => (
            <TableRow key={row.country_code}>
              <TableCell className="font-medium">
                <span className="mr-2">{row.country_code}</span>
                {row.country}
              </TableCell>
              <TableCell className="text-right">
                {row.count.toLocaleString()}
              </TableCell>
              <TableCell className="text-right">
                {row.percentage.toFixed(1)}%
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <div className="h-2 flex-1 rounded-full bg-zinc-100">
                    <div
                      className="h-2 rounded-full bg-zinc-900"
                      style={{ width: `${Math.min(row.percentage, 100)}%` }}
                    />
                  </div>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
