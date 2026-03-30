"use client"

import { useRouter } from "next/navigation"
import { ArrowRight } from "lucide-react"

import { useI18n } from "@/components/i18n/use-i18n"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { BacktestData, StrategyData } from "@/lib/api-client"

export interface StrategyTableProps {
  strategies: StrategyData[]
  getLatestBacktest: (strategyId: string) => BacktestData | null | undefined
}

function directionKey(d?: string): string {
  if (d === "short_only") return "strategies.card.dirShort"
  if (d === "neutral") return "strategies.card.dirNeutral"
  return "strategies.card.dirLong"
}

export function StrategyTable({ strategies, getLatestBacktest }: StrategyTableProps) {
  const router = useRouter()
  const { t } = useI18n()

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="text-xs">{t("strategies.table.name")}</TableHead>
          <TableHead className="text-xs">{t("strategies.table.type")}</TableHead>
          <TableHead className="text-xs">{t("strategies.table.symbol")}</TableHead>
          <TableHead className="text-xs">{t("strategies.table.interval")}</TableHead>
          <TableHead className="text-xs">{t("strategies.table.direction")}</TableHead>
          <TableHead className="text-xs">{t("strategies.table.state")}</TableHead>
          <TableHead className="text-xs text-right">{t("strategies.table.sharpe")}</TableHead>
          <TableHead className="text-xs text-right">{t("strategies.table.return")}</TableHead>
          <TableHead className="text-xs text-right">{t("strategies.table.maxDD")}</TableHead>
          <TableHead className="text-xs" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {strategies.map((s) => {
          const bt = getLatestBacktest(s.id)
          const metrics = bt?.result?.metrics
          const sharpe = metrics?.sharpe_ratio ?? bt?.sharpe_ratio ?? null
          const ret = metrics?.total_return ?? bt?.total_return ?? null
          const dd = metrics?.max_drawdown ?? bt?.max_drawdown ?? null
          return (
            <TableRow
              key={s.id}
              className="cursor-pointer hover:bg-muted/50"
              onClick={() => router.push(`/strategies/${s.id}/studio`)}
            >
              <TableCell className="text-xs font-medium">{s.name}</TableCell>
              <TableCell>
                <Badge variant="outline" className="text-[10px]">
                  {s.type}
                </Badge>
              </TableCell>
              <TableCell className="text-xs">{s.symbols?.join(", ")}</TableCell>
              <TableCell className="text-xs">{s.interval}</TableCell>
              <TableCell className="text-xs">{t(directionKey(s.direction) as Parameters<typeof t>[0])}</TableCell>
              <TableCell>
                <Badge variant="outline" className="text-[10px]">
                  {s.lifecycle_state ?? "draft"}
                </Badge>
              </TableCell>
              <TableCell className="text-right font-mono text-xs">
                {sharpe != null ? sharpe.toFixed(2) : "—"}
              </TableCell>
              <TableCell
                className={`text-right font-mono text-xs ${ret != null && ret >= 0 ? "text-emerald-400" : "text-red-400"}`}
              >
                {ret != null ? `${(ret * 100).toFixed(1)}%` : "—"}
              </TableCell>
              <TableCell className="text-right font-mono text-xs text-red-400">
                {dd != null ? `${(dd * 100).toFixed(1)}%` : "—"}
              </TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  aria-label={t("strategies.hub.openStudio")}
                  onClick={(e) => {
                    e.stopPropagation()
                    router.push(`/strategies/${s.id}/studio`)
                  }}
                >
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
