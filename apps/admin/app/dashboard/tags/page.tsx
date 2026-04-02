"use client";

import { AdminHeader } from "@/components/layout/AdminHeader";
import { TagManager } from "@/components/tags/TagManager";

export default function TagsPage() {
  return (
    <div>
      <AdminHeader title="标签" />
      <div className="p-6">
        <TagManager />
      </div>
    </div>
  );
}
