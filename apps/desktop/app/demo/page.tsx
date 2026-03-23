"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion, useScroll, useTransform, AnimatePresence } from "framer-motion";
import { Terminal, Shield, Zap, Lock, Server, Activity, Code, Database, Globe, Cpu } from "lucide-react";

const GlowingBadge = ({ text, colorClass }: { text: string; colorClass: string }) => (
  <div className={`px-3 py-1 rounded-full border bg-black/50 backdrop-blur-md text-xs font-mono flex items-center gap-1.5 ${colorClass}`}>
    <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${colorClass.split(' ')[0].replace('text-', 'bg-')}`} />
    {text}
  </div>
);

export default function DemoLanding() {
  const { scrollY } = useScroll();
  const heroY = useTransform(scrollY, [0, 500], [0, -100]);
  const heroOpacity = useTransform(scrollY, [0, 400], [1, 0]);

  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const [typedText, setTypedText] = useState("");
  const fullText = "帮我生成一个基于 ETH 15分钟线的均线回归策略，加入 RSI 过滤，并开启 1 毫秒的回测。";
  
  const [chartData, setChartData] = useState<number[]>([100, 105, 102, 108, 104, 110, 115, 112, 120, 118, 125, 130]);
  const [orderbook, setOrderbook] = useState<{bids: number[], asks: number[]}>({bids: [3400.1, 3399.8, 3398.5], asks: [3401.2, 3402.5, 3403.0]});

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setMousePosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  useEffect(() => {
    let i = 0;
    let isTyping = true;
    
    // Typing effect with realistic pauses
    const typeNext = () => {
      if (!isTyping || i >= fullText.length) return;
      
      setTypedText(fullText.slice(0, i + 1));
      i++;
      
      let delay = 30 + Math.random() * 40;
      if (['，', '。'].includes(fullText[i-1])) delay += 300; // Pause at punctuation
      
      setTimeout(typeNext, delay);
    };
    
    setTimeout(typeNext, 1000); // initial delay

    const dataInterval = setInterval(() => {
      // Update Chart
      setChartData(prev => {
        const nextVal = prev[prev.length - 1] + (Math.random() - 0.4) * 5;
        return [...prev.slice(1), nextVal];
      });
      // Update Orderbook
      setOrderbook({
        bids: Array(3).fill(0).map((_, idx) => 3400 - idx - Math.random()),
        asks: Array(3).fill(0).map((_, idx) => 3401 + idx + Math.random())
      });
    }, 800);

    return () => {
      isTyping = false;
      clearInterval(dataInterval);
    };
  }, []);

  // SVG path
  const validData = chartData.length > 0 ? chartData : [0];
  const max = Math.max(...validData) + 2;
  const min = Math.min(...validData) - 2;
  const pathData = validData.map((val, i) => {
    const x = (i / (validData.length - 1)) * 100;
    const y = 100 - ((val - min) / (max - min)) * 100;
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');

  return (
    <div 
      ref={containerRef}
      onMouseMove={handleMouseMove}
      className="min-h-screen bg-[#000000] text-white selection:bg-cyan-500/30 font-sans overflow-x-hidden relative"
    >
      {/* Interactive Spotlight Glow */}
      <div 
        className="pointer-events-none absolute inset-0 z-10 transition-opacity duration-300"
        style={{
          background: `radial-gradient(600px circle at ${mousePosition.x}px ${mousePosition.y}px, rgba(6, 182, 212, 0.07), transparent 40%)`
        }}
      />

      {/* Dynamic Background Grid */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_110%)] animate-[pulse_10s_ease-in-out_infinite]" />
        <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] bg-cyan-600/10 rounded-full blur-[150px] mix-blend-screen" />
        <div className="absolute top-[20%] right-[-20%] w-[800px] h-[800px] bg-purple-600/10 rounded-full blur-[150px] mix-blend-screen" />
      </div>

      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/[0.05] bg-black/60 backdrop-blur-xl h-16 flex items-center">
        <div className="flex items-center justify-between px-6 lg:px-8 w-full max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-400 to-purple-600 p-[1px] shadow-[0_0_15px_-3px_rgba(6,182,212,0.4)]">
              <div className="w-full h-full bg-black rounded-[11px] flex items-center justify-center">
                <Activity className="w-4 h-4 text-cyan-400" />
              </div>
            </div>
            <span className="font-bold text-xl tracking-tighter bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">PnLClaw</span>
            <span className="hidden sm:inline-block px-2 py-[2px] rounded-md bg-white/[0.03] border border-white/10 text-[10px] font-mono text-cyan-500/80 uppercase tracking-widest">v0.1 Local</span>
          </div>
          <div className="flex gap-8 text-sm font-medium text-gray-500 hover:text-gray-400 transition-colors">
            <a href="#" className="hover:text-white transition-colors">Architecture</a>
            <a href="#" className="hover:text-white transition-colors">Engine</a>
            <a href="#" className="hover:text-white transition-colors hidden sm:block">Security</a>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="relative z-20 max-w-7xl mx-auto px-6 lg:px-8 pt-32 pb-20 sm:pb-32">
        <motion.div style={{ y: heroY, opacity: heroOpacity }} className="text-center max-w-4xl mx-auto">
          <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-3 px-4 py-1.5 rounded-full bg-cyan-500/5 border border-cyan-500/20 text-sm text-cyan-300 mb-8 backdrop-blur-md shadow-[0_0_30px_-5px_rgba(6,182,212,0.3)]"
          >
            <Zap className="w-4 h-4" /> AGPL-3.0 协议开源本地量化引擎
          </motion.div>
          
          <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1 }}
            className="text-6xl md:text-7xl lg:text-[5.5rem] font-black tracking-tighter mb-8 leading-[1.05]"
          >
            <span className="bg-clip-text text-transparent bg-gradient-to-b from-white via-gray-200 to-gray-500">Local AI Meets</span>
            <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-indigo-400 to-purple-400 drop-shadow-[0_0_25px_rgba(168,85,247,0.4)]">Quant Execution.</span>
          </motion.h1>
          
          <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.2 }}
            className="text-lg md:text-xl text-gray-400 mb-10 max-w-2xl mx-auto font-light leading-relaxed"
          >
            使用 Tauri + Python 打造。数据不再传给云端，密钥不再离开桌面。享受 L2 WebSocket 直连、毫秒级回测与多 Agent 联合风控。
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.3 }}
            className="flex flex-wrap items-center justify-center gap-4"
          >
            <div className="px-8 py-4 rounded-xl bg-white text-black font-semibold hover:bg-gray-100 cursor-pointer shadow-[0_0_40px_-10px_rgba(255,255,255,0.8)] transition-all transform hover:scale-105 flex items-center gap-2">
              <Code className="w-5 h-5" /> Start Paper Trading
            </div>
            <div className="px-8 py-4 rounded-xl bg-white/5 border border-white/10 text-white font-semibold hover:bg-white/10 cursor-pointer transition-all flex items-center gap-3">
              <Terminal className="w-5 h-5 text-gray-400"/> <span className="font-mono text-sm text-cyan-100 pnlclaw-cmd">pnlclaw setup</span>
            </div>
          </motion.div>
        </motion.div>

        <motion.div style={{ y: heroY, opacity: heroOpacity }} className="mt-16 flex flex-wrap justify-center gap-3">
          <GlowingBadge text="Tauri 2 Core" colorClass="text-amber-400 border-amber-400/20" />
          <GlowingBadge text="FastAPI Runtime" colorClass="text-emerald-400 border-emerald-400/20" />
          <GlowingBadge text="Parquet Storage" colorClass="text-cyan-400 border-cyan-400/20" />
          <GlowingBadge text="React + shadcn" colorClass="text-indigo-400 border-indigo-400/20" />
        </motion.div>

        {/* Demo Dual Panel */}
        <div className="mt-20 grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-7xl mx-auto relative">
          
          {/* Main Terminal */}
          <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1, delay: 0.4 }}
            className="lg:col-span-7 flex flex-col rounded-2xl border border-white/10 bg-[#0a0a0a]/90 backdrop-blur-2xl p-0 shadow-2xl relative overflow-hidden ring-1 ring-white/5"
          >
            <div className="h-10 border-b border-white/[0.05] bg-white/[0.01] flex items-center px-4 shrink-0">
              <div className="flex gap-1.5 object-left">
                <div className="w-3 h-3 rounded-full bg-red-500/80" />
                <div className="w-3 h-3 rounded-full bg-amber-500/80" />
                <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
              </div>
              <div className="mx-auto px-3 py-1 bg-white/5 rounded-md text-[10px] font-mono text-gray-500 border border-white/5 tracking-widest">AGENT_RUNTIME_SANDBOX</div>
            </div>
            
            <div className="p-6 md:p-8 font-mono text-sm flex flex-col justify-center min-h-[380px]">
               <div className="flex gap-4 items-start w-full transition-all">
                 <div className="w-7 h-7 rounded-lg bg-cyan-500/10 flex items-center justify-center shrink-0 border border-cyan-500/30">
                   <div className="text-xs text-cyan-400 font-sans font-bold">U</div>
                 </div>
                 <div className="flex-1 bg-white/[0.03] rounded-2xl rounded-tl-none p-4 border border-white/[0.05] text-gray-200 leading-relaxed drop-shadow-sm">
                    {typedText}
                    <span className="inline-block w-2 h-4 bg-cyan-400 ml-1 animate-[pulse_1s_step-start_infinite] align-middle" />
                 </div>
               </div>
               
               <AnimatePresence>
                 {typedText.length === fullText.length && (
                   <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.5 }} className="flex gap-4 items-start w-full mt-6">
                     <div className="w-7 h-7 rounded-lg bg-purple-500/10 flex items-center justify-center shrink-0 border border-purple-500/30">
                       <Cpu className="w-4 h-4 text-purple-400" />
                     </div>
                     <div className="flex-1 space-y-3">
                       <div className="flex flex-wrap gap-2 text-[10px] tracking-wide">
                         <span className="bg-purple-500/10 text-purple-300 px-2 py-1.5 rounded flex items-center gap-1 border border-purple-500/20"><Activity className="w-3 h-3"/> get_market_kline</span>
                         <span className="bg-cyan-500/10 text-cyan-300 px-2 py-1.5 rounded flex items-center gap-1 border border-cyan-500/20"><Globe className="w-3 h-3"/> analyze_regime</span>
                       </div>
                       <div className="text-purple-300 border-l-[2px] border-purple-500/50 pl-4 py-2 bg-gradient-to-r from-purple-500/5 to-transparent rounded-r-lg">
                         <p className="text-gray-400 mb-1">{"{"}</p>
                         <p className="pl-4">&quot;status&quot;: <span className="text-emerald-400">&quot;SUCCESS&quot;</span>,</p>
                         <p className="pl-4">&quot;action&quot;: <span className="text-emerald-400">&quot;COMPILED_STRATEGY&quot;</span>,</p>
                         <p className="pl-4">&quot;engine&quot;: <span className="text-emerald-400">&quot;Backtest Ready&quot;</span></p>
                         <p className="text-gray-400 mt-1">{"}"}</p>
                         <span className="text-white mt-3 inline-block font-sans text-sm"><span className="text-purple-400 font-bold">Executing test</span> on 90d data streams...</span>
                       </div>
                     </div>
                   </motion.div>
                 )}
               </AnimatePresence>
            </div>
          </motion.div>

          {/* Widgets Stack */}
          <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1, delay: 0.6 }}
            className="lg:col-span-5 flex flex-col gap-6"
          >
            {/* Chart Widget */}
            <div className="rounded-2xl border border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl p-6 relative overflow-hidden h-44 flex flex-col ring-1 ring-white/5 group">
               <div className="absolute inset-0 bg-gradient-to-b from-transparent to-cyan-500/5 opacity-50 transition-opacity group-hover:opacity-100" />
               <div className="relative z-10 flex justify-between items-start">
                 <div>
                   <h3 className="text-gray-500 font-mono text-[10px] tracking-widest mb-1">UNREALIZED PNL</h3>
                   <div className="text-3xl font-bold text-white tracking-widest">+ $4,239.<span className="text-xl text-gray-400">50</span></div>
                 </div>
                 <div className="px-2 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded text-emerald-400 flex items-center gap-1.5 text-[10px] font-mono tracking-widest">
                   <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> LIVE
                 </div>
               </div>
               
               <div className="relative z-10 mt-auto h-20 w-full">
                 <svg viewBox="0 0 100 100" className="w-full h-full overflow-visible" preserveAspectRatio="none">
                   <defs>
                     <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
                       <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.4" />
                       <stop offset="100%" stopColor="#06b6d4" stopOpacity="0" />
                     </linearGradient>
                   </defs>
                   <motion.path d={`${pathData} L 100 100 L 0 100 Z`} fill="url(#lineGrad)" className="transition-all duration-700 ease-out" />
                   <motion.path d={pathData} fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" 
                     style={{ filter: "drop-shadow(0px 0px 6px rgba(34,211,238,0.6))" }} className="transition-all duration-700 ease-out" />
                 </svg>
               </div>
            </div>

            {/* Orderbook Simulated Widget */}
            <div className="rounded-2xl border border-white/10 bg-[#0a0a0a]/80 backdrop-blur-2xl p-5 flex-1 ring-1 ring-white/5 relative overflow-hidden">
               <div className="text-gray-500 uppercase tracking-widest text-[10px] font-mono mb-4 flex justify-between">
                 <span>L2 Orderbook Stream</span>
                 <span className="text-cyan-500/70">WSS://</span>
               </div>
               <div className="grid grid-cols-2 gap-4 font-mono text-xs">
                 <div className="space-y-1.5">
                   <div className="text-gray-600 text-[9px] mb-2 border-b border-white/5 pb-1">ASKS</div>
                   {orderbook.asks.map((ask, idx) => (
                     <div key={`ask-${idx}`} className="flex justify-between text-red-400/90 relative">
                       <div className="absolute right-0 top-0 bottom-0 bg-red-500/10 -z-10" style={{width: `${Math.random() * 100}%`}}></div>
                       <span>{ask.toFixed(1)}</span>
                       <span className="text-gray-500">{(Math.random() * 2).toFixed(3)}</span>
                     </div>
                   ))}
                 </div>
                 <div className="space-y-1.5">
                   <div className="text-gray-600 text-[9px] mb-2 border-b border-white/5 pb-1">BIDS</div>
                   {orderbook.bids.map((bid, idx) => (
                     <div key={`bid-${idx}`} className="flex justify-between text-emerald-400/90 relative">
                       <div className="absolute left-0 top-0 bottom-0 bg-emerald-500/10 -z-10" style={{width: `${Math.random() * 100}%`}}></div>
                       <span>{bid.toFixed(1)}</span>
                       <span className="text-gray-500">{(Math.random() * 2).toFixed(3)}</span>
                     </div>
                   ))}
                 </div>
               </div>
               
               <div className="mt-4 pt-3 border-t border-white/[0.05] flex gap-3 font-mono text-[10px]">
                 <span className="text-cyan-400">INFO</span>
                 <span className="text-gray-400">Gateway matching engine connected...</span>
               </div>
            </div>
          </motion.div>
        </div>
      </main>

      {/* Bento Grid */}
      <section className="relative z-20 max-w-7xl mx-auto px-6 lg:px-8 py-24 sm:py-32 border-t border-white/5 bg-black/40">
        <div className="flex flex-col items-center mb-20 text-center">
          <h2 className="text-4xl md:text-6xl font-black tracking-tighter mb-6 bg-clip-text text-transparent bg-gradient-to-b from-white to-gray-500">Under the Hood.</h2>
          <p className="text-gray-400 max-w-2xl font-light text-lg">不妥协的工程实现标准，每一行代码都为交易的稳定性与安全性服务。</p>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 auto-rows-[300px]" onMouseMove={handleMouseMove}>
          
          <motion.div viewport={{ once: true }} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}
            className="md:col-span-2 rounded-3xl border border-white/[0.08] bg-[#050505] p-8 relative overflow-hidden group hover:border-white/20 transition-all"
          >
            <div className="absolute top-0 right-0 p-8 transform translate-x-4 -translate-y-4 group-hover:scale-110 transition-transform duration-700 ease-out">
              <Lock className="w-48 h-48 text-cyan-500-[0.03]" />
            </div>
            <div className="relative z-10 flex flex-col h-full justify-between">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-cyan-500/20 to-transparent border border-cyan-500/20 flex items-center justify-center mb-6 shadow-inner">
                <Shield className="w-7 h-7 text-cyan-400" />
              </div>
              <div className="max-w-md">
                <h3 className="text-3xl font-bold text-white tracking-tight mb-4">Absolute Privacy.<br/><span className="text-cyan-400">No Cloud.</span></h3>
                <p className="text-gray-400 leading-relaxed font-light">
                  所有的 API 密钥安全存储在 OS Keychain 中，永远不会出现在 prompt 或前端日志中。你可以随意接入本地的 Ollama 模型，完全沙盒化。
                </p>
              </div>
            </div>
          </motion.div>

          {/* Continuing with Bento Cards... */}
          <motion.div viewport={{ once: true }} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className="rounded-3xl border border-white/[0.08] bg-[#050505] p-8 relative overflow-hidden group hover:border-white/20 transition-all"
          >
            <div className="relative z-10 flex flex-col h-full justify-between">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500/20 to-transparent border border-purple-500/20 flex items-center justify-center mb-6">
                <Globe className="w-7 h-7 text-purple-400" />
              </div>
              <div>
                <h3 className="text-2xl font-bold text-white tracking-tight mb-3">L2 OrderBook</h3>
                <p className="text-gray-400 text-sm leading-relaxed font-light">原生实现 WebSocket 引擎，跨过第三方网关直连，极速聚合 TickerEvent，确保毫秒不差。</p>
              </div>
            </div>
          </motion.div>

          <motion.div viewport={{ once: true }} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.3 }}
            className="rounded-3xl border border-white/[0.08] bg-[#050505] p-8 relative overflow-hidden group hover:border-white/20 transition-all"
          >
             <div className="relative z-10 flex flex-col h-full justify-between">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500/20 to-transparent border border-emerald-500/20 flex items-center justify-center mb-6">
                <Database className="w-7 h-7 text-emerald-400" />
              </div>
              <div>
                <h3 className="text-2xl font-bold text-white tracking-tight mb-3">Parquet Engine</h3>
                <p className="text-gray-400 text-sm leading-relaxed font-light">使用列式存储格式 Parquet 存储时序向量，让海量历史数据的回测读写毫无压力。</p>
              </div>
            </div>
          </motion.div>

          <motion.div viewport={{ once: true }} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }}
            className="md:col-span-2 rounded-3xl border border-white/[0.08] bg-[#050505] p-8 relative overflow-hidden group hover:border-white/20 transition-all flex flex-col md:flex-row items-center gap-8"
          >
            <div className="w-full md:w-1/2">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-white/10 to-transparent border border-white/10 flex items-center justify-center mb-6">
                <Server className="w-7 h-7 text-white" />
              </div>
              <h3 className="text-3xl font-bold text-white tracking-tight mb-4">Multi-Agent<br/>Pipeline</h3>
              <p className="text-gray-400 mb-6 text-sm leading-relaxed font-light">Market Analyst 监控分析，Strategy Architect 提出建议，Risk Guardian 负责拦截熔断。全员在本地为你效劳。</p>
            </div>
            
            <div className="w-full md:w-1/2 h-full bg-[#0a0a0a] border border-white/[0.03] rounded-2xl p-5 flex flex-col font-mono text-[11px] shadow-inner ring-1 ring-white/5">
              <div className="flex justify-between text-gray-500 border-b border-white/[0.05] pb-3 mb-3 tracking-widest">
                <span>{"// core_pipeline.py"}</span>
              </div>
              <div className="space-y-2 opacity-80">
                <div className="text-gray-400"><span className="text-purple-400 font-bold">async def</span> <span className="text-blue-300">execute_intent</span>(intent: TradeIntent):</div>
                <div className="text-gray-500 pl-4">{"# Security Gateway interop"}</div>
                <div className="text-gray-400 pl-4">decision = <span className="text-amber-300">await</span> risk_guardian.<span className="text-blue-300">pre_check</span>()</div>
                <div className="text-gray-400 pl-4"><span className="text-purple-400 font-bold">if</span> decision.status == <span className="text-emerald-300">&quot;APPROVED&quot;</span>:</div>
                <div className="text-gray-400 pl-8"><span className="text-amber-300">await</span> engine.<span className="text-blue-300">place_order</span>(intent)</div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
      
      {/* Footer */}
      <footer className="border-t border-white/5 bg-[#000] py-16 flex flex-col items-center justify-center relative z-20">
        <div className="w-10 h-10 rounded-xl bg-[#0a0a0a] border border-white/10 flex items-center justify-center mb-6">
           <Activity className="w-5 h-5 text-gray-600" />
        </div>
        <div className="text-gray-600 font-mono text-xs tracking-widest mb-3">
          $ pnlclaw doctor <span className="text-emerald-500/50">[SYSTEM_HEALTHY]</span>
        </div>
        <div className="text-gray-700 text-[10px] tracking-widest uppercase">
          AGPL-3.0-only • Built for Quant
        </div>
      </footer>
    </div>
  );
}
