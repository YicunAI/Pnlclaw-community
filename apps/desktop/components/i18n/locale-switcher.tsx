"use client"

import { useI18n } from "./use-i18n"
import { Globe } from "lucide-react"

export function LocaleSwitcher() {
  const { locale, setLocale, t } = useI18n()

  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{t("settings.language")}</label>
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as "en" | "zh-CN")}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
      >
        <option value="en">{t("common.english")}</option>
        <option value="zh-CN">{t("common.chinese")}</option>
      </select>
    </div>
  )
}

export function LocaleSwitcherCompact() {
  const { locale, setLocale } = useI18n()

  const toggle = () => {
    setLocale(locale === "en" ? "zh-CN" : "en")
  }

  return (
    <button
      onClick={toggle}
      className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted hover:border-primary/40"
      title={locale === "en" ? "切换到中文" : "Switch to English"}
    >
      <Globe className="h-3.5 w-3.5 text-primary" />
      <span>{locale === "en" ? "EN" : "中文"}</span>
    </button>
  )
}
