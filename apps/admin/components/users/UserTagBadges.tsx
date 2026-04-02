"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X, Plus } from "lucide-react";
import { apiPost, apiDelete } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import type { UserTag } from "@/lib/types";

interface UserTagBadgesProps {
  userId: string;
  userTags: UserTag[];
  allTags: UserTag[];
  onTagsChanged: () => void;
}

export function UserTagBadges({
  userId,
  userTags,
  allTags,
  onTagsChanged,
}: UserTagBadgesProps) {
  const [showAdd, setShowAdd] = useState(false);
  const { toast } = useToast();

  const availableTags = allTags.filter(
    (t) => !userTags.some((ut) => ut.id === t.id)
  );

  async function addTag(tagId: string) {
    try {
      await apiPost(`/admin/users/${userId}/tags`, { tag_id: tagId });
      onTagsChanged();
      setShowAdd(false);
    } catch {
      toast({
        title: "错误",
        description: "添加标签失败",
        variant: "destructive",
      });
    }
  }

  async function removeTag(tagId: string) {
    try {
      await apiDelete(`/admin/users/${userId}/tags/${tagId}`);
      onTagsChanged();
    } catch {
      toast({
        title: "错误",
        description: "移除标签失败",
        variant: "destructive",
      });
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {userTags.map((tag) => (
          <Badge
            key={tag.id}
            className="flex items-center gap-1 pr-1"
            style={{ backgroundColor: tag.color + "20", color: tag.color }}
          >
            {tag.name}
            <button
              onClick={() => removeTag(tag.id)}
              className="ml-1 rounded-full p-0.5 hover:bg-black/10"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <Button
          variant="outline"
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={() => setShowAdd(!showAdd)}
        >
          <Plus className="h-3 w-3 mr-1" />
          添加标签
        </Button>
      </div>

      {showAdd && availableTags.length > 0 && (
        <div className="flex flex-wrap gap-1 rounded-md border border-zinc-200 p-2">
          {availableTags.map((tag) => (
            <button
              key={tag.id}
              onClick={() => addTag(tag.id)}
              className="rounded-full px-2.5 py-0.5 text-xs font-medium hover:opacity-80 transition-opacity"
              style={{ backgroundColor: tag.color + "20", color: tag.color }}
            >
              + {tag.name}
            </button>
          ))}
        </div>
      )}

      {showAdd && availableTags.length === 0 && (
        <p className="text-xs text-zinc-500">没有更多可用标签</p>
      )}
    </div>
  );
}
