"use client"

import { useState, useEffect } from "react"
import { getTradingMode, setTradingMode } from "@/lib/api-client"
import { cn } from "@/lib/utils"

export function ModeToggle() {
  const [mode, setMode] = useState<"paper" | "live">("paper")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getTradingMode().then((res) => {
      if (res.data) setMode(res.data.mode as "paper" | "live")
    })
  }, [])

  async function handleToggle(target: "paper" | "live") {
    if (target === mode || loading) return
    setLoading(true)
    const res = await setTradingMode(target)
    if (res.data) setMode(res.data.mode as "paper" | "live")
    setLoading(false)
  }

  return (
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
        Paper
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
        Live
      </button>
    </div>
  )
}
