'use client'

import React from "react";
import { SplineScene } from "@/components/ui/splite";
import { Globe, ChevronDown } from "lucide-react";
import { useI18n } from "@/components/i18n/use-i18n";

export function SplineSceneBasic() {
  const { locale, setLocale, t } = useI18n();

  return (
    <div className="w-full h-screen bg-transparent relative overflow-hidden font-sans">
      <div className="absolute top-0 bottom-0 -left-[25%] w-[200%] z-0">
        <SplineScene 
          scene="https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode"
          className="w-full h-full"
        />
      </div>

      <div className="absolute top-8 right-8 z-50">
        <button 
          onClick={() => setLocale(locale === "zh-CN" ? "en" : "zh-CN")}
          className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 backdrop-blur-md border border-white/20 text-white hover:bg-white/20 transition-all text-sm font-medium"
        >
          <Globe className="w-4 h-4" />
          {locale === "zh-CN" ? "EN" : "中文"}
        </button>
      </div>

      <div className="relative z-10 h-full flex items-center pointer-events-none">
        <div className="p-8 md:p-12 lg:p-24 max-w-[1400px] mx-auto w-full">
          <h1 className="text-5xl md:text-6xl lg:text-8xl font-bold bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 to-neutral-400 tracking-tight">
            PnLClaw
          </h1>
          <p className="mt-6 text-lg md:text-xl text-neutral-300 max-w-xl leading-relaxed">
            {t("demo.desc1")}
            <br className="hidden md:block" />
            {t("demo.desc2")}
            <br className="hidden md:block" />
            {t("demo.desc3")}
          </p>
          <div className="mt-10 flex gap-4 pointer-events-auto">
            <button className="px-8 py-3 rounded-full bg-white text-black font-semibold hover:bg-neutral-200 transition-colors">
              {t("demo.start")}
            </button>
            <button 
              onClick={() => window.open('https://github.com/YicunAI/Pnlclaw-community', '_blank')}
              className="px-8 py-3 rounded-full border border-neutral-700 text-white hover:bg-neutral-800 transition-colors"
            >
              {t("demo.docs")}
            </button>
          </div>
        </div>
      </div>

      {/* scroll-down indicator */}
      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2 pointer-events-auto">
        <span className="text-xs tracking-widest text-white/40">
          {t("demo.scrollDown")}
        </span>
        <div className="relative w-5 h-8 rounded-full border border-white/25 flex justify-center">
          <span className="block w-0.5 h-1.5 rounded-full bg-white/50 mt-1.5 animate-scroll-dot" />
        </div>
      </div>
    </div>
  )
}
