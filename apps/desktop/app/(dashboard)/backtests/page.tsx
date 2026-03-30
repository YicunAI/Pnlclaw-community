"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

export default function BacktestsRedirectPage() {
  const router = useRouter()
  useEffect(() => {
    router.replace("/strategies?tab=backtests")
  }, [router])
  return null
}
