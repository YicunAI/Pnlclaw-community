"use client"

import { LayoutGrid, List, Search } from "lucide-react"

import { useI18n } from "@/components/i18n/use-i18n"
import { Input } from "@/components/ui/input"

export interface StrategyFiltersProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  filterState: string
  onFilterStateChange: (state: string) => void
  filterDirection: string
  onFilterDirectionChange: (direction: string) => void
  viewMode: "grid" | "table"
  onViewModeChange: (mode: "grid" | "table") => void
}

export function StrategyFilters({
  searchQuery,
  onSearchChange,
  filterState,
  onFilterStateChange,
  filterDirection,
  onFilterDirectionChange,
  viewMode,
  onViewModeChange,
}: StrategyFiltersProps) {
  const { t } = useI18n()

  return (
    <div className="flex items-center gap-3">
      <div className="relative max-w-sm flex-1">
        <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2" />
        <Input
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={t("strategies.hub.search")}
          className="h-8 pl-8 text-xs"
        />
      </div>
      <select
        value={filterState}
        onChange={(e) => onFilterStateChange(e.target.value)}
        className="border-border bg-background h-8 rounded-md border px-2 text-xs"
      >
        <option value="all">{t("strategies.hub.filterAll")}</option>
        <option value="draft">Draft</option>
        <option value="validated">Validated</option>
        <option value="confirmed">Confirmed</option>
        <option value="paper_running">Paper Running</option>
      </select>
      <select
        value={filterDirection}
        onChange={(e) => onFilterDirectionChange(e.target.value)}
        className="border-border bg-background h-8 rounded-md border px-2 text-xs"
      >
        <option value="all">{t("strategies.hub.filterAll")}</option>
        <option value="long_only">Long Only</option>
        <option value="short_only">Short Only</option>
        <option value="neutral">Neutral</option>
      </select>
      <div className="border-border flex items-center overflow-hidden rounded-md border">
        <button
          type="button"
          onClick={() => onViewModeChange("grid")}
          className={`p-1.5 transition-colors ${viewMode === "grid" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted"}`}
          aria-label={t("strategies.hub.viewCards")}
        >
          <LayoutGrid className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => onViewModeChange("table")}
          className={`p-1.5 transition-colors ${viewMode === "table" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted"}`}
          aria-label={t("strategies.hub.viewTable")}
        >
          <List className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
