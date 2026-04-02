"use client";

import { AdminHeader } from "@/components/layout/AdminHeader";
import { InvitationTable } from "@/components/invitations/InvitationTable";
import { CreateInviteDialog } from "@/components/invitations/CreateInviteDialog";
import { useInvitations } from "@/lib/hooks/useInvitations";

export default function InvitationsPage() {
  const { invitations, isLoading, mutate } = useInvitations();

  return (
    <div>
      <AdminHeader title="邀请码" />
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">
              邀请码管理
            </h2>
            <p className="text-sm text-zinc-500">
              管理新用户的邀请码
            </p>
          </div>
          <CreateInviteDialog onCreated={() => mutate()} />
        </div>

        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-zinc-300 border-t-zinc-900" />
          </div>
        ) : (
          <div className="rounded-md border border-zinc-200">
            <InvitationTable
              invitations={invitations}
              onInvitationsChanged={() => mutate()}
            />
          </div>
        )}
      </div>
    </div>
  );
}
