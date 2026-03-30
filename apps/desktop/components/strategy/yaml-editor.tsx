"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import yaml from "js-yaml"

import { useI18n } from "@/components/i18n/use-i18n"
import type { StrategyData } from "@/lib/api-client"

export interface YamlEditorProps {
  strategy: StrategyData
  onChange: (updated: Partial<StrategyData>) => void
}

function buildEditablePayload(strategy: StrategyData) {
  return {
    name: strategy.name ?? "",
    type: strategy.type ?? "",
    description: strategy.description ?? "",
    symbols: strategy.symbols ?? [],
    interval: strategy.interval ?? "",
    direction: strategy.direction ?? "neutral",
    parameters: strategy.parameters ?? {},
    entry_rules: strategy.entry_rules ?? {},
    exit_rules: strategy.exit_rules ?? {},
    risk_params: strategy.risk_params ?? {},
    tags: strategy.tags ?? [],
  }
}

function isDirection(v: unknown): v is NonNullable<StrategyData["direction"]> {
  return v === "long_only" || v === "short_only" || v === "neutral"
}

function parsedToPartial(loaded: unknown): Partial<StrategyData> {
  if (loaded === null || typeof loaded !== "object" || Array.isArray(loaded)) {
    throw new Error("Root must be a mapping")
  }
  const o = loaded as Record<string, unknown>
  const out: Partial<StrategyData> = {}

  if (typeof o.name === "string") out.name = o.name
  if (typeof o.type === "string") out.type = o.type
  if (typeof o.description === "string") out.description = o.description
  if (typeof o.interval === "string") out.interval = o.interval
  if (isDirection(o.direction)) out.direction = o.direction

  if (Array.isArray(o.symbols)) {
    out.symbols = o.symbols.filter((x): x is string => typeof x === "string")
  }
  if (Array.isArray(o.tags)) {
    out.tags = o.tags.filter((x): x is string => typeof x === "string")
  }

  if (o.parameters !== undefined && typeof o.parameters === "object" && !Array.isArray(o.parameters)) {
    out.parameters = { ...(o.parameters as Record<string, unknown>) }
  }
  if (o.entry_rules !== undefined && typeof o.entry_rules === "object" && !Array.isArray(o.entry_rules)) {
    out.entry_rules = { ...(o.entry_rules as Record<string, unknown>) }
  }
  if (o.exit_rules !== undefined && typeof o.exit_rules === "object" && !Array.isArray(o.exit_rules)) {
    out.exit_rules = { ...(o.exit_rules as Record<string, unknown>) }
  }
  if (o.risk_params !== undefined && typeof o.risk_params === "object" && !Array.isArray(o.risk_params)) {
    out.risk_params = { ...(o.risk_params as Record<string, unknown>) }
  }

  return out
}

export function YamlEditor({ strategy, onChange }: YamlEditorProps) {
  const { t } = useI18n()
  const snapshot = useMemo(() => buildEditablePayload(strategy), [strategy])
  const snapshotKey = useMemo(() => JSON.stringify(snapshot), [snapshot])

  const [yamlText, setYamlText] = useState(() =>
    yaml.dump(snapshot, { lineWidth: -1, noRefs: true, sortKeys: false })
  )
  const [parseError, setParseError] = useState<string | null>(null)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const gutterRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setYamlText(yaml.dump(buildEditablePayload(strategy), { lineWidth: -1, noRefs: true, sortKeys: false }))
    setParseError(null)
  }, [snapshotKey, strategy])

  const lineNumbers = useMemo(() => {
    const n = yamlText.split("\n").length
    return Array.from({ length: n }, (_, i) => i + 1)
  }, [yamlText])

  const syncGutterScroll = useCallback(() => {
    const ta = textareaRef.current
    const g = gutterRef.current
    if (ta && g) g.scrollTop = ta.scrollTop
  }, [])

  const handleParse = useCallback(() => {
    try {
      const loaded = yaml.load(yamlText)
      const partial = parsedToPartial(loaded)
      setParseError(null)
      onChange(partial)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setParseError(t("strategies.studio.yamlError", { message }))
    }
  }, [yamlText, onChange, t])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "s" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        handleParse()
      }
    },
    [handleParse]
  )

  return (
    <div className="space-y-2">
      <p className="text-[10px] text-muted-foreground">{t("strategies.studio.yamlSaveHint")}</p>
      <div className="flex min-h-[400px] w-full overflow-hidden rounded-lg border border-border bg-muted/30">
        <div
          ref={gutterRef}
          className="w-9 shrink-0 overflow-y-auto overflow-x-hidden border-r border-border py-4 pl-2 pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          aria-hidden
        >
          <div className="font-mono text-[10px] leading-5 text-muted-foreground">
            {lineNumbers.map((num) => (
              <div key={num} className="h-5 text-right tabular-nums">
                {num}
              </div>
            ))}
          </div>
        </div>
        <textarea
          ref={textareaRef}
          className="min-h-[400px] w-full flex-1 resize-y border-0 bg-transparent p-4 font-mono text-xs leading-5 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          value={yamlText}
          onChange={(e) => setYamlText(e.target.value)}
          onBlur={handleParse}
          onKeyDown={onKeyDown}
          onScroll={syncGutterScroll}
          spellCheck={false}
        />
      </div>
      {parseError && <p className="text-xs text-red-400">{parseError}</p>}
    </div>
  )
}
