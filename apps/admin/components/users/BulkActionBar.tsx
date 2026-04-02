"use client";

import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Ban, PauseCircle, CheckCircle, Tag, X } from "lucide-react";
import type { BulkActionRequest } from "@/lib/types";

interface BulkActionBarProps {
  selectedIds: string[];
  onClear: () => void;
  onActionComplete: () => void;
}

export function BulkActionBar({
  selectedIds,
  onClear,
  onActionComplete,
}: BulkActionBarProps) {
  const { toast } = useToast();

  if (selectedIds.length === 0) return null;

  async function handleAction(action: BulkActionRequest["action"]) {
    try {
      await apiPost("/admin/users/bulk-action", {
        user_ids: selectedIds,
        action,
      } satisfies BulkActionRequest);
      toast({
        title: "操作成功",
        description: `已更新 ${selectedIds.length} 位用户`,
      });
      onActionComplete();
      onClear();
    } catch {
      toast({
        title: "错误",
        description: "批量操作失败",
        variant: "destructive",
      });
    }
  }

  return (
    <div className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2 rounded-lg border border-zinc-200 bg-white px-4 py-3 shadow-lg">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-zinc-700">
          已选 {selectedIds.length} 项
        </span>
        <div className="h-5 w-px bg-zinc-200" />
        <Button
          variant="destructive"
          size="sm"
          onClick={() => handleAction("ban")}
        >
          <Ban className="mr-1 h-4 w-4" />
          封禁
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => handleAction("suspend")}
        >
          <PauseCircle className="mr-1 h-4 w-4" />
          暂停
        </Button>
        <Button size="sm" onClick={() => handleAction("activate")}>
          <CheckCircle className="mr-1 h-4 w-4" />
          激活
        </Button>
        <Button variant="outline" size="sm" disabled>
          <Tag className="mr-1 h-4 w-4" />
          标签
        </Button>
        <div className="h-5 w-px bg-zinc-200" />
        <button
          onClick={onClear}
          className="rounded p-1 text-zinc-400 hover:text-zinc-600"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
