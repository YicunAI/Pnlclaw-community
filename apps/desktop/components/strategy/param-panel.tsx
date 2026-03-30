"use client"

import { useCallback, type ReactNode } from "react"

import { useI18n } from "@/components/i18n/use-i18n"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import type { StrategyData } from "@/lib/api-client"

export interface ParamPanelProps {
  strategy: StrategyData
  onChange: (updated: Partial<StrategyData>) => void
}

type RuleRecord = Record<string, unknown>

function isRuleRecord(v: unknown): v is RuleRecord {
  return v !== null && typeof v === "object" && !Array.isArray(v)
}

function formatRuleLine(rule: unknown): ReactNode {
  if (!isRuleRecord(rule)) return <span className="text-muted-foreground">{String(rule)}</span>
  const ind = String(rule.indicator ?? "")
  const op = String(rule.operator ?? "").replace(/_/g, " ")
  const comp = rule.comparator
  const compRec = isRuleRecord(comp) ? comp : undefined
  const compInd = compRec ? String(compRec.indicator ?? "") : ""
  return (
    <>
      {ind}{" "}
      <span className="text-primary">{op}</span>
      {compInd ? ` ${compInd}` : ""}
    </>
  )
}

function sliderBounds(value: number): { min: number; max: number; step: number } {
  const step = value >= 10 ? 1 : 0.1
  if (value === 0) {
    return { min: 0, max: 100, step: 1 }
  }
  if (value < 0) {
    const abs = Math.abs(value)
    const maxNeg = -Math.max(1, Math.floor(abs * 0.2))
    let minNeg = Math.floor(value * 3)
    if (minNeg >= maxNeg) minNeg = maxNeg - step
    return { min: minNeg, max: maxNeg, step: abs >= 10 ? 1 : 0.1 }
  }
  const min = Math.max(1, Math.floor(value * 0.2))
  let max = Math.ceil(value * 3)
  if (max <= min) max = min + step
  return { min, max, step }
}

function RulesReadonlySection({
  title,
  rules,
  dirHeadingClass,
  emptyLabel,
}: {
  title: string
  rules: Record<string, unknown> | undefined
  dirHeadingClass: string
  emptyLabel: string
}) {
  const entries = Object.entries(rules ?? {})
  return (
    <div className="mt-4 space-y-2">
      <h3 className="text-xs font-medium uppercase text-muted-foreground">{title}</h3>
      {entries.length === 0 ? (
        <p className="text-xs text-muted-foreground">{emptyLabel}</p>
      ) : (
        entries.map(([dir, block]) => (
        <div key={dir} className="space-y-1 rounded bg-muted/30 p-2 font-mono text-xs">
          <div className={cn("font-medium", dirHeadingClass)}>{dir}:</div>
          {Array.isArray(block) ? (
            block.map((rule, i) => (
              <div key={i} className="ml-2 text-muted-foreground">
                {formatRuleLine(rule)}
              </div>
            ))
          ) : (
            <div className="ml-2 text-muted-foreground">{String(block)}</div>
          )}
        </div>
        ))
      )}
    </div>
  )
}

export function ParamPanel({ strategy, onChange }: ParamPanelProps) {
  const { t } = useI18n()
  const params = strategy.parameters ?? {}
  const paramEntries = Object.entries(params)
  const riskEntries = Object.entries(strategy.risk_params ?? {})

  const handleParamChange = useCallback(
    (key: string, next: unknown) => {
      onChange({
        parameters: {
          ...params,
          [key]: next,
        },
      })
    },
    [onChange, params]
  )

  const handleRiskChange = useCallback(
    (key: string, num: number) => {
      onChange({
        risk_params: {
          ...(strategy.risk_params ?? {}),
          [key]: num,
        },
      })
    },
    [onChange, strategy.risk_params]
  )

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h3 className="text-xs font-medium uppercase text-muted-foreground">{t("strategies.studio.paramsTab")}</h3>
        {paramEntries.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("strategies.studio.noParameters")}</p>
        ) : (
          paramEntries.map(([key, value]) => (
            <div key={key} className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <Label className="text-xs font-normal text-muted-foreground">{key}</Label>
                <span className="shrink-0 font-mono text-xs">{String(value)}</span>
              </div>
              {typeof value === "number" && (() => {
                const { min, max, step } = sliderBounds(value)
                return (
                  <div className="flex items-center gap-2">
                    <input
                      type="range"
                      min={min}
                      max={max}
                      step={step}
                      value={value}
                      onChange={(e) => handleParamChange(key, parseFloat(e.target.value))}
                      className="h-1.5 flex-1 accent-primary"
                    />
                    <input
                      type="number"
                      value={Number.isFinite(value) ? value : 0}
                      onChange={(e) => handleParamChange(key, parseFloat(e.target.value) || 0)}
                      className="h-7 w-16 rounded border border-border bg-muted/30 px-2 text-center font-mono text-xs"
                    />
                  </div>
                )
              })()}
              {typeof value === "string" && (
                <Input
                  type="text"
                  value={value}
                  onChange={(e) => handleParamChange(key, e.target.value)}
                  className="h-7 w-full font-mono text-xs"
                />
              )}
              {typeof value === "boolean" && (
                <div className="flex items-center gap-2">
                  <input
                    id={`param-${key}`}
                    type="checkbox"
                    checked={value}
                    onChange={(e) => handleParamChange(key, e.target.checked)}
                    className="h-4 w-4 rounded border-border accent-primary"
                  />
                  <Label htmlFor={`param-${key}`} className="text-xs font-normal text-muted-foreground">
                    {String(value)}
                  </Label>
                </div>
              )}
              {value !== null &&
                typeof value !== "number" &&
                typeof value !== "string" &&
                typeof value !== "boolean" && (
                  <Badge variant="outline" className="text-[10px] font-mono">
                    {JSON.stringify(value)}
                  </Badge>
                )}
            </div>
          ))
        )}
      </div>

      <RulesReadonlySection
        title={t("strategies.studio.entryRules")}
        rules={strategy.entry_rules}
        dirHeadingClass="text-emerald-400"
        emptyLabel={t("strategies.studio.emptySection")}
      />

      <RulesReadonlySection
        title={t("strategies.studio.exitRules")}
        rules={strategy.exit_rules}
        dirHeadingClass="text-red-400"
        emptyLabel={t("strategies.studio.emptySection")}
      />

      <div className="space-y-3">
        <h3 className="text-xs font-medium uppercase text-muted-foreground">{t("strategies.studio.riskControls")}</h3>
        {riskEntries.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("strategies.studio.emptySection")}</p>
        ) : (
          riskEntries.map(([key, value]) => {
            const num =
              typeof value === "number" && Number.isFinite(value)
                ? value
                : typeof value === "string"
                  ? parseFloat(value)
                  : NaN
            const safe = Number.isFinite(num) ? num : 0
            return (
              <div key={key} className="space-y-1.5">
                <Label className="text-xs font-normal text-muted-foreground">{key}</Label>
                <Input
                  type="number"
                  value={safe}
                  onChange={(e) => handleRiskChange(key, parseFloat(e.target.value) || 0)}
                  className="h-8 font-mono text-xs"
                />
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
