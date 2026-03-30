import useSWR, { type SWRConfiguration } from "swr"
import {
  checkHealth,
  getBacktests,
  getPaperAccounts,
  getTradingMode,
  getBalances,
  getPositions,
  getSettings,
  getStrategies,
  type BacktestData,
  type PaperAccountData,
  type TradingBalance,
  type TradingPosition,
  type AppSettings,
  type StrategyData,
} from "../api-client"

const defaultConfig: SWRConfiguration = {
  revalidateOnFocus: false,
  dedupingInterval: 5000,
  errorRetryCount: 2,
}

const slowConfig: SWRConfiguration = {
  ...defaultConfig,
  dedupingInterval: 30_000,
  revalidateOnFocus: false,
}

export function useHealth() {
  return useSWR<{ status: string } | null>(
    "api:health",
    async () => {
      const r = await checkHealth()
      return r.data ?? null
    },
    { ...defaultConfig, refreshInterval: 30_000 },
  )
}

export function useBacktestList(strategyId?: string) {
  return useSWR<BacktestData[]>(
    ["api:backtests", strategyId ?? null],
    async () => {
      const r = await getBacktests(strategyId)
      return Array.isArray(r.data) ? r.data : []
    },
    defaultConfig,
  )
}

export function usePaperAccounts() {
  return useSWR<PaperAccountData[]>(
    "api:paper-accounts",
    async () => {
      const r = await getPaperAccounts()
      return Array.isArray(r.data) ? r.data : []
    },
    defaultConfig,
  )
}

export function useTradingModeData() {
  return useSWR<{ mode: string } | null>(
    "api:trading-mode",
    async () => {
      const r = await getTradingMode()
      return r.data ?? null
    },
    defaultConfig,
  )
}

export function useLiveBalances(enabled: boolean) {
  return useSWR<TradingBalance[]>(
    enabled ? "api:live-balances" : null,
    async () => {
      const r = await getBalances()
      return Array.isArray(r.data) ? r.data : []
    },
    defaultConfig,
  )
}

export function useLivePositions(enabled: boolean) {
  return useSWR<TradingPosition[]>(
    enabled ? "api:live-positions" : null,
    async () => {
      const r = await getPositions()
      return Array.isArray(r.data) ? r.data : []
    },
    defaultConfig,
  )
}

export function useAppSettings() {
  return useSWR<AppSettings | null>(
    "api:settings",
    async () => {
      const r = await getSettings()
      return r.data ?? null
    },
    slowConfig,
  )
}

export function useStrategyList(tags?: string) {
  return useSWR<StrategyData[]>(
    ["api:strategies", tags ?? null],
    async () => {
      const r = await getStrategies(tags)
      return Array.isArray(r.data) ? r.data : []
    },
    defaultConfig,
  )
}
