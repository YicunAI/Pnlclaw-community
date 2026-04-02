"use client";

import { useState, useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type RowSelectionState,
} from "@tanstack/react-table";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import {
  ArrowUpDown,
  MoreHorizontal,
  Eye,
  Ban,
  CheckCircle,
} from "lucide-react";
import Link from "next/link";
import type { User, UserTag } from "@/lib/types";

interface UserTableProps {
  users: User[];
  tags: UserTag[];
  onSelectionChange?: (selectedIds: string[]) => void;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  tagFilter: string;
  onTagFilterChange: (tag: string) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
}

const statusVariantMap: Record<string, "success" | "warning" | "destructive"> =
  {
    active: "success",
    suspended: "warning",
    banned: "destructive",
  };

export function UserTable({
  users,
  tags,
  onSelectionChange,
  statusFilter,
  onStatusFilterChange,
  tagFilter,
  onTagFilterChange,
  searchQuery,
  onSearchChange,
}: UserTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const columns = useMemo<ColumnDef<User>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="h-4 w-4 rounded border-zinc-300"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="h-4 w-4 rounded border-zinc-300"
          />
        ),
        enableSorting: false,
      },
      {
        accessorKey: "avatar_url",
        header: "",
        cell: ({ row }) => (
          <div className="flex items-center justify-center">
            {row.original.avatar_url ? (
              <img
                src={row.original.avatar_url}
                alt=""
                className="h-8 w-8 rounded-full"
              />
            ) : (
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-200 text-xs font-medium text-zinc-600">
                {(
                  row.original.display_name ||
                  row.original.name ||
                  ""
                )
                  .charAt(0)
                  .toUpperCase() || "?"}
              </div>
            )}
          </div>
        ),
        enableSorting: false,
      },
      {
        accessorKey: "name",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            名称 <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
      },
      {
        accessorKey: "email",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            邮箱 <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
      },
      {
        id: "providers",
        header: "登录方式",
        cell: ({ row }) => (
          <div className="flex gap-1">
            {(row.original.oauth_accounts ?? []).map((acc) => (
              <Badge key={acc.id} variant="outline" className="text-xs">
                {acc.provider}
              </Badge>
            ))}
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "状态",
        cell: ({ row }) => (
          <Badge variant={statusVariantMap[row.original.status] ?? "default"}>
            {row.original.status}
          </Badge>
        ),
      },
      {
        id: "tags",
        header: "标签",
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {(row.original.tags ?? []).map((tag) => (
              <Badge
                key={tag.id}
                className="text-xs"
                style={{ backgroundColor: tag.color + "20", color: tag.color }}
              >
                {tag.name}
              </Badge>
            ))}
          </div>
        ),
      },
      {
        accessorKey: "last_login",
        header: ({ column }) => (
          <button
            className="flex items-center gap-1"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            最近登录 <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) =>
          row.original.last_login
            ? new Date(row.original.last_login).toLocaleDateString()
            : "从未登录",
      },
      {
        accessorKey: "country",
        header: "国家/地区",
        cell: ({ row }) => row.original.country ?? "-",
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <Link href={`/dashboard/users/${row.original.id}`}>
                  <Eye className="mr-2 h-4 w-4" />
                  查看详情
                </Link>
              </DropdownMenuItem>
              {row.original.status !== "banned" && (
                <DropdownMenuItem className="text-red-600">
                  <Ban className="mr-2 h-4 w-4" />
                  封禁用户
                </DropdownMenuItem>
              )}
              {row.original.status !== "active" && (
                <DropdownMenuItem className="text-green-600">
                  <CheckCircle className="mr-2 h-4 w-4" />
                  激活
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        ),
      },
    ],
    []
  );

  const table = useReactTable({
    data: users,
    columns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: (updater) => {
      const next =
        typeof updater === "function" ? updater(rowSelection) : updater;
      setRowSelection(next);
      const selectedIds = Object.keys(next)
        .filter((k) => next[k])
        .map((idx) => users[Number(idx)]?.id)
        .filter(Boolean) as string[];
      onSelectionChange?.(selectedIds);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="搜索用户..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="max-w-xs"
        />
        <select
          value={statusFilter}
          onChange={(e) => onStatusFilterChange(e.target.value)}
          className="h-9 rounded-md border border-zinc-300 bg-white px-3 text-sm"
        >
          <option value="">全部状态</option>
          <option value="active">活跃</option>
          <option value="suspended">已暂停</option>
          <option value="banned">已封禁</option>
        </select>
        <select
          value={tagFilter}
          onChange={(e) => onTagFilterChange(e.target.value)}
          className="h-9 rounded-md border border-zinc-300 bg-white px-3 text-sm"
        >
          <option value="">全部标签</option>
          {tags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="rounded-md border border-zinc-200">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center text-zinc-500"
                >
                  未找到用户
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
