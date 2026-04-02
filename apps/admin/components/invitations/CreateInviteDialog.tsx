"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPost } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Plus } from "lucide-react";
import type { CreateInvitationRequest } from "@/lib/types";

interface CreateInviteDialogProps {
  onCreated: () => void;
}

export function CreateInviteDialog({ onCreated }: CreateInviteDialogProps) {
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState<"user" | "admin" | "operator">("user");
  const [maxUses, setMaxUses] = useState(1);
  const [expiresInHours, setExpiresInHours] = useState(168);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { toast } = useToast();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    setSubmitting(true);
    try {
      const body: CreateInvitationRequest = {
        role,
        max_uses: maxUses,
        expires_in_hours: expiresInHours,
        ...(note.trim() ? { note: note.trim() } : {}),
      };
      await apiPost("/admin/invitations", body);
      toast({ title: "邀请码已创建" });
      setRole("user");
      setMaxUses(1);
      setExpiresInHours(168);
      setNote("");
      setOpen(false);
      onCreated();
    } catch {
      toast({
        title: "错误",
        description: "创建邀请码失败",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-1 h-4 w-4" />
          新建邀请码
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>创建邀请码</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-700">
              角色
            </label>
            <select
              value={role}
              onChange={(e) =>
                setRole(e.target.value as "user" | "admin" | "operator")
              }
              className="flex h-9 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm"
            >
              <option value="user">用户</option>
              <option value="operator">运营</option>
              <option value="admin">管理员</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-700">
              最大使用次数
            </label>
            <Input
              type="number"
              min={1}
              max={1000}
              value={maxUses}
              onChange={(e) => setMaxUses(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-700">
              过期时间（小时）
            </label>
            <Input
              type="number"
              min={1}
              max={8760}
              value={expiresInHours}
              onChange={(e) => setExpiresInHours(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-700">
              备注（可选）
            </label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="内部备注"
              maxLength={500}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
