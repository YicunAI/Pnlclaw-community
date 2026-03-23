"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Save, ExternalLink } from "lucide-react"

const STORAGE_KEY = "pnlclaw-settings"

interface Settings {
  general: {
    api_url: string
    default_symbol: string
    default_interval: string
  }
  exchange: {
    provider: string
    api_key: string
    api_secret: string
  }
  llm: {
    provider: string
    api_key: string
    base_url: string
    model: string
  }
  risk: {
    max_position_pct: string
    single_risk_pct: string
    daily_loss_limit_pct: string
    cooldown_seconds: string
  }
}

const DEFAULT_SETTINGS: Settings = {
  general: {
    api_url: "http://localhost:8000",
    default_symbol: "BTC/USDT",
    default_interval: "1h",
  },
  exchange: {
    provider: "binance",
    api_key: "",
    api_secret: "",
  },
  llm: {
    provider: "openai",
    api_key: "",
    base_url: "",
    model: "gpt-4o-mini",
  },
  risk: {
    max_position_pct: "10",
    single_risk_pct: "2",
    daily_loss_limit_pct: "5",
    cooldown_seconds: "300",
  },
}

function SettingsField({
  label,
  description,
  type = "text",
  value,
  onChange,
  placeholder,
}: {
  label: string
  description?: string
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
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
    </div>
  )
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored) as Partial<Settings>
        setSettings((prev) => ({
          general: { ...prev.general, ...parsed.general },
          exchange: { ...prev.exchange, ...parsed.exchange },
          llm: { ...prev.llm, ...parsed.llm },
          risk: { ...prev.risk, ...parsed.risk },
        }))
      }
    } catch {
      // ignore parse errors
    }
  }, [])

  const handleSave = () => {
    const toStore: Settings = {
      ...settings,
      exchange: {
        ...settings.exchange,
        api_key: settings.exchange.api_key ? "••••••••" : "",
        api_secret: settings.exchange.api_secret ? "••••••••" : "",
      },
      llm: {
        ...settings.llm,
        api_key: settings.llm.api_key ? "••••••••" : "",
      },
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const update = <S extends keyof Settings>(
    section: S,
    field: keyof Settings[S],
    value: string
  ) => {
    setSettings((prev) => ({
      ...prev,
      [section]: { ...prev[section], [field]: value },
    }))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure your PnLClaw instance
          </p>
        </div>
        <Button onClick={handleSave}>
          <Save className="h-4 w-4 mr-2" />
          {saved ? "Saved!" : "Save Settings"}
        </Button>
      </div>

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="exchange">Exchange</TabsTrigger>
          <TabsTrigger value="llm">LLM</TabsTrigger>
          <TabsTrigger value="risk">Risk Control</TabsTrigger>
          <TabsTrigger value="about">About</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">General Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SettingsField
                label="API Server URL"
                description="Local API server address"
                value={settings.general.api_url}
                onChange={(v) => update("general", "api_url", v)}
                placeholder="http://localhost:8000"
              />
              <SettingsField
                label="Default Symbol"
                description="Default trading pair"
                value={settings.general.default_symbol}
                onChange={(v) => update("general", "default_symbol", v)}
                placeholder="BTC/USDT"
              />
              <SettingsField
                label="Default Interval"
                description="Default kline interval"
                value={settings.general.default_interval}
                onChange={(v) => update("general", "default_interval", v)}
                placeholder="1h"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="exchange">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Exchange Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Exchange</label>
                <select
                  value={settings.exchange.provider}
                  onChange={(e) =>
                    update("exchange", "provider", e.target.value)
                  }
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="binance">Binance</option>
                </select>
                <p className="text-xs text-muted-foreground">
                  v0.1 supports Binance only
                </p>
              </div>
              <SettingsField
                label="API Key"
                description="Optional for public market data"
                type="password"
                value={settings.exchange.api_key}
                onChange={(v) => update("exchange", "api_key", v)}
                placeholder="Enter your API key"
              />
              <SettingsField
                label="API Secret"
                type="password"
                value={settings.exchange.api_secret}
                onChange={(v) => update("exchange", "api_secret", v)}
                placeholder="Enter your API secret"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="llm">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">LLM Provider</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Provider</label>
                <select
                  value={settings.llm.provider}
                  onChange={(e) => update("llm", "provider", e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="openai">OpenAI / Compatible</option>
                  <option value="ollama">Ollama (Local)</option>
                </select>
              </div>
              <SettingsField
                label="API Key"
                type="password"
                value={settings.llm.api_key}
                onChange={(v) => update("llm", "api_key", v)}
                placeholder="sk-..."
              />
              <SettingsField
                label="Base URL"
                description="Custom endpoint for OpenAI-compatible providers (DeepSeek, OpenRouter, etc.)"
                value={settings.llm.base_url}
                onChange={(v) => update("llm", "base_url", v)}
                placeholder="https://api.openai.com/v1"
              />
              <SettingsField
                label="Model"
                value={settings.llm.model}
                onChange={(v) => update("llm", "model", v)}
                placeholder="gpt-4o-mini"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="risk">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Risk Control Parameters</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SettingsField
                label="Max Position Size (%)"
                description="Maximum position as percentage of total equity"
                type="number"
                value={settings.risk.max_position_pct}
                onChange={(v) => update("risk", "max_position_pct", v)}
              />
              <SettingsField
                label="Single Trade Risk (%)"
                description="Maximum risk per trade as percentage of equity"
                type="number"
                value={settings.risk.single_risk_pct}
                onChange={(v) => update("risk", "single_risk_pct", v)}
              />
              <SettingsField
                label="Daily Loss Limit (%)"
                description="Stop trading after this daily loss percentage"
                type="number"
                value={settings.risk.daily_loss_limit_pct}
                onChange={(v) => update("risk", "daily_loss_limit_pct", v)}
              />
              <SettingsField
                label="Cooldown Period (seconds)"
                description="Wait time after hitting loss limit"
                type="number"
                value={settings.risk.cooldown_seconds}
                onChange={(v) => update("risk", "cooldown_seconds", v)}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="about">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">About PnLClaw</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Version</span>
                  <Badge variant="outline">v0.1.0</Badge>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Edition</span>
                  <span className="text-sm">Community</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">License</span>
                  <span className="text-sm">AGPL-3.0</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Runtime</span>
                  <span className="text-sm">Python 3.11+ / Next.js 16 / Tauri 2</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">GitHub</span>
                  <a
                    href="https://github.com/pnlclaw/pnlclaw"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary flex items-center gap-1 hover:underline"
                  >
                    pnlclaw/pnlclaw
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>

              <Separator className="my-4" />

              <div className="text-xs text-muted-foreground space-y-1">
                <p>
                  PnLClaw Community is a local-first crypto quantitative research
                  platform for backtesting, paper trading, and AI-assisted
                  strategy development.
                </p>
                <p>
                  This software is provided under the GNU Affero General Public
                  License v3.0.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
