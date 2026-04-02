"use client";

import { use } from "react";
import { AdminHeader } from "@/components/layout/AdminHeader";
import { UserDetailCard } from "@/components/users/UserDetailCard";
import { UserActionButtons } from "@/components/users/UserActionButtons";
import { UserTagBadges } from "@/components/users/UserTagBadges";
import { LoginHistoryTable } from "@/components/users/LoginHistoryTable";
import { AdminNotesList } from "@/components/users/AdminNotesList";
import {
  useUser,
  useUserActivity,
  useUserLoginHistory,
  useUserSessions,
  useUserNotes,
} from "@/lib/hooks/useUsers";
import { useTags } from "@/lib/hooks/useTags";
import * as Tabs from "@radix-ui/react-tabs";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiDelete } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { ArrowLeft, Trash2 } from "lucide-react";
import Link from "next/link";

export default function UserDetailPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = use(params);
  const { user, isLoading, mutate: mutateUser } = useUser(userId);
  const { activity } = useUserActivity(userId);
  const { loginHistory } = useUserLoginHistory(userId);
  const { sessions, mutate: mutateSessions } = useUserSessions(userId);
  const { notes, mutate: mutateNotes } = useUserNotes(userId);
  const { tags: allTags } = useTags();
  const { toast } = useToast();

  async function revokeSession(sessionId: string) {
    try {
      await apiDelete(`/admin/sessions/${sessionId}`);
      toast({ title: "会话已撤销" });
      mutateSessions();
    } catch {
      toast({
        title: "错误",
        description: "撤销会话失败",
        variant: "destructive",
      });
    }
  }

  if (isLoading || !user) {
    return (
      <div>
        <AdminHeader title="用户详情" />
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-zinc-300 border-t-zinc-900" />
        </div>
      </div>
    );
  }

  return (
    <div>
      <AdminHeader title="用户详情" />
      <div className="p-6 space-y-6">
        {/* Back link */}
        <Link
          href="/dashboard/users"
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900"
        >
          <ArrowLeft className="h-4 w-4" />
          返回用户列表
        </Link>

        {/* User card + actions */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex-1">
            <UserDetailCard user={user} />
          </div>
          <UserActionButtons user={user} onActionComplete={() => mutateUser()} />
        </div>

        {/* Tabs */}
        <Tabs.Root defaultValue="activity">
          <Tabs.List className="flex border-b border-zinc-200">
            {([
              { value: "activity", label: "活动记录" },
              { value: "login-history", label: "登录历史" },
              { value: "sessions", label: "会话" },
              { value: "tags", label: "标签" },
              { value: "notes", label: "备注" },
            ] as const).map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className="px-4 py-2 text-sm font-medium text-zinc-500 border-b-2 border-transparent data-[state=active]:border-zinc-900 data-[state=active]:text-zinc-900"
              >
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          {/* Activity tab */}
          <Tabs.Content value="activity" className="pt-4">
            {activity.length === 0 ? (
              <p className="py-8 text-center text-sm text-zinc-500">
                暂无活动记录
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>时间</TableHead>
                    <TableHead>操作</TableHead>
                    <TableHead>详情</TableHead>
                    <TableHead>IP</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activity.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-sm">
                        {new Date(entry.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{entry.action}</Badge>
                      </TableCell>
                      <TableCell className="text-sm">
                        {entry.details ?? "-"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {entry.ip_address ?? "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Tabs.Content>

          {/* Login History tab */}
          <Tabs.Content value="login-history" className="pt-4">
            <LoginHistoryTable entries={loginHistory} />
          </Tabs.Content>

          {/* Sessions tab */}
          <Tabs.Content value="sessions" className="pt-4">
            {sessions.length === 0 ? (
              <p className="py-8 text-center text-sm text-zinc-500">
                暂无活跃会话
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>设备</TableHead>
                    <TableHead>IP</TableHead>
                    <TableHead>位置</TableHead>
                    <TableHead>最近活跃</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sessions.map((session) => (
                    <TableRow key={session.id}>
                      <TableCell className="text-sm">
                        {[session.browser, session.os]
                          .filter(Boolean)
                          .join(" / ") || session.user_agent}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {session.ip_address}
                      </TableCell>
                      <TableCell className="text-sm">
                        {[session.city, session.country]
                          .filter(Boolean)
                          .join(", ") || "-"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {new Date(session.last_active).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        {session.is_current ? (
                          <Badge variant="success">当前</Badge>
                        ) : (
                          <Badge variant="default">活跃</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {!session.is_current && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-red-600"
                            onClick={() => revokeSession(session.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Tabs.Content>

          {/* Tags tab */}
          <Tabs.Content value="tags" className="pt-4">
            <UserTagBadges
              userId={userId}
              userTags={user.tags ?? []}
              allTags={allTags}
              onTagsChanged={() => mutateUser()}
            />
          </Tabs.Content>

          {/* Notes tab */}
          <Tabs.Content value="notes" className="pt-4">
            <AdminNotesList
              userId={userId}
              notes={notes}
              onNotesChanged={() => mutateNotes()}
            />
          </Tabs.Content>
        </Tabs.Root>
      </div>
    </div>
  );
}
