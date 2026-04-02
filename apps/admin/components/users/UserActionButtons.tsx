"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { apiPost } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Ban, PauseCircle, CheckCircle } from "lucide-react";
import type { User } from "@/lib/types";

interface UserActionButtonsProps {
  user: User;
  onActionComplete: () => void;
}

type ActionType = "ban" | "suspend" | "activate";

const actionConfig: Record<
  ActionType,
  {
    label: string;
    description: string;
    icon: typeof Ban;
    variant: "destructive" | "outline" | "default";
  }
> = {
  ban: {
    label: "封禁用户",
    description: "该用户将被永久封禁，无法访问平台。",
    icon: Ban,
    variant: "destructive",
  },
  suspend: {
    label: "暂停用户",
    description: "该用户将被临时暂停。",
    icon: PauseCircle,
    variant: "outline",
  },
  activate: {
    label: "激活用户",
    description: "该用户将被重新激活并恢复访问权限。",
    icon: CheckCircle,
    variant: "default",
  },
};

export function UserActionButtons({
  user,
  onActionComplete,
}: UserActionButtonsProps) {
  const [pendingAction, setPendingAction] = useState<ActionType | null>(null);
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  async function handleConfirm() {
    if (!pendingAction) return;
    setLoading(true);
    try {
      await apiPost(`/admin/users/${user.id}/${pendingAction}`);
      toast({
        title: "操作成功",
        description: `用户已${pendingAction === "ban" ? "封禁" : pendingAction === "suspend" ? "暂停" : "激活"}`,
      });
      onActionComplete();
    } catch {
      toast({
        title: "错误",
        description: "更新用户状态失败",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  }

  return (
    <>
      <div className="flex gap-2">
        {user.status !== "banned" && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setPendingAction("ban")}
          >
            <Ban className="mr-1 h-4 w-4" />
            封禁
          </Button>
        )}
        {user.status !== "suspended" && user.status !== "banned" && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPendingAction("suspend")}
          >
            <PauseCircle className="mr-1 h-4 w-4" />
            暂停
          </Button>
        )}
        {user.status !== "active" && (
          <Button size="sm" onClick={() => setPendingAction("activate")}>
            <CheckCircle className="mr-1 h-4 w-4" />
            激活
          </Button>
        )}
      </div>

      {/* Confirmation dialog */}
      <Dialog
        open={pendingAction !== null}
        onOpenChange={(open) => !open && setPendingAction(null)}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {pendingAction ? actionConfig[pendingAction].label : ""}
            </DialogTitle>
            <DialogDescription>
              {pendingAction ? actionConfig[pendingAction].description : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setPendingAction(null)}
              disabled={loading}
            >
              取消
            </Button>
            <Button
              variant={
                pendingAction ? actionConfig[pendingAction].variant : "default"
              }
              onClick={handleConfirm}
              disabled={loading}
            >
              {loading ? "处理中..." : "确认"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
