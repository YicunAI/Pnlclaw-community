"use client"

import React from "react"
import { RequireAuth } from "@/components/auth/require-auth"
import { useI18n } from "@/components/i18n/use-i18n"
import { AlertTriangle } from "lucide-react"

export default function TradingPage() {
  const { t } = useI18n()

  return (
    <RequireAuth>
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("trading.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("trading.subtitle")}
          </p>
        </div>
      </div>

      {/* ⚠️ 实盘交易暂未开放提示 */}
      <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
        <div className="space-y-1 text-sm">
          <p className="font-semibold text-amber-400">
            🚧 因涉及资产安全、网络攻防等安全问题，秉持用户资产第一的原则，当前版本暂不支持实盘交易
          </p>
          <p className="text-amber-300/80">
            实盘交易功能正在紧锣密鼓地开发中，将会在后续版本推出。
          </p>
        </div>
      </div>
    </div>
    </RequireAuth>
  )
}
