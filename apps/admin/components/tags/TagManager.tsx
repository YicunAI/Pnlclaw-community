"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { useTags } from "@/lib/hooks/useTags";
import { apiPost, apiPatch, apiDelete } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Plus, Edit, Trash2 } from "lucide-react";
import type { UserTag, CreateTagRequest } from "@/lib/types";

const PRESET_COLORS = [
  "#ef4444",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#06b6d4",
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
  "#6b7280",
  "#18181b",
];

export function TagManager() {
  const { tags, isLoading, mutate } = useTags();
  const { toast } = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTag, setEditingTag] = useState<UserTag | null>(null);
  const [name, setName] = useState("");
  const [color, setColor] = useState(PRESET_COLORS[0]);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function openCreate() {
    setEditingTag(null);
    setName("");
    setColor(PRESET_COLORS[0]);
    setDescription("");
    setDialogOpen(true);
  }

  function openEdit(tag: UserTag) {
    setEditingTag(tag);
    setName(tag.name);
    setColor(tag.color);
    setDescription(tag.description ?? "");
    setDialogOpen(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    try {
      if (editingTag) {
        await apiPatch(`/admin/tags/${editingTag.id}`, {
          name: name.trim(),
          color,
          description: description.trim() || undefined,
        });
        toast({ title: "标签已更新" });
      } else {
        await apiPost("/admin/tags", {
          name: name.trim(),
          color,
          description: description.trim() || undefined,
        } satisfies CreateTagRequest);
        toast({ title: "标签已创建" });
      }
      mutate();
      setDialogOpen(false);
    } catch {
      toast({
        title: "错误",
        description: "保存标签失败",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(tag: UserTag) {
    if (!confirm(`确定删除标签 "${tag.name}"？`)) return;
    try {
      await apiDelete(`/admin/tags/${tag.id}`);
      toast({ title: "标签已删除" });
      mutate();
    } catch {
      toast({
        title: "错误",
        description: "删除标签失败",
        variant: "destructive",
      });
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
        加载标签中...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-zinc-900">标签</h2>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-1 h-4 w-4" />
          新建标签
        </Button>
      </div>

      {tags.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          暂无标签
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tags.map((tag) => (
            <div
              key={tag.id}
              className="flex items-center justify-between rounded-md border border-zinc-200 p-3"
            >
              <div className="flex items-center gap-3">
                <div
                  className="h-4 w-4 rounded-full"
                  style={{ backgroundColor: tag.color }}
                />
                <div>
                  <p className="text-sm font-medium text-zinc-900">
                    {tag.name}
                  </p>
                  {tag.description && (
                    <p className="text-xs text-zinc-500">{tag.description}</p>
                  )}
                  {tag.user_count !== undefined && (
                    <Badge variant="outline" className="mt-1 text-xs">
                      {tag.user_count} 位用户
                    </Badge>
                  )}
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  onClick={() => openEdit(tag)}
                  className="rounded p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
                >
                  <Edit className="h-4 w-4" />
                </button>
                <button
                  onClick={() => handleDelete(tag)}
                  className="rounded p-1.5 text-zinc-400 hover:bg-red-50 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create / Edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {editingTag ? "编辑标签" : "新建标签"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-700">
                名称
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="标签名称"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-700">
                颜色
              </label>
              <div className="flex flex-wrap gap-2">
                {PRESET_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setColor(c)}
                    className={`h-8 w-8 rounded-full border-2 transition-all ${
                      color === c ? "border-zinc-900 scale-110" : "border-transparent"
                    }`}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-700">
                描述（可选）
              </label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="标签描述"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
              >
                取消
              </Button>
              <Button type="submit" disabled={!name.trim() || submitting}>
                {submitting
                  ? "保存中..."
                  : editingTag
                    ? "更新"
                    : "创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
