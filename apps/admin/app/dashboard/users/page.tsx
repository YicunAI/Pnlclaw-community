"use client";

import { useState } from "react";
import { AdminHeader } from "@/components/layout/AdminHeader";
import { UserTable } from "@/components/users/UserTable";
import { BulkActionBar } from "@/components/users/BulkActionBar";
import { UserExportButton } from "@/components/users/UserExportButton";
import { useUsers } from "@/lib/hooks/useUsers";
import { useTags } from "@/lib/hooks/useTags";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

export default function UsersPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const { users, pagination, isLoading, mutate } = useUsers({
    page,
    limit: 20,
    search: search || undefined,
    status: statusFilter || undefined,
    tag: tagFilter || undefined,
  });

  const { tags } = useTags();

  return (
    <div>
      <AdminHeader title="用户管理" />
      <div className="p-6 space-y-4">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">
              用户管理
            </h2>
            {pagination && (
              <p className="text-sm text-zinc-500">
                共 {pagination.total.toLocaleString()} 位用户
              </p>
            )}
          </div>
          <UserExportButton />
        </div>

        {/* Loading state */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-zinc-300 border-t-zinc-900" />
          </div>
        ) : (
          <>
            <UserTable
              users={users ?? []}
              tags={tags}
              onSelectionChange={setSelectedIds}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              tagFilter={tagFilter}
              onTagFilterChange={setTagFilter}
              searchQuery={search}
              onSearchChange={(q) => {
                setSearch(q);
                setPage(1);
              }}
            />

            {/* Pagination */}
            {pagination && pagination.pages > 1 && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-zinc-500">
                  第 {pagination.page} / {pagination.pages} 页
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= pagination.pages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    下一页
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}

        {/* Bulk action bar */}
        <BulkActionBar
          selectedIds={selectedIds}
          onClear={() => setSelectedIds([])}
          onActionComplete={() => mutate()}
        />
      </div>
    </div>
  );
}
