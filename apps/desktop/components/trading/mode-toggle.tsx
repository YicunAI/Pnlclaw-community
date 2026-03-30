"use client"

import { useState, useEffect } from "react"
import { getTradingMode, setTradingMode } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"
import { cn } from "@/lib/utils"

export function ModeToggle() {
  const { t } = useI18n()
  const [mode, setMode] = useState<"paper" | "live">("paper")
  const [loading, setLoading] = useState(false)
  const [liveWarning, setLiveWarning] = useState(false)

  useEffect(() => {
    getTradingMode().then((res) => {
      if (res.data) setMode(res.data.mode as "paper" | "live")
    })
  }, [])

  async function handleToggle(target: "paper" | "live") {
    if (target === mode || loading) return

    if (target === "live") {
      setLiveWarning(true)
      setTimeout(() => setLiveWarning(false), 3000)
      return
    }

    setLoading(true)
    const res = await setTradingMode(target)
    if (res.data) setMode(res.data.mode as "paper" | "live")
    if (res.error) setLiveWarning(true)
    setLoading(false)
  }

  return (
    <div className="flex items-center gap-2">
      <div className="inline-flex rounded-lg border border-border p-1 bg-muted/40">
        <button
          onClick={() => handleToggle("paper")}
          disabled={loading}
          className={cn(
            "px-4 py-1.5 rounded-md text-sm font-medium transition-all",
            mode === "paper"
              ? "bg-blue-600 text-white shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {t("trading.paper")}
        </button>
        <button
          onClick={() => handleToggle("live")}
          disabled={loading}
          className={cn(
            "px-4 py-1.5 rounded-md text-sm font-medium transition-all",
            mode === "live"
              ? "bg-red-600 text-white shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {t("trading.live")}
        </button>
      </div>
      {liveWarning && (
        <span className="text-xs text-amber-500 animate-in fade-in">
          {"Live trading is not available in v0.1"}
        </span>
      )}
    </div>
  )
}
