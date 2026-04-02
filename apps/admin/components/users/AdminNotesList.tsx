"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPost, apiDelete } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Trash2, Send } from "lucide-react";
import type { AdminNote } from "@/lib/types";

interface AdminNotesListProps {
  userId: string;
  notes: AdminNote[];
  onNotesChanged: () => void;
}

export function AdminNotesList({
  userId,
  notes,
  onNotesChanged,
}: AdminNotesListProps) {
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { toast } = useToast();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;

    setSubmitting(true);
    try {
      await apiPost(`/admin/users/${userId}/notes`, {
        content: content.trim(),
      });
      setContent("");
      onNotesChanged();
    } catch {
      toast({
        title: "错误",
        description: "添加备注失败",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(noteId: string) {
    try {
      await apiDelete(`/admin/users/${userId}/notes/${noteId}`);
      onNotesChanged();
    } catch {
      toast({
        title: "错误",
        description: "删除备注失败",
        variant: "destructive",
      });
    }
  }

  return (
    <div className="space-y-4">
      {/* Add note form */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="添加备注..."
          className="flex-1"
        />
        <Button type="submit" size="sm" disabled={!content.trim() || submitting}>
          <Send className="h-4 w-4 mr-1" />
          {submitting ? "添加中..." : "添加"}
        </Button>
      </form>

      {/* Notes list */}
      {notes.length === 0 ? (
        <p className="py-4 text-center text-sm text-zinc-500">
          暂无备注
        </p>
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <div
              key={note.id}
              className="flex items-start justify-between rounded-md border border-zinc-200 p-3"
            >
              <div className="flex-1">
                <p className="text-sm text-zinc-900">{note.content}</p>
                <p className="mt-1 text-xs text-zinc-500">
                  {note.admin_name} &middot;{" "}
                  {new Date(note.created_at).toLocaleString()}
                </p>
              </div>
              <button
                onClick={() => handleDelete(note.id)}
                className="ml-2 rounded p-1 text-zinc-400 hover:text-red-600 hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
