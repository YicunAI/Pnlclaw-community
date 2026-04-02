"use client";

import { useState, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPost, setAccessToken } from "@/lib/api";
import { useToast } from "@/components/ui/toast";

interface TOTPVerifyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onVerified: () => void;
  /** OAuth login step: required for `/auth/verify-totp`. Omit for `/admin/2fa/enable`. */
  partialToken?: string;
}

export function TOTPVerifyDialog({
  open,
  onOpenChange,
  onVerified,
  partialToken,
}: TOTPVerifyDialogProps) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (code.length !== 6) return;

    setLoading(true);
    try {
      if (partialToken) {
        const out = await apiPost<{ access_token?: string }>(
          "/auth/verify-totp",
          {
            code,
            partial_token: partialToken,
          }
        );
        if (out?.access_token) {
          setAccessToken(out.access_token);
        }
      } else {
        await apiPost("/admin/2fa/enable", { code });
      }
      toast({ title: "验证成功", description: "双因素认证验证通过" });
      onVerified();
      onOpenChange(false);
      setCode("");
    } catch {
      toast({
        title: "验证失败",
        description: "验证码无效，请重试",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }

  function handleCodeChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value.replace(/\D/g, "").slice(0, 6);
    setCode(val);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>双因素认证</DialogTitle>
          <DialogDescription>
            请输入验证器应用中的 6 位验证码
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="py-4">
            <Input
              ref={inputRef}
              value={code}
              onChange={handleCodeChange}
              placeholder="000000"
              maxLength={6}
              className="text-center text-2xl tracking-[0.5em] font-mono"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={code.length !== 6 || loading}>
              {loading ? "验证中..." : "验证"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
