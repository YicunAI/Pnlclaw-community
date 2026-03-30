"use client"

import { useEffect, useState } from "react"
import { getBalances, type TradingBalance } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"

interface BalanceCardProps {
  wsBalances: TradingBalance[]
}

export function BalanceCard({ wsBalances }: BalanceCardProps) {
  const { t } = useI18n()
  const [balances, setBalances] = useState<TradingBalance[]>([])

  useEffect(() => {
    getBalances().then((res) => {
      if (res.data) setBalances(res.data)
    })
  }, [])

  const display = wsBalances.length > 0 ? wsBalances : balances

  return (
    <div className="space-y-2">
      {display.length === 0 && (
        <p className="text-center text-sm text-muted-foreground py-4">{t("trading.noBalance")}</p>
      )}
      {display.map((b) => (
        <div key={b.asset} className="flex items-center justify-between py-1.5">
          <div>
            <span className="font-mono text-sm font-medium">{b.asset}</span>
            <span className="text-xs text-muted-foreground ml-2">{b.exchange}</span>
          </div>
          <div className="text-right">
            <div className="font-mono text-sm">{b.free.toFixed(2)}</div>
            {b.locked > 0 && (
              <div className="text-xs text-muted-foreground">{t("trading.locked")}: {b.locked.toFixed(2)}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
