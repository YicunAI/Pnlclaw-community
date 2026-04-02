"use client";

import { useState } from "react";
import { AdminHeader } from "@/components/layout/AdminHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TOTPVerifyDialog } from "@/components/auth/TOTPVerifyDialog";
import { useAuthContext } from "@/components/auth/AuthProvider";
import { apiPost } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import { Shield, QrCode } from "lucide-react";

export default function SettingsPage() {
  const { user } = useAuthContext();
  const { toast } = useToast();
  const [totpDialogOpen, setTotpDialogOpen] = useState(false);
  const [setupQR, setSetupQR] = useState<string | null>(null);

  async function enableTOTP() {
    try {
      const data = await apiPost<{
        qr_code: string;
      }>("/admin/2fa/setup");
      setSetupQR(data.qr_code);
      setTotpDialogOpen(true);
    } catch {
      toast({
        title: "错误",
        description: "双因素认证设置失败",
        variant: "destructive",
      });
    }
  }

  async function disableTOTP() {
    const code = window.prompt(
      "请输入当前的 6 位验证码以禁用双因素认证："
    );
    if (!code || code.length !== 6) {
      if (code !== null) {
        toast({
        title: "无效验证码",
        description: "请输入 6 位验证码",
          variant: "destructive",
        });
      }
      return;
    }
    try {
      await apiPost("/admin/2fa/disable", { code });
      toast({ title: "双因素认证已禁用" });
    } catch {
      toast({
        title: "错误",
        description: "禁用双因素认证失败",
        variant: "destructive",
      });
    }
  }

  const displayName = user?.display_name || user?.name;

  return (
    <div>
      <AdminHeader title="设置" />
      <div className="p-6 space-y-8">
        <section className="rounded-lg border border-zinc-200 bg-white p-6">
          <div className="flex items-center gap-3 mb-4">
            <Shield className="h-5 w-5 text-zinc-700" />
            <h2 className="text-lg font-semibold text-zinc-900">
              双因素认证
            </h2>
          </div>
          <p className="text-sm text-zinc-500 mb-4">
            通过启用验证器应用的双因素认证，为您的管理员账户添加额外的安全层。
          </p>

          {setupQR && (
            <div className="mb-4 rounded-md border border-zinc-200 p-4 text-center">
              <p className="text-sm text-zinc-700 mb-2">
                使用验证器应用扫描此二维码：
              </p>
              <img
                src={setupQR}
                alt="TOTP QR Code"
                className="mx-auto h-48 w-48"
              />
            </div>
          )}

          <div className="flex gap-2">
            <Button onClick={enableTOTP}>
              <QrCode className="mr-1 h-4 w-4" />
              启用双因素认证
            </Button>
            <Button variant="outline" onClick={disableTOTP}>
              禁用双因素认证
            </Button>
          </div>
        </section>

        <section className="rounded-lg border border-zinc-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-zinc-900 mb-4">
            账户信息
          </h2>
          <div className="grid gap-3 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-500">名称</span>
              <span className="font-medium text-zinc-900">
                {displayName ?? "-"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">邮箱</span>
              <span className="font-medium text-zinc-900">
                {user?.email ?? "-"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">角色</span>
              <Badge variant="outline">{user?.role ?? "-"}</Badge>
            </div>
          </div>
        </section>
      </div>

      <TOTPVerifyDialog
        open={totpDialogOpen}
        onOpenChange={setTotpDialogOpen}
        onVerified={() => {
          setSetupQR(null);
          toast({
            title: "双因素认证已启用",
            description: "双因素认证现已生效",
          });
        }}
      />
    </div>
  );
}
