"use client"

import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react"
import type { ExchangeProvider, MarketType } from "@/lib/api-client"
import { useTradingWS } from "@/lib/use-trading-ws"
import { useMarketWS } from "@/lib/use-market-ws"

type MarketSubscription = {
  symbol: string
  exchange: ExchangeProvider
  marketType: MarketType
  interval: string
}

type TradingWSValue = ReturnType<typeof useTradingWS>
type MarketWSValue = ReturnType<typeof useMarketWS>

const TradingWSContext = createContext<TradingWSValue | null>(null)
const MarketWSContext = createContext<MarketWSValue | null>(null)
const MarketSubscriptionContext = createContext<{
  marketSubscription: MarketSubscription
  setMarketSubscription: (next: Partial<MarketSubscription>) => void
} | null>(null)

function TradingWSProvider({ children }: { children: React.ReactNode }) {
  const trading = useTradingWS()
  return (
    <TradingWSContext.Provider value={trading}>
      {children}
    </TradingWSContext.Provider>
  )
}

function MarketWSProvider({
  subscription,
  children,
}: {
  subscription: MarketSubscription
  children: React.ReactNode
}) {
  const market = useMarketWS(subscription)
  return (
    <MarketWSContext.Provider value={market}>
      {children}
    </MarketWSContext.Provider>
  )
}

export function DashboardRealtimeProvider({ children }: { children: React.ReactNode }) {
  const [marketSubscription, setMarketSubscriptionState] = useState<MarketSubscription>({
    symbol: "BTC/USDT",
    exchange: "binance",
    marketType: "futures",
    interval: "1h",
  })

  const setMarketSubscription = useCallback((next: Partial<MarketSubscription>) => {
    setMarketSubscriptionState((prev) => ({ ...prev, ...next }))
  }, [])

  const subValue = useMemo(
    () => ({ marketSubscription, setMarketSubscription }),
    [marketSubscription, setMarketSubscription],
  )

  return (
    <MarketSubscriptionContext.Provider value={subValue}>
      <TradingWSProvider>
        <MarketWSProvider subscription={marketSubscription}>
          {children}
        </MarketWSProvider>
      </TradingWSProvider>
    </MarketSubscriptionContext.Provider>
  )
}

export function useDashboardRealtime() {
  const trading = useContext(TradingWSContext)
  const market = useContext(MarketWSContext)
  const sub = useContext(MarketSubscriptionContext)
  if (!trading || !market || !sub) {
    throw new Error("useDashboardRealtime must be used inside DashboardRealtimeProvider")
  }
  return {
    trading,
    market,
    marketSubscription: sub.marketSubscription,
    setMarketSubscription: sub.setMarketSubscription,
  }
}

export function useTradingWSContext() {
  const value = useContext(TradingWSContext)
  if (!value) throw new Error("useTradingWSContext must be used inside DashboardRealtimeProvider")
  return value
}

export function useMarketWSContext() {
  const value = useContext(MarketWSContext)
  if (!value) throw new Error("useMarketWSContext must be used inside DashboardRealtimeProvider")
  return value
}

export function useMarketSubscription() {
  const value = useContext(MarketSubscriptionContext)
  if (!value) throw new Error("useMarketSubscription must be used inside DashboardRealtimeProvider")
  return value
}
