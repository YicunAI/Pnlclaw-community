"use client"

import React, { useState, useEffect, useCallback } from "react"
import { updateSettings, getLLMModels, type AppSettings, type LLMModel } from "@/lib/api-client"
import { useAppSettings } from "@/lib/hooks/use-api"
import { mutate } from "swr"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Save, ExternalLink, ShieldCheck, ShieldAlert, Globe, RefreshCw, Sparkles } from "lucide-react"
import { useI18n } from "@/components/i18n/use-i18n"
import { LocaleSwitcher } from "@/components/i18n/locale-switcher"

type Settings = AppSettings

const DEFAULT_SETTINGS: Settings = {
  general: {
    api_url: "http://localhost:8080",
    default_symbol: "BTC/USDT",
    default_interval: "1h",
  },
  exchange: {
    provider: "binance",
    market_type: "spot",
    api_key: "",
    api_secret: "",
    api_key_configured: false,
    api_secret_configured: false,
    api_key_masked: "",
    api_secret_masked: "",
  },
  llm: {
    provider: "openai",
    api_key: "",
    base_url: "",
    model: "",
    api_key_configured: false,
    api_key_masked: "",
    smart_mode: false,
    smart_models: {
      strategy: "",
      analysis: "",
      quick: "",
    },
  },
  risk: {
    max_position_pct: "10",
    single_risk_pct: "2",
    daily_loss_limit_pct: "5",
    cooldown_seconds: "300",
  },
  network: {
    proxy_url: "",
  },
}

function SettingsField({
  label,
  description,
  type = "text",
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string
  description?: string
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  hint?: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {description && (
        <p className="text-xs text-muted-foreground">{description}</p>
      )}
      <Input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {hint}
    </div>
  )
}

function normalizeBaseUrl(url: string): string {
  let u = url.trim().replace(/\/+$/, "")
  if (!u) return ""
  for (const suffix of ["/chat/completions", "/completions", "/models", "/embeddings"]) {
    if (u.endsWith(suffix)) {
      u = u.slice(0, -suffix.length).replace(/\/+$/, "")
      break
    }
  }
  if (u.endsWith("/v1") || u.includes("/v1/")) return u
  if (u.includes("/v1beta")) return u
  return `${u}/v1`
}

