"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { Download, FileJson, FileSpreadsheet } from "lucide-react";
import { apiFetchBlob } from "@/lib/api";
import { useToast } from "@/components/ui/toast";

export function UserExportButton() {
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  async function downloadExport(format: "csv" | "json") {
    setBusy(true);
    try {
      const blob = await apiFetchBlob(`/admin/users/export?format=${format}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `users_export.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast({
        title: "导出失败",
        description: "导出文件下载失败，请重试",
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={busy}>
          <Download className="mr-1 h-4 w-4" />
          {busy ? "导出中..." : "导出"}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => downloadExport("csv")}>
          <FileSpreadsheet className="mr-2 h-4 w-4" />
          导出为 CSV
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => downloadExport("json")}>
          <FileJson className="mr-2 h-4 w-4" />
          导出为 JSON
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
