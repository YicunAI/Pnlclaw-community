'use client'

import React, { useState } from "react";
import { SplineScene } from "@/components/ui/splite";
import { Globe } from "lucide-react";
 
const translations = {
  zh: {
    title: "PnLClaw",
    desc1: "基于 OpenClaw 开发的加密货币与预测市场量化开源引擎",
    desc2: "对话即量化，对话即交易，重塑您的投资体验",
    desc3: "极致性能，智能决策，安全可靠",
    start: "开始使用",
    docs: "GitHub"
  },
  en: {
    title: "PnLClaw",
    desc1: "Open-source quant engine for Crypto & Prediction Markets based on OpenClaw",
    desc2: "Conversational Quant, Conversational Trading, Redefining Your Investment Experience",
    desc3: "Ultra-performance, smart decision-making, secure and reliable",
    start: "Get Started",
    docs: "GitHub"
  }
};

export function SplineSceneBasic() {
  const [lang, setLang] = useState<'zh' | 'en'>('zh');
  const t = translations[lang];

  return (
    <div className="w-full h-screen bg-transparent relative overflow-hidden font-sans">
      
      {/* 3D Scene - 铺满全屏作为底层 */}
      <div className="absolute top-0 bottom-0 -left-[25%] w-[200%] z-0">
        <SplineScene 
          scene="https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode"
          className="w-full h-full"
        />
      </div>

      {/* Language Switcher - 放在页面右上角 */}
      <div className="absolute top-8 right-8 z-50">
        <button 
          onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
          className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 backdrop-blur-md border border-white/20 text-white hover:bg-white/20 transition-all text-sm font-medium"
        >
          <Globe className="w-4 h-4" />
          {lang === 'zh' ? 'EN' : '中文'}
        </button>
      </div>

      {/* Text content - 浮在 3D 场景上方 */}
      <div className="relative z-10 h-full flex items-center pointer-events-none">
        <div className="p-8 md:p-12 lg:p-24 max-w-[1400px] mx-auto w-full">
          <h1 className="text-5xl md:text-6xl lg:text-8xl font-bold bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 to-neutral-400 tracking-tight">
            {t.title}
          </h1>
          <p className="mt-6 text-lg md:text-xl text-neutral-300 max-w-xl leading-relaxed">
            {t.desc1}
            <br className="hidden md:block" />
            {t.desc2}
            <br className="hidden md:block" />
            {t.desc3}
          </p>
          <div className="mt-10 flex gap-4 pointer-events-auto">
            <button className="px-8 py-3 rounded-full bg-white text-black font-semibold hover:bg-neutral-200 transition-colors">
              {t.start}
            </button>
            <button 
              onClick={() => window.open('https://github.com/openclaw/openclaw', '_blank')}
              className="px-8 py-3 rounded-full border border-neutral-700 text-white hover:bg-neutral-800 transition-colors"
            >
              {t.docs}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
