"use client";

import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { CheckCircle, XCircle } from "lucide-react";
import type { LoginHistoryEntry } from "@/lib/types";

interface LoginHistoryTableProps {
  entries: LoginHistoryEntry[];
}

export function LoginHistoryTable({ entries }: LoginHistoryTableProps) {
  if (entries.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        暂无登录历史
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>时间</TableHead>
          <TableHead>登录方式</TableHead>
          <TableHead>IP</TableHead>
          <TableHead>位置</TableHead>
          <TableHead>设备</TableHead>
          <TableHead>操作系统</TableHead>
          <TableHead>浏览器</TableHead>
          <TableHead>状态</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry) => (
          <TableRow key={entry.id}>
            <TableCell className="whitespace-nowrap text-sm">
              {new Date(entry.created_at).toLocaleString()}
            </TableCell>
            <TableCell>
              <Badge variant="outline">{entry.provider}</Badge>
            </TableCell>
            <TableCell className="font-mono text-xs">
              {entry.ip_address}
            </TableCell>
            <TableCell className="text-sm">
              {[entry.city, entry.country].filter(Boolean).join(", ") || "-"}
            </TableCell>
            <TableCell className="text-sm">{entry.device ?? "-"}</TableCell>
            <TableCell className="text-sm">{entry.os ?? "-"}</TableCell>
            <TableCell className="text-sm">{entry.browser ?? "-"}</TableCell>
            <TableCell>
              {entry.success ? (
                <span className="flex items-center gap-1 text-green-600 text-sm">
                  <CheckCircle className="h-4 w-4" />
                  成功
                </span>
              ) : (
                <span className="flex items-center gap-1 text-red-600 text-sm">
                  <XCircle className="h-4 w-4" />
                  失败
                </span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
