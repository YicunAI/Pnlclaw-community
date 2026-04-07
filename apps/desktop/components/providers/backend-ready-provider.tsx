"use client"

import { useEffect, useState, useCallback, useRef } from "react"

const HEALTH_URL = "http://127.0.0.1:8080/api/v1/health"
const MAX_RETRIES = 60
const POLL_INTERVAL = 1000

export function BackendReadyProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"checking" | "ready" | "failed">("checking")
  const [attempt, setAttempt] = useState(0)
  const [lastError, setLastError] = useState("")
  const debugRef = useRef<string[]>([])

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(HEALTH_URL, {
        signal: AbortSignal.timeout(5000),
        mode: "cors",
      })
      debugRef.current.push(`[${new Date().toISOString()}] status=${res.status} ok=${res.ok}`)
      if (res.ok) {
        setStatus("ready")
        return true
      }
      setLastError(`HTTP ${res.status}`)
    } catch (err) {
      const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err)
      debugRef.current.push(`[${new Date().toISOString()}] error: ${msg}`)
      setLastError(msg)
    }
    return false
  }, [])

  const startPolling = useCallback(async () => {
    setStatus("checking")
    setAttempt(0)
    for (let i = 0; i < MAX_RETRIES; i++) {
      setAttempt(i + 1)
      const ok = await checkHealth()
      if (ok) return
      await new Promise((r) => setTimeout(r, POLL_INTERVAL))
    }
    setStatus("failed")
  }, [checkHealth])

  useEffect(() => {
    startPolling()
  }, [startPolling])

  if (status === "ready") {
    return <>{children}</>
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-6 text-center">
        <div className="relative">
          <div className="h-16 w-16 rounded-2xl bg-primary/10 flex items-center justify-center">
            <span className="text-2xl font-bold text-primary">P</span>
          </div>
          {status === "checking" && (
            <div className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full border-2 border-background bg-amber-500 animate-pulse" />
          )}
          {status === "failed" && (
            <div className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full border-2 border-background bg-red-500" />
          )}
        </div>

        {status === "checking" && (
          <>
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-foreground">
                Starting PnLClaw...
              </h2>
              <p className="text-sm text-muted-foreground">
                Waiting for backend service
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-32 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-300"
                  style={{ width: `${Math.min((attempt / MAX_RETRIES) * 100, 95)}%` }}
                />
              </div>
              <span className="text-xs text-muted-foreground tabular-nums">
                {attempt}s
              </span>
            </div>
          </>
        )}

        {status === "failed" && (
          <>
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-destructive">
                Backend Unavailable
              </h2>
              <p className="text-sm text-muted-foreground max-w-xs">
                Could not connect to the PnLClaw backend service.
                Please check if the application started correctly.
              </p>
              {lastError && (
                <p className="text-xs text-red-400 font-mono max-w-md break-all mt-2">
                  Error: {lastError}
                </p>
              )}
              <details className="mt-2 text-left">
                <summary className="text-xs text-muted-foreground cursor-pointer">Debug log</summary>
                <pre className="text-xs text-muted-foreground font-mono mt-1 max-h-40 overflow-auto whitespace-pre-wrap">
                  {debugRef.current.join("\n") || "No debug entries"}
                </pre>
              </details>
            </div>
            <button
              type="button"
              onClick={startPolling}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Retry
            </button>
          </>
        )}
      </div>
    </div>
  )
}
