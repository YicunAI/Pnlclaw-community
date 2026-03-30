"use client"

import React, { useEffect, useRef, useState, useMemo, useCallback } from "react"
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries, HistogramSeries, CrosshairMode, createSeriesMarkers } from "lightweight-charts"
import type { KlineData } from "@/lib/api-client"
import { cn } from "@/lib/utils"

export interface TradeMarker {
  time: number
  position: "aboveBar" | "belowBar"
  color: string
  shape: "arrowUp" | "arrowDown" | "circle" | "square"
  text?: string
}

interface HoverData {
  time: string | number
  open: number
  high: number
  low: number
  close: number
}

export default function CandlestickChart({
  data,
  interval,
  onLoadMore,
  isLoadingMore,
  markers,
}: {
  data: KlineData[]
  interval: string
  onLoadMore?: (oldestTimestamp: number) => void
  isLoadingMore?: boolean
  markers?: TradeMarker[]
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null)
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null)
  const markersApiRef = useRef<any>(null)
  const loadingMoreRef = useRef(false)
  const dataLenRef = useRef(0)
  const prevDataLenRef = useRef(0)

  const [hoverData, setHoverData] = useState<HoverData | null>(null)

  const lastCandle = useMemo(() => {
    if (data.length === 0) return null
    return data[data.length - 1]
  }, [data])

  const displayData = hoverData || (lastCandle ? {
    time: lastCandle.timestamp,
    open: lastCandle.open,
    high: lastCandle.high,
    low: lastCandle.low,
    close: lastCandle.close
  } : null)

  useEffect(() => {
    loadingMoreRef.current = !!isLoadingMore
  }, [isLoadingMore])

  useEffect(() => {
    dataLenRef.current = data.length
  }, [data.length])

  const onLoadMoreRef = useRef(onLoadMore)
  useEffect(() => {
    onLoadMoreRef.current = onLoadMore
  }, [onLoadMore])

  useEffect(() => {
    if (!chartContainerRef.current) return

    const handleResize = () => {
      if (chartRef.current && chartContainerRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        })
      }
    }

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.5)",
        fontFamily: "Inter, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(255, 255, 255, 0.4)",
          style: 2,
          labelBackgroundColor: "#1e222d",
        },
        horzLine: {
          color: "rgba(255, 255, 255, 0.4)",
          style: 2,
          labelBackgroundColor: "#1e222d",
        },
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        autoScale: true,
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
    })
    chartRef.current = chart

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    })
    seriesRef.current = candlestickSeries as any

    markersApiRef.current = createSeriesMarkers(candlestickSeries, [])

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    })
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    volumeRef.current = volumeSeries

    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time || param.point === undefined || !seriesRef.current) {
        setHoverData(null)
        return
      }
      const candle = param.seriesData.get(seriesRef.current) as any
      if (candle) {
        setHoverData({
          time: param.time as any,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
        })
      } else {
        setHoverData(null)
      }
    })

    chart.timeScale().subscribeVisibleLogicalRangeChange((logicalRange) => {
      if (!logicalRange) return
      if (logicalRange.from < 5 && !loadingMoreRef.current && onLoadMoreRef.current && dataLenRef.current > 0) {
        loadingMoreRef.current = true
        onLoadMoreRef.current(-1)
      }
    })

    const ro = new ResizeObserver(handleResize)
    ro.observe(chartContainerRef.current)
    window.addEventListener("resize", handleResize)
    return () => {
      ro.disconnect()
      window.removeEventListener("resize", handleResize)
      markersApiRef.current = null
      chart.remove()
    }
  }, [])

  useEffect(() => {
    if (!seriesRef.current || !volumeRef.current || !chartRef.current) return

    const candleData = data.map((d) => ({
      time: Math.floor(d.timestamp / 1000) as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))

    const volData = data.map((d) => ({
      time: Math.floor(d.timestamp / 1000) as any,
      value: d.volume,
      color: d.close >= d.open ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)",
    }))

    seriesRef.current.setData(candleData)
    volumeRef.current.setData(volData)

    const oldLen = prevDataLenRef.current
    const newLen = data.length
    prevDataLenRef.current = newLen

    if (oldLen < 30 && newLen >= 30) {
      const barsToShow = Math.min(newLen, 120)
      chartRef.current.timeScale().setVisibleLogicalRange({
        from: newLen - barsToShow,
        to: newLen + 10,
      })
    }
  }, [data])

  useEffect(() => {
    if (!markersApiRef.current) return
    if (!markers || markers.length === 0) {
      markersApiRef.current.setMarkers([])
      return
    }
    const sorted = [...markers]
      .sort((a, b) => a.time - b.time)
      .map((m) => ({
        time: m.time as any,
        position: m.position,
        color: m.color,
        shape: m.shape,
        text: m.text,
        size: 1.5,
      }))
    markersApiRef.current.setMarkers(sorted)
  }, [markers])

  const change = displayData ? displayData.close - displayData.open : 0
  const changePct = displayData ? (change / displayData.open) * 100 : 0

  return (
    <div className="relative w-full h-full flex flex-col overflow-hidden">
      <div className="absolute top-2 left-2 z-10 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono pointer-events-none bg-background/40 backdrop-blur-sm px-2 py-1 rounded">
        {displayData ? (
          <>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">O</span>
              <span className={cn(change >= 0 ? "text-[#10b981]" : "text-[#ef4444]")}>{displayData.open.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">H</span>
              <span className={cn(change >= 0 ? "text-[#10b981]" : "text-[#ef4444]")}>{displayData.high.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">L</span>
              <span className={cn(change >= 0 ? "text-[#10b981]" : "text-[#ef4444]")}>{displayData.low.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">C</span>
              <span className={cn(change >= 0 ? "text-[#10b981]" : "text-[#ef4444]")}>{displayData.close.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1 ml-2">
              <span className={cn("font-bold px-1 rounded", change >= 0 ? "bg-[#10b981]/10 text-[#10b981]" : "bg-[#ef4444]/10 text-[#ef4444]")}>
                {change >= 0 ? "+" : ""}{change.toFixed(2)} ({changePct.toFixed(2)}%)
              </span>
            </div>
          </>
        ) : (
          <span className="text-muted-foreground">载入行情中...</span>
        )}
      </div>

      <div ref={chartContainerRef} className="flex-1 w-full z-[2]" />
      
      <div
        className="absolute inset-0 flex items-center justify-center pointer-events-none z-[1] select-none"
        style={{ opacity: 0.1 }}
      >
        <img
          src="/logo.svg"
          alt="PnLClaw Logo"
          className="w-[60%] max-w-2xl h-auto invert"
          draggable={false}
        />
      </div>
      
      {isLoadingMore && (
        <div className="absolute top-10 left-2 bg-background/80 text-[10px] text-muted-foreground px-1.5 py-0.5 rounded border border-white/10 z-10">
          加载历史数据...
        </div>
      )}
    </div>
  )
}
