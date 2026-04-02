"use client";

import { Badge } from "@/components/ui/badge";
import { User as UserIcon, Calendar, Globe, Shield } from "lucide-react";
import type { User } from "@/lib/types";

interface UserDetailCardProps {
  user: User;
}

const statusVariantMap: Record<string, "success" | "warning" | "destructive"> =
  {
    active: "success",
    suspended: "warning",
    banned: "destructive",
  };

export function UserDetailCard({ user }: UserDetailCardProps) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-6">
      <div className="flex items-start gap-4">
        {/* Avatar */}
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt={user.name}
            className="h-16 w-16 rounded-full"
          />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-zinc-200 text-zinc-600">
            <UserIcon className="h-8 w-8" />
          </div>
        )}

        {/* Info */}
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold text-zinc-900">{user.name}</h2>
            <Badge variant={statusVariantMap[user.status] ?? "default"}>
              {user.status}
            </Badge>
          </div>
          <p className="text-sm text-zinc-500">{user.email}</p>

          <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div className="flex items-center gap-2 text-zinc-600">
              <Shield className="h-4 w-4" />
              <span>角色：{user.role}</span>
            </div>
            <div className="flex items-center gap-2 text-zinc-600">
              <Globe className="h-4 w-4" />
              <span>
                {user.country ?? "未知"}
                {user.city ? `, ${user.city}` : ""}
              </span>
            </div>
            <div className="flex items-center gap-2 text-zinc-600">
              <Calendar className="h-4 w-4" />
              <span>
                注册于 {new Date(user.created_at).toLocaleDateString()}
              </span>
            </div>
            <div className="flex items-center gap-2 text-zinc-600">
              <Calendar className="h-4 w-4" />
              <span>
                最近登录{" "}
                {user.last_login
                  ? new Date(user.last_login).toLocaleDateString()
                  : "从未登录"}
              </span>
            </div>
          </div>

          {/* OAuth accounts */}
          {(user.oauth_accounts ?? []).length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-zinc-500 mb-2">
                关联账户
              </p>
              <div className="flex gap-2">
                {(user.oauth_accounts ?? []).map((acc) => (
                  <Badge key={acc.id} variant="outline">
                    {acc.provider}
                    {acc.email ? ` (${acc.email})` : ""}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