export default function SettingsPage() {
  const { t } = useI18n()
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<LLMModel[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [smartMode, setSmartMode] = useState(false)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    if (settings.llm.smart_mode !== undefined) {
      setSmartMode(settings.llm.smart_mode)
    }
  }, [settings.llm.smart_mode])

  const { data: cachedSettings, error: settingsError } = useAppSettings()
  useEffect(() => {
    if (hydrated) return
    if (settingsError) {
      setError(t("settings.loadError"))
      return
    }
    if (!cachedSettings) return
    setSettings({
      ...cachedSettings,
      exchange: {
        ...cachedSettings.exchange,
        api_key: "",
        api_secret: "",
        clear_api_key: false,
        clear_api_secret: false,
      },
      llm: {
        ...cachedSettings.llm,
        api_key: "",
        clear_api_key: false,
      },
    })
    setHydrated(true)
  }, [cachedSettings, settingsError, t, hydrated])

  const handleSave = async () => {
    setSaving(true)
    setError(null)

    const payload: Partial<Settings> = {
      general: settings.general,
      risk: settings.risk,
      network: settings.network,
      exchange: {
        provider: settings.exchange.provider,
        market_type: settings.exchange.market_type,
        api_key: settings.exchange.api_key,
        api_secret: settings.exchange.api_secret,
        clear_api_key: Boolean(settings.exchange.clear_api_key),
        clear_api_secret: Boolean(settings.exchange.clear_api_secret),
      },
      llm: {
        provider: settings.llm.provider,
        api_key: settings.llm.api_key,
        clear_api_key: Boolean(settings.llm.clear_api_key),
        base_url: settings.llm.base_url,
        model: settings.llm.model,
        smart_mode: smartMode,
        ...(settings.llm.smart_models &&
          typeof settings.llm.smart_models === "object" && {
            smart_models: settings.llm.smart_models,
          }),
      },
    }

    const res = await updateSettings(payload)
    setSaving(false)

    if (res.error || !res.data) {
      setError(res.error ?? t("settings.saveError"))
      return
    }

    const updatedSettings = {
      ...res.data,
      exchange: {
        ...res.data.exchange,
        api_key: "",
        api_secret: "",
        clear_api_key: false,
        clear_api_secret: false,
      },
      llm: {
        ...res.data.llm,
        api_key: "",
        clear_api_key: false,
      },
    }
    setSettings(updatedSettings)
    mutate("api:settings", res.data, false)

    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const update = <S extends keyof Settings, K extends keyof Settings[S]>(
    section: S,
    field: K,
    value: Settings[S][K]
  ) => {
    setSettings((prev) => ({
      ...prev,
      [section]: { ...prev[section], [field]: value },
    }))
  }

  const autoSaveModel = useCallback(async (model: string, smartModels?: Record<string, string>) => {
    const payload: Partial<Settings> = {
      llm: {
        provider: settings.llm.provider,
        base_url: settings.llm.base_url,
        model,
        smart_mode: smartMode,
        ...(smartModels && { smart_models: smartModels }),
      },
    }
    const res = await updateSettings(payload)
    if (res.data) {
      setSettings(prev => ({
        ...prev,
        llm: {
          ...prev.llm,
          ...res.data!.llm,
          api_key: "",
          clear_api_key: false,
        },
      }))
      mutate("api:settings", res.data, false)
    }
  }, [settings.llm.provider, settings.llm.base_url, smartMode])

  const handleModelSelect = (model: string) => {
    update("llm", "model", model)
    autoSaveModel(model)
  }

  const handleSmartModelChange = (role: string, model: string) => {
    const updated = { ...settings.llm.smart_models, [role]: model }
    update("llm", "smart_models", updated)
    autoSaveModel(settings.llm.model, updated)
  }

  const handleFetchModels = async () => {
    setLoadingModels(true)
    setError(null)
    const res = await getLLMModels()
    setLoadingModels(false)

    if (res.error || !res.data) {
      setError(res.error ?? "Failed to fetch models")
      return
    }

    setModels(res.data.models)

    if (res.data.models.length > 0) {
      const modelIds = res.data.models.map(m => m.id)
      let needAutoSave = false

      // If no model is selected yet, pick the first one and auto-save
      if (!settings.llm.model) {
        const first = modelIds[0]
        update("llm", "model", first)
        needAutoSave = true
        // will be saved below
      }

      // Auto-populate smart_models if any role is empty
      const prev = settings.llm.smart_models || {}
      const strategyModel = prev.strategy || modelIds.find(id =>
        id.includes('opus') || id.includes('gpt-4') || id.includes('claude-3')
      ) || modelIds[0]
      const analysisModel = prev.analysis || modelIds.find(id =>
        id.includes('sonnet') || id.includes('4o-mini') || id.includes('3.5')
      ) || modelIds[0]
      const quickModel = prev.quick || modelIds.find(id =>
        id.includes('haiku') || id.includes('4o-mini') || id.includes('3.5')
      ) || modelIds[0]

      const updatedSmartModels = { strategy: strategyModel, analysis: analysisModel, quick: quickModel }
      const smartChanged = prev.strategy !== strategyModel || prev.analysis !== analysisModel || prev.quick !== quickModel

      setSettings(prev => ({
        ...prev,
        llm: {
          ...prev.llm,
          model: prev.llm.model || modelIds[0],
          smart_models: updatedSmartModels,
        },
      }))

      if (needAutoSave || smartChanged) {
        autoSaveModel(settings.llm.model || modelIds[0], updatedSmartModels)
      }
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("settings.title")}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t("settings.subtitle")}
          </p>
        </div>
        <Button onClick={handleSave} disabled={saving}>
          <Save className="h-4 w-4 mr-2" />
          {saving ? t("settings.saving") : saved ? t("settings.saved") : t("settings.save")}
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">{t("settings.general")}</TabsTrigger>
          <TabsTrigger value="exchange">{t("settings.exchange")}</TabsTrigger>
          <TabsTrigger value="llm">{t("settings.llm")}</TabsTrigger>
          <TabsTrigger value="risk">{t("settings.risk")}</TabsTrigger>
          <TabsTrigger value="network">{t("settings.network")}</TabsTrigger>
          <TabsTrigger value="about">{t("settings.about")}</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings.generalSettings")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SettingsField
                label={t("settings.apiServerUrl")}
                description={t("settings.localApiAddress")}
                value={settings.general.api_url}
                onChange={(v) => update("general", "api_url", v)}
                placeholder="http://localhost:8080"
              />
              <SettingsField
                label={t("settings.defaultSymbol")}
                description={t("settings.defaultPair")}
                value={settings.general.default_symbol}
                onChange={(v) => update("general", "default_symbol", v)}
                placeholder="BTC/USDT"
              />
              <SettingsField
                label={t("settings.defaultInterval")}
                description={t("settings.defaultKline")}
                value={settings.general.default_interval}
                onChange={(v) => update("general", "default_interval", v)}
                placeholder="1h"
              />
              <Separator className="my-2" />
              <LocaleSwitcher />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="exchange">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings.exchangeConfig")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t("settings.exchange.label")}</label>
                <select
                  value={settings.exchange.provider}
                  onChange={(e) =>
                    update("exchange", "provider", e.target.value as Settings["exchange"]["provider"])
                  }
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="binance">Binance</option>
                  <option value="okx">OKX</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t("settings.marketType")}</label>
                <select
                  value={settings.exchange.market_type}
                  onChange={(e) => update("exchange", "market_type", e.target.value as Settings["exchange"]["market_type"])}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="spot">{t("markets.spot")}</option>
                  <option value="futures">{t("markets.futures")}</option>
                </select>
              </div>
              <SettingsField
                label={t("settings.apiKey")}
                description={
                  settings.exchange.api_key_configured
                    ? t("settings.configuredHint", {
                        masked:
                          settings.exchange.api_key_masked || "••••••••",
                      })
                    : t("settings.optionalPublic")
                }
                type="password"
                value={settings.exchange.api_key}
                onChange={(v) => update("exchange", "api_key", v)}
                placeholder={t("settings.enterApiKey")}
              />
              <SettingsField
                label={t("settings.apiSecret")}
                description={
                  settings.exchange.api_secret_configured
                    ? t("settings.configuredHint", {
                        masked:
                          settings.exchange.api_secret_masked || "••••••••",
                      })
                    : t("settings.optionalPublic")
                }
                type="password"
                value={settings.exchange.api_secret}
                onChange={(v) => update("exchange", "api_secret", v)}
                placeholder={t("settings.enterApiSecret")}
              />
              <div className="flex items-center justify-between rounded-md border border-input px-3 py-2">
                <span className="text-sm">{t("settings.clearApiKey")}</span>
                <input
                  type="checkbox"
                  checked={Boolean(settings.exchange.clear_api_key)}
                  onChange={(e) => update("exchange", "clear_api_key", e.target.checked)}
                />
              </div>
              <div className="flex items-center justify-between rounded-md border border-input px-3 py-2">
                <span className="text-sm">{t("settings.clearApiSecret")}</span>
                <input
                  type="checkbox"
                  checked={Boolean(settings.exchange.clear_api_secret)}
                  onChange={(e) => update("exchange", "clear_api_secret", e.target.checked)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="llm">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings.llmProvider")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">{t("settings.provider")}</label>
                <select
                  value={settings.llm.provider}
                  onChange={(e) => update("llm", "provider", e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="openai">{t("settings.openaiCompatible")}</option>
                  <option value="ollama">{t("settings.ollamaLocal")}</option>
                </select>
              </div>
              <SettingsField
                label={t("settings.apiKey")}
                description={
                  settings.llm.api_key_configured
                    ? t("settings.configuredHint", {
                        masked: settings.llm.api_key_masked || "••••••••",
                      })
                    : undefined
                }
                type="password"
                value={settings.llm.api_key}
                onChange={(v) => update("llm", "api_key", v)}
                placeholder={t("settings.llmApiKeyPlaceholder")}
              />
              <SettingsField
                label={t("settings.baseUrl")}
                description={t("settings.customEndpoint")}
                value={settings.llm.base_url}
                onChange={(v) => update("llm", "base_url", v)}
                placeholder="https://api.openai.com/v1"
                hint={
                  settings.llm.base_url ? (
                    <p className="text-xs text-muted-foreground">
                      {t("settings.preview")}:{" "}
                      <span className="font-mono text-[11px]">
                        {normalizeBaseUrl(settings.llm.base_url)}/chat/completions
                      </span>
                    </p>
                  ) : null
                }
              />

              <Separator className="my-4" />

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">{t("settings.modelConfiguration")}</label>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleFetchModels}
                    disabled={loadingModels || !settings.llm.api_key_configured}
                  >
                    <RefreshCw className={`h-4 w-4 mr-2 ${loadingModels ? "animate-spin" : ""}`} />
                    {t("settings.fetchModels")}
                  </Button>
                </div>

                {models.length > 0 && (
                  <div className="rounded-md border border-input p-3 space-y-2">
                    <p className="text-xs text-muted-foreground">
                      {t("settings.availableModels")}: {models.length}
                    </p>
                    <div className="max-h-40 overflow-y-auto space-y-1">
                      {models.map((model) => {
                        const isSelected = model.id === settings.llm.model
                        return (
                          <button
                            key={model.id}
                            type="button"
                            onClick={() => handleModelSelect(model.id)}
                            className={`w-full text-left text-xs font-mono px-2 py-1.5 rounded flex items-center justify-between transition-colors cursor-pointer ${
                              isSelected
                                ? "bg-primary/15 text-primary border border-primary/30"
                                : "bg-muted/50 hover:bg-muted text-foreground"
                            }`}
                          >
                            <span>{model.id}</span>
                            {isSelected && (
                              <Badge variant="default" className="text-[10px] h-4">{t("settings.current") || "Current"}</Badge>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">{t("settings.modelSelection")}</label>
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-3 w-3 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">{t("settings.smartMode")}</span>
                      <input
                        type="checkbox"
                        checked={smartMode}
                        onChange={(e) => setSmartMode(e.target.checked)}
                        className="rounded"
                      />
                    </div>
                  </div>

                  {smartMode ? (
                    <div className="rounded-md border border-input bg-muted/30 p-3 space-y-3">
                      <p className="text-xs text-muted-foreground">
                        {t("settings.smartModeDesc")}
                      </p>

                      <div className="space-y-2">
                        {([
                          { role: "strategy", label: t("settings.strategyDrafting") },
                          { role: "analysis", label: t("settings.marketAnalysis") },
                          { role: "quick", label: t("settings.quickQueries") },
                        ] as const).map(({ role, label }) => (
                          <div key={role} className="flex items-center justify-between">
                            <span className="text-xs font-medium">{label}</span>
                            {models.length > 0 ? (
                              <select
                                value={settings.llm.smart_models?.[role] || ""}
                                onChange={(e) => handleSmartModelChange(role, e.target.value)}
                                className="text-xs h-7 rounded-md border border-input bg-background px-2"
                              >
                                <option value="" disabled>{t("settings.selectModel") || "Select model..."}</option>
                                {models.map((m) => (
                                  <option key={m.id} value={m.id}>{m.id}</option>
                                ))}
                              </select>
                            ) : (
                              <Input
                                value={settings.llm.smart_models?.[role] || ""}
                                onChange={(e) => handleSmartModelChange(role, e.target.value)}
                                className="text-xs h-7 w-40"
                                placeholder={t("settings.selectModel") || "Select model..."}
                              />
                            )}
                          </div>
                        ))}
                      </div>

                      <p className="text-xs font-medium text-primary mt-2">
                        {t("settings.autoSelectEnabled")}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {models.length > 0 ? (
                        <select
                          value={settings.llm.model}
                          onChange={(e) => handleModelSelect(e.target.value)}
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        >
                          <option value="" disabled>{t("settings.selectModel") || "Select model..."}</option>
                          {models.map((m) => (
                            <option key={m.id} value={m.id}>{m.id}</option>
                          ))}
                        </select>
                      ) : (
                        <Input
                          value={settings.llm.model}
                          onChange={(e) => update("llm", "model", e.target.value)}
                          placeholder={t("settings.selectModel") || "Select model..."}
                        />
                      )}
                      <p className="text-xs text-muted-foreground">
                        {settings.llm.model
                          ? <>{t("settings.currentModel")}: <span className="font-mono">{settings.llm.model}</span></>
                          : t("settings.noModelSelected") || "请先获取模型列表并选择模型"
                        }
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <Separator className="my-4" />

              <div className="flex items-center justify-between rounded-md border border-input px-3 py-2">
                <span className="text-sm">{t("settings.clearLlmKey")}</span>
                <input
                  type="checkbox"
                  checked={Boolean(settings.llm.clear_api_key)}
                  onChange={(e) => update("llm", "clear_api_key", e.target.checked)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="risk">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings.riskParams")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SettingsField
                label={t("settings.maxPosition")}
                description={t("settings.maxPositionDesc")}
                type="number"
                value={settings.risk.max_position_pct}
                onChange={(v) => update("risk", "max_position_pct", v)}
              />
              <SettingsField
                label={t("settings.singleRisk")}
                description={t("settings.singleRiskDesc")}
                type="number"
                value={settings.risk.single_risk_pct}
                onChange={(v) => update("risk", "single_risk_pct", v)}
              />
              <SettingsField
                label={t("settings.dailyLoss")}
                description={t("settings.dailyLossDesc")}
                type="number"
                value={settings.risk.daily_loss_limit_pct}
                onChange={(v) => update("risk", "daily_loss_limit_pct", v)}
              />
              <SettingsField
                label={t("settings.cooldown")}
                description={t("settings.cooldownDesc")}
                type="number"
                value={settings.risk.cooldown_seconds}
                onChange={(v) => update("risk", "cooldown_seconds", v)}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="network">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Globe className="h-4 w-4" />
                {t("settings.networkTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SettingsField
                label={t("settings.proxyUrl")}
                description={t("settings.proxyUrlDesc")}
                value={settings.network.proxy_url}
                onChange={(v) => update("network", "proxy_url", v)}
                placeholder="socks5h://127.0.0.1:1081"
              />
              <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground space-y-1.5">
                <p>{t("settings.proxyNote")}</p>
                <p className="font-mono text-[11px] space-y-0.5">
                  socks5h://127.0.0.1:1081 (V2Ray)<br />
                  socks5h://127.0.0.1:7890 (Clash)<br />
                  http://127.0.0.1:7890
                </p>
                <p>{t("settings.proxyRestart")}</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="about">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("settings.aboutTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.version")}</span>
                  <Badge variant="outline">v0.1.0</Badge>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.edition")}</span>
                  <span className="text-sm">{t("settings.community")}</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.license")}</span>
                  <span className="text-sm">AGPL-3.0</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.runtime")}</span>
                  <span className="text-sm">Python 3.11+ / Next.js 16 / Tauri 2</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.github")}</span>
                  <a
                    href="https://github.com/YicunAI/Pnlclaw-community"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary flex items-center gap-1 hover:underline"
                  >
                    YicunAI/Pnlclaw-community
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>

              <Separator className="my-4" />

              <div className="space-y-3">
                <div className="flex items-center gap-2 mb-2">
                  {settings.security?.keyring_available ? (
                    <ShieldCheck className="h-4 w-4 text-green-500" />
                  ) : (
                    <ShieldAlert className="h-4 w-4 text-yellow-500" />
                  )}
                  <span className="text-sm font-medium">{t("settings.securityStatus")}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.secretBackend")}</span>
                  <span className="text-sm">{settings.security?.secret_backend ?? "keyring"}</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.keyringAvailable")}</span>
                  <Badge variant={settings.security?.keyring_available ? "default" : "destructive"}>
                    {settings.security?.keyring_available ? t("settings.keyringYes") : t("settings.keyringNo")}
                  </Badge>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{t("settings.transportEncryption")}</span>
                  <span className="text-sm">{t("settings.transportEncrypted")}</span>
                </div>
              </div>

              <Separator className="my-4" />

              <div className="text-xs text-muted-foreground space-y-1">
                <p>{t("settings.securityNote")}</p>
                <p>{t("settings.aboutP1")}</p>
                <p>{t("settings.aboutP2")}</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
