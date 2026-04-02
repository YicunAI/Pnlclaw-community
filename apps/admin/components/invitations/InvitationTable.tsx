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
import { Button } from "@/components/ui/button";
import { apiDelete } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Copy, XCircle } from "lucide-react";
import type { Invitation } from "@/lib/types";

interface InvitationTableProps {
  invitations: Invitation[];
  onInvitationsChanged: () => void;
}

function isExpired(expiresAt: string): boolean {
  return new Date(expiresAt).getTime() < Date.now();
}

export function InvitationTable({
  invitations,
  onInvitationsChanged,
}: InvitationTableProps) {
  const { toast } = useToast();

  function copyCode(code: string) {
    navigator.clipboard.writeText(code);
    toast({ title: "已复制", description: "邀请码已复制到剪贴板" });
  }

  async function deleteInvitation(id: string) {
    try {
      await apiDelete(`/admin/invitations/${id}`);
      toast({ title: "邀请码已删除" });
      onInvitationsChanged();
    } catch {
      toast({
        title: "错误",
        description: "删除邀请码失败",
        variant: "destructive",
      });
    }
  }

  if (invitations.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        暂无邀请码
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>邀请码</TableHead>
          <TableHead>角色</TableHead>
          <TableHead>使用次数</TableHead>
          <TableHead>备注</TableHead>
          <TableHead>创建者</TableHead>
          <TableHead>过期时间</TableHead>
          <TableHead>操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {invitations.map((inv) => {
          const expired = isExpired(inv.expires_at);
          const exhausted =
            inv.max_uses > 0 && inv.used_count >= inv.max_uses;
          return (
            <TableRow key={inv.id}>
              <TableCell>
                <code className="rounded bg-zinc-100 px-2 py-0.5 text-xs font-mono">
                  {inv.code}
                </code>
              </TableCell>
              <TableCell>
                <Badge variant="outline">{inv.role}</Badge>
              </TableCell>
              <TableCell className="text-sm tabular-nums">
                {inv.used_count} / {inv.max_uses}
              </TableCell>
              <TableCell className="max-w-[140px] truncate text-sm text-zinc-600">
                {inv.note ?? "—"}
              </TableCell>
              <TableCell className="text-sm font-mono text-zinc-600">
                {inv.created_by}
              </TableCell>
              <TableCell className="text-sm">
                <span className={expired ? "text-amber-700" : ""}>
                  {new Date(inv.expires_at).toLocaleString()}
                </span>
                {expired && (
                  <Badge variant="outline" className="ml-2">
                    已过期
                  </Badge>
                )}
                {exhausted && !expired && (
                  <Badge variant="outline" className="ml-2">
                    已用完
                  </Badge>
                )}
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => copyCode(inv.code)}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  {!expired && !exhausted && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-red-600"
                      onClick={() => deleteInvitation(inv.id)}
                    >
                      <XCircle className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
