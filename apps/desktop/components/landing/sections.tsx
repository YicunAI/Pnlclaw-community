"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  motion, useInView, useScroll, useTransform,
  useMotionValue, useSpring, useMotionTemplate,
  AnimatePresence,
} from "framer-motion";
import {
  MessageSquare, Shield, Zap, Brain, Layers, Lock,
  Bot, BarChart3, LineChart, TrendingUp, Settings,
  BookOpen, AlertTriangle, ArrowRight, GitBranch,
  ChevronRight, ExternalLink, Star, Github,
  Boxes, Database, Globe2, Terminal, Mail,
  Check, Sparkles, Target, Workflow,
} from "lucide-react";

// ─── helpers ──────────────────────────────────────────────────────────────────

function Reveal({ children, delay = 0, className = "" }: {
  children: React.ReactNode; delay?: number; className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <motion.div ref={ref} className={className}
      initial={{ opacity: 0, y: 36 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

function Counter({ to, suffix = "", prefix = "" }: {
  to: number; suffix?: string; prefix?: string;
}) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      let s: number | null = null;
      const step = (ts: number) => {
        if (!s) s = ts;
        const p = Math.min((ts - s) / 1600, 1);
        setVal(Math.round((1 - Math.pow(1 - p, 3)) * to));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step); obs.disconnect();
    }, { threshold: 0.5 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [to]);
  return <span ref={ref}>{prefix}{val}{suffix}</span>;
}

function SectionLabel({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-2.5 rounded-full border border-white/10 bg-white/[0.04] px-5 py-2 text-xs uppercase tracking-[0.3em] text-white/40 backdrop-blur-sm mb-8">
      <span className="size-2 rounded-full bg-cyan-400 animate-pulse" />
      {text}
    </span>
  );
}

function GlowCard({ children, className = "", color = "cyan" }: {
  children: React.ReactNode; className?: string; color?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mx = useMotionValue(0), my = useMotionValue(0);
  const onMove = useCallback((e: React.PointerEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    mx.set(e.clientX - r.left); my.set(e.clientY - r.top);
  }, [mx, my]);
  const bg = useMotionTemplate`radial-gradient(400px circle at ${mx}px ${my}px, rgba(34,211,238,0.06), transparent 70%)`;

  return (
    <motion.div ref={ref}
      className={`group relative rounded-2xl border border-white/[0.08] bg-white/[0.02] overflow-hidden backdrop-blur-sm transition-colors hover:border-white/[0.15] ${className}`}
      onPointerMove={onMove}
      whileHover={{ y: -4 }}
      transition={{ duration: 0.25 }}
    >
      <motion.div className="absolute inset-0 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" style={{ background: bg }} />
      {children}
    </motion.div>
  );
}

// ─── 1. Ticker Marquee ────────────────────────────────────────────────────────

const TICKERS = [
  { pair: "BTC/USDT", price: "67,828", chg: "+2.34%", up: true },
  { pair: "ETH/USDT", price: "3,412", chg: "+1.87%", up: true },
  { pair: "SOL/USDT", price: "142.56", chg: "+4.21%", up: true },
  { pair: "BNB/USDT", price: "581.30", chg: "-0.43%", up: false },
  { pair: "ARB/USDT", price: "1.024", chg: "+3.45%", up: true },
  { pair: "POLYMARKET", price: "0.67", chg: "67¢ Yes", up: true },
  { pair: "OP/USDT", price: "2.156", chg: "+6.12%", up: true },
  { pair: "AVAX/USDT", price: "33.41", chg: "-0.88%", up: false },
];

export function TickerMarquee() {
  const items = [...TICKERS, ...TICKERS, ...TICKERS];
  return (
    <div className="relative overflow-hidden py-3 border-y border-white/[0.06] bg-black/40">
      <div className="absolute inset-y-0 left-0 w-20 z-10 bg-gradient-to-r from-[#0a0a0a] to-transparent" />
      <div className="absolute inset-y-0 right-0 w-20 z-10 bg-gradient-to-l from-[#0a0a0a] to-transparent" />
      <motion.div className="flex gap-12 w-max"
        animate={{ x: ["-33.33%", "0%"] }}
        transition={{ duration: 30, repeat: Infinity, ease: "linear" }}>
        {items.map((t, i) => (
          <span key={i} className="shrink-0 flex items-center gap-2.5 text-[11px] font-mono">
            <span className="text-white/40">{t.pair}</span>
            <span className="text-white/70">{t.price}</span>
            <span className={t.up ? "text-emerald-400" : "text-red-400"}>{t.chg}</span>
          </span>
        ))}
      </motion.div>
    </div>
  );
}

// ─── 2. Core Philosophy — Sticky Scroll + Liquid Glass ──────────────────────

const PHILOSOPHY_CARDS = [
  {
    num: "01",
    title: "对话即量化",
    subtitle: "Natural Language → Strategy → Backtest → Deploy",
    desc: "用自然语言描述交易思路，Agent 自动生成 YAML 配置、运行回测、分析结果并建议优化方向——在多轮对话中持续迭代，形成完整闭环。",
    accent: "cyan",
    visual: "terminal",
  },
  {
    num: "02",
    title: "本地优先",
    subtitle: "Your keys, your machine, your data",
    desc: "无需订阅、无云端依赖。API 密钥和策略代码永远留在你的硬件上。密钥通过 Security Gateway 脱敏，绝不进入提示词或日志。",
    accent: "emerald",
    visual: "vault",
  },
  {
    num: "03",
    title: "事件驱动统一架构",
    subtitle: "Write once, run everywhere",
    desc: "回测、模拟交易和实盘共享完全相同的事件循环和 L2 盘口数据模型。一次编写策略，到处运行。",
    accent: "amber",
    visual: "flow",
  },
  {
    num: "04",
    title: "技能驱动 Agent",
    subtitle: "8 built-in skills · MCP extensible",
    desc: "8 个内置量化技能覆盖策略起草、代码生成、回测解读、市场分析、PnL 归因、风控报告、指标教学、交易所配置。支持 MCP 扩展，与 LLM 解耦。",
    accent: "violet",
    visual: "constellation",
  },
  {
    num: "05",
    title: "Security by Design",
    subtitle: "Not a general-purpose agent",
    desc: "高风险能力严格管控。Shell 执行与文件写入默认禁用。Agent 不持有默认的系统权限，实盘交易需要显式开启。",
    accent: "rose",
    visual: "radar",
  },
];

const ACCENT_STYLES: Record<string, {
  border: string; glow: string; text: string; bg: string; line: string;
}> = {
  cyan:    { border: "border-cyan-500/20",    glow: "shadow-[0_0_80px_rgba(34,211,238,0.08)]",    text: "text-cyan-400",    bg: "bg-cyan-500",    line: "from-cyan-500/30" },
  emerald: { border: "border-emerald-500/20", glow: "shadow-[0_0_80px_rgba(52,211,153,0.08)]",   text: "text-emerald-400", bg: "bg-emerald-500", line: "from-emerald-500/30" },
  amber:   { border: "border-amber-500/20",   glow: "shadow-[0_0_80px_rgba(245,158,11,0.08)]",   text: "text-amber-400",   bg: "bg-amber-500",   line: "from-amber-500/30" },
  violet:  { border: "border-violet-500/20",  glow: "shadow-[0_0_80px_rgba(139,92,246,0.08)]",   text: "text-violet-400",  bg: "bg-violet-500",  line: "from-violet-500/30" },
  rose:    { border: "border-rose-500/20",    glow: "shadow-[0_0_80px_rgba(244,63,94,0.08)]",    text: "text-rose-400",    bg: "bg-rose-500",    line: "from-rose-500/30" },
};

/* ── Liquid glass card shell ── */
function GlassCard({ children, accent, className = "" }: {
  children: React.ReactNode; accent: string; className?: string;
}) {
  const s = ACCENT_STYLES[accent];
  const ref = useRef<HTMLDivElement>(null);
  const mx = useMotionValue(0), my = useMotionValue(0);
  const rx = useSpring(useTransform(my, [-200, 200], [4, -4]), { stiffness: 200, damping: 30 });
  const ry = useSpring(useTransform(mx, [-200, 200], [-4, 4]), { stiffness: 200, damping: 30 });

  const onMove = useCallback((e: React.PointerEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    mx.set(e.clientX - r.left - r.width / 2);
    my.set(e.clientY - r.top - r.height / 2);
  }, [mx, my]);
  const onLeave = useCallback(() => { mx.set(0); my.set(0); }, [mx, my]);

  return (
    <motion.div ref={ref}
      className={`relative group rounded-[1.5rem] overflow-hidden ${s.glow} ${className}`}
      style={{ rotateX: rx, rotateY: ry, perspective: 1200, transformStyle: "preserve-3d" }}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
    >
      {/* animated border glow */}
      <div className={`absolute -inset-px rounded-[1.5rem] border ${s.border} transition-colors duration-500 group-hover:${s.border.replace("/20", "/40")}`} />

      {/* liquid glass layers */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.04] via-transparent to-white/[0.02]" />
      <div className="absolute inset-0 backdrop-blur-md" style={{ background: "rgba(12,12,20,0.75)" }} />

      {/* refraction highlight */}
      <motion.div className="absolute inset-0 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-700"
        style={{
          background: useMotionTemplate`radial-gradient(500px circle at ${useTransform(mx, v => v + 300)}px ${useTransform(my, v => v + 250)}px, rgba(255,255,255,0.04), transparent 60%)`,
        }} />

      {/* noise texture */}
      <div className="absolute inset-0 opacity-[0.015] pointer-events-none"
        style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")" }} />

      {/* rainbow shimmer on hover */}
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-1000 pointer-events-none bg-[conic-gradient(from_var(--border-angle),transparent,rgba(255,255,255,0.02),transparent,rgba(255,255,255,0.01),transparent)] animate-border-spin" />

      <div className="relative z-10">
        {children}
      </div>
    </motion.div>
  );
}

/* ── Card visual: Terminal ── */
function CardVisualTerminal() {
  const lines = [
    { p: "user ", c: "text-cyan-400", t: "设计一个 BTC 的 EMA 交叉策略" },
    { p: "agent", c: "text-emerald-400", t: "▸ strategy_validate → ema_cross" },
    { p: "     ", c: "text-white/30", t: "  fast:20  slow:50  symbol:BTCUSDT" },
    { p: "agent", c: "text-emerald-400", t: "✓ 已生成，准备回测" },
    { p: "user ", c: "text-cyan-400", t: "回测最近 90 天" },
    { p: "agent", c: "text-emerald-400", t: "▸ backtest_run …" },
    { p: "     ", c: "text-amber-400", t: "  Sharpe 1.45 | DD -6.8% | Win 52%" },
    { p: "agent", c: "text-emerald-400", t: "建议: 加 RSI>40 过滤假信号" },
    { p: "user ", c: "text-cyan-400", t: "好, 加上再跑" },
    { p: "     ", c: "text-emerald-300", t: "  Sharpe ↑1.72 | Win ↑58% | DD ↓5.1%" },
    { p: "agent", c: "text-emerald-400", t: "✓ 策略显著改善，建议部署" },
  ];
  const [n, setN] = useState(0);
  useEffect(() => {
    if (n >= lines.length) { const t = setTimeout(() => setN(0), 2500); return () => clearTimeout(t); }
    const t = setTimeout(() => setN(c => c + 1), 550);
    return () => clearTimeout(t);
  }, [n, lines.length]);

  return (
    <div className="rounded-xl bg-black/50 border border-white/[0.05] p-4 font-mono text-[10.5px] leading-[1.8]">
      <div className="flex items-center gap-1.5 mb-2.5">
        <span className="size-[7px] rounded-full bg-[#ff5f57]" />
        <span className="size-[7px] rounded-full bg-[#febc2e]" />
        <span className="size-[7px] rounded-full bg-[#28c840]" />
        <span className="ml-2 text-[9px] text-white/15 font-sans">pnlclaw agent</span>
      </div>
      <div className="h-[150px] overflow-hidden relative">
        <div className="absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-black/50 to-transparent z-10" />
        <div style={{ transform: `translateY(-${Math.max(0, n - 7) * 19}px)`, transition: "transform 0.3s" }}>
          {lines.map((l, i) => (
            <div key={i} className={`transition-opacity duration-300 ${i < n ? "opacity-100" : "opacity-0"}`}>
              <span className="text-white/15 select-none">{l.p} </span><span className={l.c}>{l.t}</span>
            </div>
          ))}
        </div>
        {n < lines.length && (
          <motion.span className="inline-block w-[6px] h-[13px] bg-cyan-400/70"
            animate={{ opacity: [1, 0] }} transition={{ duration: 0.5, repeat: Infinity }} />
        )}
      </div>
    </div>
  );
}

/* ── Card visual: Vault orbits ── */
function CardVisualVault() {
  return (
    <div className="flex items-center justify-center h-[180px]">
      <div className="relative w-[180px] h-[180px]">
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <motion.div className="size-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center"
            animate={{ scale: [1, 1.08, 1] }} transition={{ duration: 3, repeat: Infinity }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="rgb(52,211,153)" strokeWidth="1.5">
              <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0110 0v4" /><circle cx="12" cy="16" r="1.5" fill="rgb(52,211,153)" />
            </svg>
          </motion.div>
        </div>
        {[40, 62, 84].map((r, i) => (
          <motion.div key={i} className="absolute rounded-full border border-emerald-500/[0.08]"
            style={{ inset: `${90 - r}px` }}
            animate={{ rotate: i % 2 === 0 ? 360 : -360 }}
            transition={{ duration: 12 + i * 6, repeat: Infinity, ease: "linear" }}>
            {Array.from({ length: 3 + i * 2 }).map((_, d) => {
              const a = (d / (3 + i * 2)) * Math.PI * 2;
              return <div key={d} className="absolute size-[5px] rounded-full bg-emerald-400/50 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                style={{ left: `calc(50% + ${Math.cos(a) * r * 0.5}px - 2.5px)`, top: `calc(50% + ${Math.sin(a) * r * 0.5}px - 2.5px)` }} />;
            })}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ── Card visual: Event flow ── */
function CardVisualFlow() {
  return (
    <div className="relative h-[180px]">
      <svg className="w-full h-full" viewBox="0 0 200 120">
        <defs>
          <linearGradient id="gAmber" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="rgba(245,158,11,0.5)" /><stop offset="100%" stopColor="rgba(245,158,11,0)" /></linearGradient>
        </defs>
        {/* flow paths */}
        {[
          { d: "M20,60 C60,20 140,20 180,60", label: "Backtest" },
          { d: "M20,60 L180,60", label: "Paper" },
          { d: "M20,60 C60,100 140,100 180,60", label: "Live" },
        ].map(({ d, label }, i) => (
          <g key={i}>
            <path d={d} fill="none" stroke="rgba(245,158,11,0.08)" strokeWidth="1" />
            <circle r="2.5" fill="rgba(245,158,11,0.8)">
              <animateMotion dur={`${3 + i}s`} repeatCount="indefinite" path={d} />
            </circle>
            <circle r="1.5" fill="rgba(245,158,11,0.4)">
              <animateMotion dur={`${3 + i}s`} begin={`${1.5 + i * 0.5}s`} repeatCount="indefinite" path={d} />
            </circle>
            <text x="100" y={i === 0 ? 18 : i === 1 ? 55 : 115} textAnchor="middle" fill="rgba(255,255,255,0.2)" fontSize="7" fontFamily="monospace">{label}</text>
          </g>
        ))}
        {/* nodes */}
        {[{ x: 20, y: 60, l: "WS" }, { x: 180, y: 60, l: "Engine" }].map(n => (
          <g key={n.l}>
            <circle cx={n.x} cy={n.y} r="10" fill="rgba(245,158,11,0.06)" stroke="rgba(245,158,11,0.25)" strokeWidth="0.8">
              <animate attributeName="r" values="10;12;10" dur="3s" repeatCount="indefinite" />
            </circle>
            <text x={n.x} y={n.y + 1} textAnchor="middle" dominantBaseline="middle" fill="rgba(245,158,11,0.6)" fontSize="6" fontWeight="bold">{n.l}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

/* ── Card visual: Constellation ── */
function CardVisualConstellation() {
  const skills = ["策略起草", "代码生成", "回测解读", "市场分析", "PnL归因", "风控报告", "指标教学", "交易所配置"];
  const [hovered, setHovered] = useState<number | null>(null);
  const cx = 110, cy = 90, R = 60;
  const pos = skills.map((_, i) => {
    const a = (i / skills.length) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R };
  });
  return (
    <div className="relative h-[180px]">
      <svg className="w-full h-full" viewBox="0 0 220 180">
        {pos.map((p, i) => (
          <line key={`l${i}`} x1={cx} y1={cy} x2={p.x} y2={p.y}
            stroke={hovered === i ? "rgba(139,92,246,0.5)" : "rgba(139,92,246,0.08)"} strokeWidth="0.5"
            style={{ transition: "stroke 0.3s" }} />
        ))}
        <circle cx={cx} cy={cy} r="12" fill="rgba(139,92,246,0.08)" stroke="rgba(139,92,246,0.25)" strokeWidth="0.6">
          <animate attributeName="r" values="12;14;12" dur="4s" repeatCount="indefinite" />
        </circle>
        <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle" fill="rgba(139,92,246,0.7)" fontSize="6" fontWeight="bold">Agent</text>
        {pos.map((p, i) => (
          <g key={i} onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)} style={{ cursor: "pointer" }}>
            <circle cx={p.x} cy={p.y} r={hovered === i ? 16 : 12}
              fill={hovered === i ? "rgba(139,92,246,0.12)" : "rgba(139,92,246,0.04)"}
              stroke={hovered === i ? "rgba(139,92,246,0.5)" : "rgba(139,92,246,0.15)"}
              strokeWidth="0.5" style={{ transition: "all 0.3s" }} />
            <text x={p.x} y={p.y + 1} textAnchor="middle" dominantBaseline="middle"
              fill={hovered === i ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.3)"}
              fontSize="4.5" style={{ transition: "fill 0.3s" }}>{skills[i]}</text>
          </g>
        ))}
        {[0, 3, 5].map(i => (
          <circle key={`p${i}`} r="1.5" fill="rgba(139,92,246,0.7)">
            <animateMotion dur={`${3.5 + i * 0.4}s`} repeatCount="indefinite" path={`M${cx},${cy} L${pos[i].x},${pos[i].y} L${cx},${cy}`} />
          </circle>
        ))}
      </svg>
    </div>
  );
}

/* ── Card visual: Radar ── */
function CardVisualRadar() {
  const labels = ["Shell 禁用", "文件写禁用", "实盘 opt-in", "幻觉检测"];
  return (
    <div className="flex items-center justify-center h-[180px]">
      <div className="relative w-[170px] h-[170px]">
        {[1, 2, 3].map(i => (
          <div key={i} className="absolute rounded-full border border-rose-500/[0.07]" style={{ inset: `${(3 - i) * 22}px` }} />
        ))}
        <motion.div className="absolute inset-0" animate={{ rotate: 360 }} transition={{ duration: 4, repeat: Infinity, ease: "linear" }}>
          <div className="absolute top-1/2 left-1/2 w-1/2 h-px origin-left" style={{ background: "linear-gradient(to right, rgba(244,63,94,0.5), transparent)" }} />
          <div className="absolute top-1/2 left-1/2 w-1/2 origin-left" style={{ height: 35, marginTop: -35, background: "conic-gradient(from 0deg, transparent, rgba(244,63,94,0.06))" }} />
        </motion.div>
        {labels.map((label, i) => {
          const a = (i / labels.length) * Math.PI * 2 - Math.PI / 2;
          return (
            <motion.div key={label} className="absolute flex flex-col items-center gap-0.5"
              style={{ left: 85 + Math.cos(a) * 55 - 22, top: 85 + Math.sin(a) * 55 - 8, width: 44 }}
              animate={{ opacity: [0.35, 1, 0.35] }} transition={{ duration: 2, repeat: Infinity, delay: i * 0.5 }}>
              <div className="size-2.5 rounded-full bg-rose-400/50 shadow-[0_0_8px_rgba(244,63,94,0.4)]" />
              <span className="text-[7px] text-rose-300/40 text-center whitespace-nowrap">{label}</span>
            </motion.div>
          );
        })}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="size-7 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgb(244,63,94)" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
          </div>
        </div>
      </div>
    </div>
  );
}

const VISUAL_MAP: Record<string, () => React.JSX.Element> = {
  terminal: CardVisualTerminal,
  vault: CardVisualVault,
  flow: CardVisualFlow,
  constellation: CardVisualConstellation,
  radar: CardVisualRadar,
};

export function CorePhilosophy() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ["start start", "end end"] });
  const activeRaw = useTransform(scrollYProgress, [0, 1], [0, PHILOSOPHY_CARDS.length - 0.01]);
  const activeSmooth = useSpring(activeRaw, { stiffness: 100, damping: 25 });
  const [active, setActive] = useState(0);

  useEffect(() => {
    const unsub = activeRaw.on("change", (v) => {
      setActive(Math.floor(Math.max(0, Math.min(v, PHILOSOPHY_CARDS.length - 1))));
    });
    return unsub;
  }, [activeRaw]);

  return (
    <section ref={containerRef} className="relative" style={{ height: `${PHILOSOPHY_CARDS.length * 100}vh` }}>
      {/* ambient */}
      <div className="sticky top-0 h-screen">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-[10%] left-[10%] w-[600px] h-[600px] rounded-full bg-cyan-500/[0.02] blur-[150px]" />
          <div className="absolute bottom-[10%] right-[10%] w-[500px] h-[500px] rounded-full bg-violet-500/[0.02] blur-[130px]" />
        </div>
        <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: "radial-gradient(circle, rgba(255,255,255,0.012) 1px, transparent 1px)", backgroundSize: "24px 24px" }} />

        <div className="mx-auto max-w-7xl px-6 lg:px-8 h-full flex items-center">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 w-full items-center">

            {/* ── Left: Sticky title + progress ── */}
            <div className="flex flex-col">
              <SectionLabel text="Design Philosophy" />
              <h2 className="text-4xl md:text-5xl lg:text-[3.2rem] font-bold tracking-tight leading-[1.15] mt-4">
                <span className="text-[#b0b0b8]">从第一行代码</span>
                <br /><span className="text-[#d0d0d6]">就围绕的</span>
                <br />
                <span className="bg-gradient-to-r from-[#e8e8ed] via-[#f5f5f7] to-[#c8c8d0] bg-clip-text text-transparent">五个核心原则</span>
              </h2>

              {/* vertical progress steps */}
              <div className="mt-12 flex flex-col gap-1">
                {PHILOSOPHY_CARDS.map((card, i) => {
                  const isActive = active === i;
                  const s = ACCENT_STYLES[card.accent];
                  return (
                    <motion.div key={i}
                      className={`flex items-center gap-4 rounded-xl px-4 py-3 transition-all duration-500 cursor-default ${
                        isActive ? "bg-white/[0.03]" : ""
                      }`}
                      animate={{ opacity: isActive ? 1 : 0.35 }}
                    >
                      <div className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-mono font-bold transition-colors duration-500 ${
                        isActive ? `${s.bg}/20 ${s.text}` : "bg-white/[0.03] text-white/20"
                      }`}>
                        {card.num}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-semibold transition-colors duration-500 ${isActive ? "text-white" : "text-white/25"}`}>
                          {card.title}
                        </div>
                      </div>
                      <motion.div
                        className={`h-0.5 rounded-full ${s.bg}`}
                        animate={{ width: isActive ? 48 : 0, opacity: isActive ? 0.6 : 0 }}
                        transition={{ duration: 0.5 }}
                      />
                    </motion.div>
                  );
                })}
              </div>
            </div>

            {/* ── Right: Direct visual render ── */}
            <div className="relative min-h-[520px] flex flex-col justify-center">
              {(() => {
                const card = PHILOSOPHY_CARDS[active];
                const Visual = VISUAL_MAP[card.visual];
                const s = ACCENT_STYLES[card.accent];
                return (
                  <motion.div
                    key={active}
                    className="flex flex-col"
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <div className="mb-8">
                      <div className="flex items-center gap-3 mb-3">
                        <span className={`text-xs font-mono ${s.text} tracking-wider`}>{card.num}</span>
                        <div className={`h-px w-16 bg-gradient-to-r ${s.line} to-transparent`} />
                      </div>
                      <h3 className="text-3xl lg:text-4xl font-bold text-[#e8e8ed]">{card.title}</h3>
                      <p className="text-[#6a6a78] text-xs tracking-wide uppercase mt-2">{card.subtitle}</p>
                      <p className="text-[15px] leading-relaxed text-[#8a8a98] mt-4 max-w-lg">{card.desc}</p>
                    </div>
                    <Visual />
                  </motion.div>
                );
              })()}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── 3. Conversational Workflow Demo — Typewriter + Charts ──────────────────

type StepKind = "user" | "agent" | "chart";
interface ChatStep {
  kind: StepKind;
  text?: string;
  tag?: string;
  chart?: "v1" | "v2";
  metrics?: { label: string; value: string; improved?: boolean }[];
}

const WORKFLOW_STEPS: ChatStep[] = [
  { kind: "user",  text: "帮我设计一个 BTC/USDT 的 EMA 交叉策略，1 小时级别" },
  { kind: "agent", text: "已生成策略配置：EMA(20) 上穿 EMA(50) 做多，下穿平仓。Symbol: BTCUSDT, Interval: 1h", tag: "strategy-draft" },
  { kind: "user",  text: "回测一下最近 90 天" },
  { kind: "agent", text: "回测完成，以下是收益曲线 ↓", tag: "backtest-run" },
  { kind: "chart", chart: "v1", metrics: [
    { label: "总收益", value: "+3.2%" },
    { label: "Sharpe", value: "0.41" },
    { label: "最大回撤", value: "-12.6%" },
    { label: "胜率", value: "38%" },
  ]},
  { kind: "agent", text: "收益偏低，回撤严重，假信号太多。建议加入 RSI 过滤条件。" },
  { kind: "user",  text: "好，加个 RSI > 40 的入场过滤" },
  { kind: "agent", text: "已更新策略并重新回测，新收益曲线 ↓", tag: "自主寻优" },
  { kind: "chart", chart: "v2", metrics: [
    { label: "总收益", value: "+18.7%", improved: true },
    { label: "Sharpe", value: "1.72", improved: true },
    { label: "最大回撤", value: "-5.1%", improved: true },
    { label: "胜率", value: "58%", improved: true },
  ]},
  { kind: "agent", text: "策略显著改善 ✓  建议部署到模拟盘持续验证。" },
];

const EQUITY_V1 = [0, 3, -1, 5, -2, 2, -4, 1, -6, -3, 2, -5, 0, -7, -2, 3, -4, 1, -3, 5, -1, 2, 4, 3.2];
const EQUITY_V2 = [0, 1, 2.5, 2, 4, 3.5, 6, 5.5, 8, 7.5, 10, 9.5, 12, 11.5, 13.5, 13, 15, 14.5, 16, 15.8, 17, 16.5, 18, 18.7];

function EquityCurve({ data, color, label }: { data: number[]; color: string; label: string }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 320, h = 100, pad = 6;
  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x},${y}`;
  });
  const linePath = `M${points.join(" L")}`;
  const areaPath = `${linePath} L${w - pad},${h - pad} L${pad},${h - pad} Z`;

  return (
    <div className="rounded-xl bg-black/40 border border-white/[0.06] p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-white/30 font-mono">{label}</span>
        <span className="text-xs font-mono font-bold" style={{ color }}>{data[data.length - 1] > 0 ? "+" : ""}{data[data.length - 1]}%</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto">
        <defs>
          <linearGradient id={`eq-${label}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.2" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#eq-${label})`} />
        <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <animate attributeName="stroke-dasharray" from={`0 ${w * 3}`} to={`${w * 3} 0`} dur="1.5s" fill="freeze" />
        </path>
      </svg>
    </div>
  );
}

function TypewriterText({ text, onDone }: { text: string; onDone: () => void }) {
  const [display, setDisplay] = useState("");
  const idx = useRef(0);
  useEffect(() => {
    idx.current = 0; setDisplay("");
    const t = setInterval(() => {
      idx.current++;
      if (idx.current >= text.length) { setDisplay(text); clearInterval(t); onDone(); return; }
      setDisplay(text.slice(0, idx.current));
    }, 25);
    return () => clearInterval(t);
  }, [text, onDone]);
  return (
    <span>
      {display}
      {display.length < text.length && <span className="inline-block w-[5px] h-[12px] bg-cyan-400/70 ml-0.5 animate-pulse" />}
    </span>
  );
}

function WorkflowChat() {
  const [step, setStep] = useState(0);
  const [typing, setTyping] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const advance = useCallback(() => {
    setTyping(false);
    setTimeout(() => {
      setStep(s => {
        const next = s + 1;
        if (next >= WORKFLOW_STEPS.length) return s;
        setTyping(true);
        return next;
      });
    }, 600);
  }, []);

  useEffect(() => {
    const current = WORKFLOW_STEPS[step];
    if (!current) return;
    if (current.kind === "chart") {
      const t = setTimeout(advance, 2200);
      return () => clearTimeout(t);
    }
    if (current.kind === "user") {
      // user messages auto-advance after typing finishes (handled by TypewriterText onDone)
    }
  }, [step, advance]);

  useEffect(() => {
    if (step >= WORKFLOW_STEPS.length - 1 && !typing) {
      const t = setTimeout(() => { setStep(0); setTyping(true); }, 4000);
      return () => clearTimeout(t);
    }
  }, [step, typing]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [step]);

  return (
    <div className="relative rounded-2xl border border-white/[0.06] bg-[#0a0a10]/90 backdrop-blur-xl shadow-[0_0_80px_rgba(34,211,238,0.04)]">
      {/* title bar */}
      <div className="flex items-center gap-2.5 px-6 py-4 border-b border-white/[0.05]">
        <div className="flex gap-2">
          <span className="size-[11px] rounded-full bg-[#ff5f57]" />
          <span className="size-[11px] rounded-full bg-[#febc2e]" />
          <span className="size-[11px] rounded-full bg-[#28c840]" />
        </div>
        <span className="ml-2 text-xs text-white/20 font-mono">PnLClaw Agent</span>
      </div>

      {/* chat body */}
      <div ref={scrollRef} className="p-6 space-y-4 max-h-[580px] overflow-y-auto hover-scrollbar">
        {WORKFLOW_STEPS.slice(0, step + 1).map((s, i) => {
          const isLast = i === step;

          if (s.kind === "user") {
            return (
              <motion.div key={i} className="flex justify-end"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
                <div className="max-w-[80%] rounded-2xl rounded-br-md px-5 py-3 text-[15px] leading-relaxed bg-cyan-500/12 border border-cyan-500/15 text-white/75">
                  {isLast && typing ? <TypewriterText text={s.text!} onDone={advance} /> : s.text}
                </div>
              </motion.div>
            );
          }

          if (s.kind === "agent") {
            return (
              <motion.div key={i} className="flex justify-start"
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
                <div className="max-w-[85%] rounded-2xl rounded-bl-md px-5 py-3 text-[15px] leading-relaxed bg-white/[0.03] border border-white/[0.06] text-white/55">
                  {s.tag && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/12 border border-cyan-500/20 px-2.5 py-1 text-xs text-cyan-300/80 mb-2 mr-1">
                      <Sparkles className="size-3" />{s.tag}
                    </span>
                  )}
                  {isLast && typing ? <TypewriterText text={s.text!} onDone={advance} /> : <span>{s.text}</span>}
                </div>
              </motion.div>
            );
          }

          if (s.kind === "chart") {
            return (
              <motion.div key={i} className="px-1"
                initial={{ opacity: 0, y: 16, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
                <EquityCurve
                  data={s.chart === "v1" ? EQUITY_V1 : EQUITY_V2}
                  color={s.chart === "v1" ? "rgb(34,211,238)" : "rgb(52,211,153)"}
                  label={s.chart === "v1" ? "EMA Cross — 90d Backtest" : "EMA Cross + RSI Filter — 90d Backtest"}
                />
                {s.metrics && (
                  <div className="grid grid-cols-4 gap-3 mt-3">
                    {s.metrics.map(m => (
                      <div key={m.label} className="rounded-lg bg-white/[0.02] border border-white/[0.05] px-3 py-2 text-center">
                        <div className="text-[11px] text-white/25 mb-0.5">{m.label}</div>
                        <div className={`text-sm font-mono font-bold ${m.improved ? "text-emerald-400" : "text-white/60"}`}>{m.value}</div>
                      </div>
                    ))}
                  </div>
                )}
              </motion.div>
            );
          }
          return null;
        })}
      </div>
    </div>
  );
}

export function WorkflowDemo() {
  return (
    <section className="relative py-36 lg:py-40 overflow-hidden">
      <div className="absolute inset-0"
        style={{ backgroundImage: "linear-gradient(rgba(34,211,238,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.02) 1px, transparent 1px)", backgroundSize: "80px 80px" }}
      />
      <div className="mx-auto max-w-[1400px] px-8 lg:px-12 relative z-10">
        <div className="grid lg:grid-cols-2 gap-16 lg:gap-20 items-start">
          <Reveal>
            <div className="lg:sticky lg:top-40">
              <SectionLabel text="Workflow" />
              <h2 className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1]">
                <span className="text-[#b0b0b8]">一次对话</span>
                <br />
                <span className="bg-gradient-to-r from-[#e8e8ed] via-[#f5f5f7] to-[#c8c8d0] bg-clip-text text-transparent">
                  完成策略闭环。
                </span>
              </h2>
              <p className="mt-8 text-xl text-[#8a8a98] leading-relaxed">
                从策略构思到回测验证到模拟部署，全部在一段自然语言对话中完成。Agent 自主分析结果并建议优化方向，在多轮对话中持续迭代。
              </p>
              <div className="mt-12 grid grid-cols-2 gap-5">
                {[
                  { icon: Brain, label: "完整上下文记忆" },
                  { icon: Target, label: "意图连续性" },
                  { icon: Workflow, label: "渐进式优化" },
                  { icon: Zap, label: "智能上下文压缩" },
                ].map(({ icon: Icon, label }) => (
                  <div key={label} className="flex items-center gap-3 text-base text-[#7a7a88]">
                    <Icon className="size-5 text-cyan-400/60 shrink-0" />
                    {label}
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

          <Reveal delay={0.1}>
            <WorkflowChat />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ─── 4. Why PnLClaw — Constellation Hub ─────────────────────────────────────

const HUB_FEATURES = [
  {
    icon: MessageSquare, title: "对话即策略", desc: "自然语言 → 可执行 YAML", accent: "#22d3ee",
    detail: "用自然语言描述交易想法，Agent 自动生成可执行的 YAML 策略并运行回测。不需要 Python / Pine Script 经验。",
  },
  {
    icon: Brain, title: "长时记忆", desc: "完整上下文，永不丢失", accent: "#a78bfa",
    detail: "Agent 完整记忆整段对话。说「回测上面那个策略」，它自动定位并继续操作，上下文永不丢失。",
  },
  {
    icon: Workflow, title: "全闭环工作流", desc: "设计→回测→优化→部署", accent: "#34d399",
    detail: "设计 → 校验 → 回测 → 分析 → 优化 → 部署，全部在一次对话中完成。Agent 主动建议优化方向。",
  },
  {
    icon: Layers, title: "8 个内置技能", desc: "即装即用量化工具链", accent: "#fbbf24",
    detail: "策略起草、代码生成、回测解读、市场分析、PnL 归因、风险报告、指标教学、交易所配置。",
  },
  {
    icon: Globe2, title: "预测市场原生", desc: "Polymarket CLOB 接入", accent: "#fb7185",
    detail: "业内罕见的 Polymarket CLOB 原生接入，实时盘口与隐含概率分析。同时支持 Binance / OKX。",
  },
  {
    icon: Shield, title: "极客级隐私", desc: "Security Gateway 守护", accent: "#2dd4bf",
    detail: "无云端依赖、无订阅费。密钥通过 Security Gateway 脱敏，绝不进入提示词或日志。",
  },
];

// cardX/Y = card anchor (left cards: right edge center, right cards: left edge center)
// lineX/Y = where the line actually connects (the corner facing the logo)
const NODES = [
  { cardX: 8,  cardY: 14, lineX: 14, lineY: 19, side: "left" as const },   // top-left
  { cardX: 2,  cardY: 46, lineX: 8,  lineY: 46, side: "left" as const },   // mid-left
  { cardX: 8,  cardY: 78, lineX: 14, lineY: 83, side: "left" as const },   // bottom-left
  { cardX: 86, cardY: 14, lineX: 86, lineY: 19, side: "right" as const },  // top-right
  { cardX: 92, cardY: 46, lineX: 92, lineY: 46, side: "right" as const },  // mid-right
  { cardX: 86, cardY: 78, lineX: 86, lineY: 83, side: "right" as const },  // bottom-right
];

function PnLClawLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" className={className} fill="currentColor">
      <path d="M268.703,730.897C251.785,735.45,235.16,738.271,218.012,734.749C195.676,730.161,180.803,716.426,170.867,696.606C162.435,679.787,159.228,661.614,157.784,643.116C154.322,598.778,161.729,555.736,175.846,513.995C204.417,429.517,255.378,360.868,325.658,306.281C383.929,261.022,449.698,231.926,521.429,216.122C557.907,208.085,594.941,203.458,632.408,204.829C681.59,206.628,728.867,216.306,772.261,240.809C773.95,241.762,775.987,242.31,777.215,244.622C774.832,245.936,772.357,245.296,770.042,245.122C714.447,240.941,661.843,251.87,612.857,278.165C527.339,324.071,474.888,395.891,450.419,489.025C443.932,513.718,440.122,538.831,439.176,564.364C438.935,570.852,438.634,577.339,438.232,583.819C437.548,594.86,432.86,604.341,426.422,613.051C395.478,654.914,358.074,689.442,311.651,713.627C298.038,720.718,283.915,726.639,268.703,730.897Z" />
      <path d="M775.761,676.754C704.972,746.936,620.918,791.787,523.773,811.965C490.767,818.821,457.261,821.982,423.52,820.999C388.989,819.993,354.788,816.348,321.755,805.355C313.792,802.705,306.27,799.144,299.722,793.868C287.667,784.155,287.383,768.183,299.003,757.909C303.781,753.684,309.318,750.577,315.024,747.803C367.481,722.293,410.872,685.643,445.04,638.69C459.733,618.499,478.149,612.808,501.389,614.858C523.145,616.777,544.938,615.953,566.719,613.97C600.187,610.923,632.894,604.136,664.705,593.589C727.79,572.673,785.306,541.991,832.717,494.452C852.375,474.74,868.662,452.484,881.013,427.448C881.526,426.408,882.129,425.409,882.751,424.43C882.899,424.198,883.294,424.123,883.656,423.933C885.303,425.662,885.144,427.883,885.233,429.98C886.146,451.38,884.195,472.522,879.84,493.495C868.196,549.562,841.839,598.323,806.212,642.524C796.69,654.337,786.439,665.499,775.761,676.754Z" />
    </svg>
  );
}

function FlowLine({ x1, y1, color, index }: {
  x1: number; y1: number; color: string; index: number;
}) {
  const cx = 50, cy = 50;
  const dx = cx - x1, dy = cy - y1;
  const lenPx = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);
  const dur1 = 2.8 + index * 0.4;
  const dur2 = 3.5 + index * 0.3;

  return (
    <>
      {/* static track line */}
      <div
        className="absolute pointer-events-none origin-left"
        style={{
          left: `${x1}%`, top: `${y1}%`,
          width: `${lenPx}%`, height: "1px",
          transform: `rotate(${angle}deg)`,
          background: `linear-gradient(90deg, ${color}20, ${color}08 50%, ${color}20)`,
        }}
      />
      {/* particle 1 */}
      <motion.div
        className="absolute rounded-full pointer-events-none z-[1]"
        style={{ width: 6, height: 6, background: color, boxShadow: `0 0 8px ${color}` }}
        animate={{
          left: [`${x1}%`, `${cx}%`],
          top: [`${y1}%`, `${cy}%`],
          opacity: [0, 0.9, 0.9, 0],
        }}
        transition={{ duration: dur1, repeat: Infinity, ease: "linear" }}
      />
      {/* particle 2 — offset start */}
      <motion.div
        className="absolute rounded-full pointer-events-none z-[1]"
        style={{ width: 4, height: 4, background: color, boxShadow: `0 0 6px ${color}` }}
        animate={{
          left: [`${x1}%`, `${cx}%`],
          top: [`${y1}%`, `${cy}%`],
          opacity: [0, 0.6, 0.6, 0],
        }}
        transition={{ duration: dur1, repeat: Infinity, ease: "linear", delay: dur1 * 0.45 }}
      />
      {/* particle 3 */}
      <motion.div
        className="absolute rounded-full pointer-events-none z-[1]"
        style={{ width: 3, height: 3, background: color }}
        animate={{
          left: [`${x1}%`, `${cx}%`],
          top: [`${y1}%`, `${cy}%`],
          opacity: [0, 0.4, 0.4, 0],
        }}
        transition={{ duration: dur2, repeat: Infinity, ease: "linear", delay: dur2 * 0.3 }}
      />
    </>
  );
}

function FeatureNode({ feature, node, index, inView }: {
  feature: typeof HUB_FEATURES[number];
  node: typeof NODES[number];
  index: number;
  inView: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const isLeft = node.side === "left";
  const isMid = index === 1 || index === 4;
  const yTranslate = isMid ? "-50%" : "-100%";

  const floatAmplitude = [8, 6, 10, 7, 9, 5][index] ?? 8;
  const floatDuration = [3.8, 4.2, 3.5, 4.6, 3.2, 4.0][index] ?? 4;

  return (
    <motion.div
      className={`absolute z-10 cursor-default ${isLeft ? "pr-4" : "pl-4"}`}
      style={{
        left: `${node.cardX}%`,
        top: `${node.cardY}%`,
        transform: `translate(${isLeft ? "-100%" : "0%"}, ${yTranslate})`,
      }}
      initial={{ opacity: 0, x: isLeft ? -40 : 40 }}
      animate={inView ? {
        opacity: 1,
        x: 0,
        y: [0, -floatAmplitude, 0, floatAmplitude * 0.5, 0],
      } : {}}
      transition={{
        opacity: { duration: 0.7, delay: 0.3 + index * 0.1, ease: [0.22, 1, 0.36, 1] },
        x: { duration: 0.7, delay: 0.3 + index * 0.1, ease: [0.22, 1, 0.36, 1] },
        y: { duration: floatDuration, delay: 0.3 + index * 0.1 + 0.7, ease: "easeInOut", repeat: Infinity, repeatType: "loop" },
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className={`flex items-start gap-4 ${isLeft ? "flex-row" : "flex-row-reverse"}`}>
        <motion.div
          className="relative shrink-0 size-12 md:size-14 rounded-xl flex items-center justify-center border transition-colors duration-300"
          style={{
            background: hovered ? `${feature.accent}18` : `${feature.accent}08`,
            borderColor: hovered ? `${feature.accent}40` : "rgba(255,255,255,0.06)",
          }}
          animate={{ scale: hovered ? 1.08 : 1 }}
          transition={{ duration: 0.25 }}
        >
          <feature.icon className="size-5 md:size-6" style={{ color: feature.accent }} />
        </motion.div>
        <div className={`${isLeft ? "text-left" : "text-right"} min-w-0`}>
          <div className="text-base md:text-lg font-semibold text-[#d0d0d8] whitespace-nowrap transition-colors duration-300"
            style={{ color: hovered ? "#ffffff" : undefined }}
          >
            {feature.title}
          </div>
          <div className="text-xs md:text-sm text-white/30 whitespace-nowrap transition-colors duration-300"
            style={{ color: hovered ? `${feature.accent}90` : undefined }}
          >
            {feature.desc}
          </div>
          <AnimatePresence>
            {hovered && (
              <motion.p
                className={`mt-2 text-sm leading-relaxed text-white/50 max-w-[280px] ${isLeft ? "" : "ml-auto"}`}
                initial={{ opacity: 0, height: 0, y: -4 }}
                animate={{ opacity: 1, height: "auto", y: 0 }}
                exit={{ opacity: 0, height: 0, y: -4 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              >
                {feature.detail}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

export function WhyPnLClaw() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const inView = useInView(sectionRef, { once: true, margin: "-100px" });

  return (
    <section ref={sectionRef} className="relative min-h-screen flex flex-col items-center justify-center py-20 lg:py-0 overflow-hidden">
      <div className="absolute inset-0 bg-[#08080c]" />
      <div className="absolute inset-0" style={{ backgroundImage: "radial-gradient(circle at 50% 50%, rgba(255,255,255,0.03) 0%, transparent 50%)" }} />
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />
      <div className="absolute bottom-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />

      <div className="relative z-10 w-full max-w-[1400px] mx-auto px-8 lg:px-12">
        <Reveal className="text-center mb-8 lg:mb-4">
          <SectionLabel text="Why PnLClaw" />
          <h2 className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.1]">
            <span className="text-[#b0b0b8]">为什么选择</span>
            <span className="bg-gradient-to-r from-[#e8e8ed] via-[#f5f5f7] to-[#c8c8d0] bg-clip-text text-transparent">
              {" "}PnLClaw
            </span>
          </h2>
        </Reveal>

        <div className="relative w-full" style={{ aspectRatio: "16/9", maxHeight: "70vh" }}>
          {/* flow lines + particles — use lineX/lineY for precise corner connections */}
          {NODES.map((n, i) => (
            <FlowLine key={i} x1={n.lineX} y1={n.lineY} color={HUB_FEATURES[i].accent} index={i} />
          ))}

          {/* center logo */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
            <motion.div
              className="absolute -inset-12 rounded-full"
              style={{ background: "radial-gradient(circle, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.02) 40%, transparent 70%)" }}
              animate={{ scale: [1, 1.2, 1], opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            />
            <motion.div
              className="absolute -inset-20 rounded-full"
              style={{ background: "radial-gradient(circle, rgba(255,255,255,0.04) 0%, transparent 60%)" }}
              animate={{ scale: [1, 1.25, 1], opacity: [0.3, 0.6, 0.3] }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
            />
            <motion.div
              className="absolute -inset-32 rounded-full"
              style={{ background: "radial-gradient(circle, rgba(255,255,255,0.02) 0%, transparent 50%)" }}
              animate={{ scale: [1, 1.15, 1], opacity: [0.15, 0.4, 0.15] }}
              transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
            />
            <motion.div
              className="relative size-32 md:size-40 lg:size-48 rounded-full border border-white/[0.12] flex items-center justify-center"
              style={{ background: "radial-gradient(circle at 40% 40%, rgba(255,255,255,0.06), rgba(10,10,18,0.95))" }}
              initial={{ scale: 0, opacity: 0 }}
              animate={inView ? { scale: 1, opacity: 1 } : {}}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            >
              <PnLClawLogo className="size-16 md:size-20 lg:size-24 text-white drop-shadow-[0_0_20px_rgba(255,255,255,0.3)]" />
            </motion.div>
          </div>

          {/* 6 feature nodes */}
          {HUB_FEATURES.map((f, i) => (
            <FeatureNode key={f.title} feature={f} node={NODES[i]} index={i} inView={inView} />
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── 5. Skills System ────────────────────────────────────────────────────────

const SKILLS = [
  { id: "strategy-draft", name: "Strategy Draft", desc: "引导式对话逐步起草并验证 YAML 策略", icon: MessageSquare, tools: ["strategy_validate", "strategy_compile"] },
  { id: "strategy-coder", name: "Strategy Coder", desc: "自然语言直接转换为可执行策略 YAML", icon: Terminal, tools: ["strategy_compile", "code_gen"] },
  { id: "backtest-explain", name: "Backtest Explain", desc: "通俗解释回测指标，指出风险和优化方向", icon: BarChart3, tools: ["backtest_run", "metrics_calc"] },
  { id: "market-analysis", name: "Market Analysis", desc: "综合 Ticker、K 线和盘口数据多周期分析", icon: LineChart, tools: ["market_fetch", "indicator_calc"] },
  { id: "pnl-explain", name: "PnL Explain", desc: "拆解模拟账户的 PnL 构成与归因", icon: TrendingUp, tools: ["paper_state", "pnl_decompose"] },
  { id: "risk-report", name: "Risk Report", desc: "汇总持仓风险敞口，评估整体风险暴露", icon: AlertTriangle, tools: ["position_fetch", "risk_evaluate"] },
  { id: "indicator-guide", name: "Indicator Guide", desc: "解释技术指标原理、参数含义与适用场景", icon: BookOpen, tools: ["indicator_list", "indicator_explain"] },
  { id: "exchange-setup", name: "Exchange Setup", desc: "引导完成交易所 API 凭证的安全配置", icon: Settings, tools: ["secret_store", "connection_test"] },
];

export function SkillsSystem() {
  const [active, setActive] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const sectionInView = useInView(sectionRef, { amount: 0.3 });
  const skill = SKILLS[active];
  const SkillIcon = skill.icon;

  useEffect(() => {
    const container = scrollRef.current;
    const el = container?.children[active] as HTMLElement | undefined;
    if (!container || !el) return;
    const left = el.offsetLeft - container.offsetWidth / 2 + el.offsetWidth / 2;
    container.scrollTo({ left, behavior: "smooth" });
  }, [active]);

  useEffect(() => {
    if (!sectionInView) return;
    const t = setInterval(() => setActive(p => (p + 1) % SKILLS.length), 1000);
    return () => clearInterval(t);
  }, [sectionInView]);

  return (
    <section ref={sectionRef} className="relative py-36 lg:py-40 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0a] via-[#0a0a10] to-[#0a0a0a]" />
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />

      <div className="mx-auto max-w-[1400px] px-8 lg:px-12 relative z-10">
        {/* title */}
        <Reveal className="text-center mb-16">
          <SectionLabel text="Skills" />
          <h2 className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1]">
            <span className="bg-gradient-to-r from-[#f0f0f5] to-[#d0d0d8] bg-clip-text text-transparent">8</span>
            <span className="text-[#b0b0b8]"> 个内置</span>
            <br />
            <span className="bg-gradient-to-r from-[#e8e8ed] via-[#f5f5f7] to-[#c8c8d0] bg-clip-text text-transparent">
              量化技能
            </span>
          </h2>
          <p className="mt-6 text-lg text-white/30 max-w-xl mx-auto">
            每个 Skill 是一套专精工作流。支持多源分层注册表与 MCP 协议扩展。
          </p>
        </Reveal>

        {/* horizontal skill tabs — scrollable */}
        <div className="relative mb-12">
          <div ref={scrollRef} className="flex gap-3 overflow-x-auto pb-4 scrollbar-hide snap-x snap-mandatory">
            {SKILLS.map(({ id, name, icon: Icon }, i) => (
              <motion.button
                key={id}
                className={`group relative flex items-center gap-3 shrink-0 snap-center rounded-2xl px-6 py-4 text-left transition-all duration-300 border ${
                  active === i
                    ? "bg-white/[0.08] border-white/20 text-white"
                    : "bg-white/[0.02] border-white/[0.06] text-white/40 hover:text-white/60 hover:bg-white/[0.04]"
                }`}
                onClick={() => setActive(i)}
                whileTap={{ scale: 0.97 }}
              >
                <div className={`size-10 rounded-lg flex items-center justify-center transition-colors duration-300 ${
                  active === i ? "bg-white/[0.12]" : "bg-white/[0.04]"
                }`}>
                  <Icon className={`size-4.5 transition-colors duration-300 ${active === i ? "text-white/80" : "text-white/30"}`} />
                </div>
                <span className="text-sm font-medium whitespace-nowrap">{name}</span>
                {active === i && (
                  <motion.div
                    className="absolute bottom-0 left-6 right-6 h-0.5 bg-gradient-to-r from-white/60 to-white/30 rounded-full"
                    layoutId="skill-indicator"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
              </motion.button>
            ))}
          </div>
          {/* fade edges */}
          <div className="absolute left-0 top-0 bottom-4 w-12 bg-gradient-to-r from-[#0a0a0a] to-transparent pointer-events-none z-10" />
          <div className="absolute right-0 top-0 bottom-4 w-12 bg-gradient-to-l from-[#0a0a0a] to-transparent pointer-events-none z-10" />
        </div>

        {/* detail panel — slides in on switch */}
        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            className="rounded-2xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-sm overflow-hidden"
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -40 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="grid lg:grid-cols-2 divide-x divide-white/[0.06]">
              {/* left: info */}
              <div className="p-10">
                <div className="flex items-center gap-4 mb-8">
                  <div className="size-14 rounded-xl bg-white/[0.06] border border-white/[0.12] flex items-center justify-center">
                    <SkillIcon className="size-6 text-white/70" />
                  </div>
                  <div>
                    <h3 className="text-2xl font-bold text-white">{skill.name}</h3>
                    <span className="text-sm font-mono text-white/25">{skill.id}</span>
                  </div>
                </div>
                <p className="text-base text-white/45 leading-relaxed">{skill.desc}</p>
                <div className="mt-8 flex flex-wrap gap-3">
                  {[
                    { label: "工具依赖校验", icon: Check },
                    { label: "可覆盖/禁用", icon: Check },
                    { label: "MCP 扩展", icon: Check },
                  ].map(t => (
                    <span key={t.label} className="inline-flex items-center gap-1.5 text-sm text-white/30 bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-1.5">
                      <t.icon className="size-3.5 text-emerald-400" />{t.label}
                    </span>
                  ))}
                </div>
              </div>
              {/* right: code preview */}
              <div className="p-10 bg-black/30">
                <div className="flex items-center gap-2 mb-6">
                  <div className="flex gap-1.5">
                    <span className="size-2.5 rounded-full bg-[#ff5f57]" />
                    <span className="size-2.5 rounded-full bg-[#febc2e]" />
                    <span className="size-2.5 rounded-full bg-[#28c840]" />
                  </div>
                  <span className="text-xs text-white/15 font-mono ml-2">SKILL.md</span>
                </div>
                <div className="font-mono text-sm leading-loose">
                  <div className="text-white/15"># skill config</div>
                  <div><span className="text-white/60">name</span><span className="text-white/20">:</span> <span className="text-cyan-300">{skill.id}</span></div>
                  <div><span className="text-white/60">requires_tools</span><span className="text-white/20">:</span></div>
                  {skill.tools.map(t => (
                    <div key={t} className="text-white/30 pl-4">- {t}</div>
                  ))}
                  <div><span className="text-white/60">priority</span><span className="text-white/20">:</span> <span className="text-amber-300">bundled</span></div>
                  <div><span className="text-white/60">mcp_compatible</span><span className="text-white/20">:</span> <span className="text-emerald-300">true</span></div>
                </div>
              </div>
            </div>
          </motion.div>
        </AnimatePresence>

        {/* progress dots */}
        <div className="flex justify-center gap-2 mt-8">
          {SKILLS.map((_, i) => (
            <button key={i} onClick={() => setActive(i)}
              className={`h-1 rounded-full transition-all duration-300 ${active === i ? "w-8 bg-white/60" : "w-2 bg-white/15 hover:bg-white/25"}`}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── 6. Architecture — Tree Flowchart ────────────────────────────────────────

function TreeNode({ name, sub, accent, delay = 0 }: {
  name: string; sub: string; accent: string; delay?: number;
}) {
  return (
    <Reveal delay={delay}>
      <motion.div
        className="relative rounded-xl border px-5 py-3.5 backdrop-blur-sm cursor-default text-center transition-all duration-300 hover:scale-[1.04]"
        style={{ borderColor: `${accent}35`, background: `${accent}0a` }}
        whileHover={{ y: -3 }}
      >
        <div className="text-sm font-semibold whitespace-nowrap" style={{ color: accent }}>{name}</div>
        <div className="text-[11px] mt-0.5 text-white/30 whitespace-nowrap">{sub}</div>
      </motion.div>
    </Reveal>
  );
}

function VLine({ h = 32, accent = "rgba(255,255,255,0.1)", delay = 0 }: { h?: number; accent?: string; delay?: number }) {
  return (
    <Reveal delay={delay}>
      <div className="flex justify-center">
        <div style={{ width: 1, height: h, background: accent }} />
      </div>
    </Reveal>
  );
}

function HBranch({ count, accent = "rgba(255,255,255,0.08)", delay = 0 }: { count: number; accent?: string; delay?: number }) {
  return (
    <Reveal delay={delay}>
      <div className="relative flex justify-between mx-auto" style={{ width: `${Math.min(100, count * 20)}%` }}>
        <div className="absolute top-0 left-[calc(50%/(count))] right-[calc(50%/(count))] h-px" style={{ background: accent, left: `${100 / (count * 2)}%`, right: `${100 / (count * 2)}%` }} />
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} className="flex justify-center" style={{ width: `${100 / count}%` }}>
            <div style={{ width: 1, height: 20, background: accent }} />
          </div>
        ))}
      </div>
    </Reveal>
  );
}

export function Architecture() {
  const W = "w-[1050px] max-w-[92vw]";
  return (
    <section className="relative py-36 lg:py-40 overflow-hidden">
      <div className="absolute inset-0 bg-[#08080c]" />
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(34,211,238,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.015) 1px, transparent 1px)", backgroundSize: "60px 60px" }} />
      <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />

      <div className="mx-auto max-w-[1200px] px-8 lg:px-12 relative z-10">
        <Reveal className="text-center mb-20">
          <SectionLabel text="Architecture" />
          <h2 className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1]">
            <span className="text-[#b0b0b8]">模块化</span>{" "}
            <span className="bg-gradient-to-r from-[#e8e8ed] via-[#f5f5f7] to-[#c8c8d0] bg-clip-text text-transparent">
              Monorepo
            </span>
          </h2>
          <p className="mt-6 text-lg text-white/30 max-w-xl mx-auto">
            16 个独立包，严格分离前端 UI、API 编排层以及领域驱动的核心业务模块。
          </p>
        </Reveal>

        <div className="flex flex-col items-center">

          {/* L0: User Interface */}
          <TreeNode name="Desktop UI" sub="Next.js 16 + Tauri 2" accent="#22d3ee" delay={0} />
          <VLine accent="rgba(34,211,238,0.2)" delay={0.04} />

          {/* L1: API Layer */}
          <TreeNode name="Local API" sub="FastAPI · :8080 · WebSocket" accent="#60a5fa" delay={0.06} />
          <VLine accent="rgba(96,165,250,0.2)" delay={0.1} />

          {/* Branch to L2: 6 core domain packages */}
          <Reveal delay={0.12}>
            <div className={`relative ${W}`}>
              <div className="absolute top-0 left-[8%] right-[8%] h-px bg-white/[0.08]" />
              <div className="flex justify-between px-[8%]">
                {[0,1,2,3,4,5].map(i => (
                  <div key={i} className="flex justify-center" style={{ width: `${100/6}%` }}>
                    <div className="w-px h-5 bg-white/[0.08]" />
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

          {/* L2: Core domain packages (6 columns) */}
          <Reveal delay={0.14}>
            <div className={`grid grid-cols-6 gap-3 ${W}`}>
              <TreeNode name="Exchange SDK" sub="Binance · OKX · Polymarket" accent="#34d399" delay={0.16} />
              <TreeNode name="Strategy Engine" sub="YAML · Indicators · Validator" accent="#a78bfa" delay={0.18} />
              <TreeNode name="Agent Runtime" sub="ReAct · Tool Catalog" accent="#e879f9" delay={0.2} />
              <TreeNode name="Security Gateway" sub="Guardrails · Redaction" accent="#fb7185" delay={0.22} />
              <TreeNode name="LLM Adapter" sub="OpenAI · Ollama · Router" accent="#c084fc" delay={0.24} />
              <TreeNode name="Risk Engine" sub="Pre-trade · Rule-based" accent="#f472b6" delay={0.26} />
            </div>
          </Reveal>

          {/* Branch lines L2 → L3 (per column) */}
          <Reveal delay={0.28}>
            <div className={`grid grid-cols-6 gap-3 ${W}`}>
              {/* Exchange SDK → Market Data */}
              <div className="flex justify-center"><div className="w-px h-5 bg-emerald-500/20" /></div>
              {/* Strategy → Backtest + Paper */}
              <div className="relative">
                <div className="flex justify-center"><div className="w-px h-2 bg-violet-500/20" /></div>
                <div className="relative mx-2">
                  <div className="absolute top-0 left-[20%] right-[20%] h-px bg-violet-500/12" />
                  <div className="flex justify-between px-[20%]">
                    <div className="w-px h-3 bg-violet-500/12" />
                    <div className="w-px h-3 bg-violet-500/12" />
                  </div>
                </div>
              </div>
              {/* Agent → Skills + MCP */}
              <div className="relative">
                <div className="flex justify-center"><div className="w-px h-2 bg-fuchsia-500/20" /></div>
                <div className="relative mx-2">
                  <div className="absolute top-0 left-[20%] right-[20%] h-px bg-fuchsia-500/12" />
                  <div className="flex justify-between px-[20%]">
                    <div className="w-px h-3 bg-fuchsia-500/12" />
                    <div className="w-px h-3 bg-fuchsia-500/12" />
                  </div>
                </div>
              </div>
              <div />
              <div />
              <div />
            </div>
          </Reveal>

          {/* L3: Sub-packages */}
          <Reveal delay={0.3}>
            <div className={`grid grid-cols-6 gap-3 ${W}`}>
              <TreeNode name="Market Data" sub="L2 Cache · Event Bus" accent="#2dd4bf" delay={0.32} />
              <div className="grid grid-cols-2 gap-1.5">
                <TreeNode name="Backtest" sub="Event-driven" accent="#fbbf24" delay={0.34} />
                <TreeNode name="Paper" sub="L2 Fill · PnL" accent="#fb923c" delay={0.36} />
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <TreeNode name="Skills" sub="8 内置技能" accent="#d946ef" delay={0.38} />
                <TreeNode name="MCP" sub="协议扩展" accent="#c026d3" delay={0.4} />
              </div>
              <div />
              <div />
              <div />
            </div>
          </Reveal>

          {/* Connector to Foundation */}
          <Reveal delay={0.42}>
            <div className="flex justify-center my-5">
              <div className="flex flex-col items-center">
                <div className="w-px h-6 bg-white/[0.06]" />
                <div className="size-1.5 rounded-full bg-white/10" />
                <div className="w-px h-6 bg-white/[0.06]" />
              </div>
            </div>
          </Reveal>

          {/* L4: Foundation bar */}
          <Reveal delay={0.44}>
            <div className="flex items-center gap-4 rounded-2xl border border-white/[0.06] bg-white/[0.02] px-6 py-4">
              <span className="text-[10px] uppercase tracking-widest text-white/20 shrink-0">Foundation</span>
              <div className="h-6 w-px bg-white/[0.08]" />
              <div className="flex gap-3 flex-wrap">
                {[
                  { name: "Core", sub: "Config · Log · Utils", accent: "#a3a3a3" },
                  { name: "Shared Types", sub: "Pydantic Models", accent: "#818cf8" },
                  { name: "Storage", sub: "SQLite · Async", accent: "#94a3b8" },
                ].map(m => (
                  <div key={m.name} className="rounded-lg border px-4 py-2 text-center" style={{ borderColor: `${m.accent}25`, background: `${m.accent}08` }}>
                    <div className="text-xs font-semibold" style={{ color: m.accent }}>{m.name}</div>
                    <div className="text-[10px] text-white/25">{m.sub}</div>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

        </div>
      </div>
    </section>
  );
}

// ─── 7. Exchanges ────────────────────────────────────────────────────────────

const EXCHANGES = [
  { name: "Binance", ws: true, l2: true, kline: true, rest: true, note: "支持测试网" },
  { name: "OKX",     ws: true, l2: true, kline: true, rest: true, note: "支持模拟盘" },
  { name: "Polymarket", ws: true, l2: true, kline: false, rest: true, note: "CLOB 预测市场" },
];

export function Exchanges() {
  return (
    <section className="py-32">
      <div className="mx-auto max-w-5xl px-6 lg:px-8">
        <Reveal className="text-center mb-16">
          <SectionLabel text="Exchanges" />
          <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white">
            统一事件模型，
            <span className="bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">多交易所</span>
          </h2>
          <p className="mt-4 text-white/40">原生 WebSocket · L2 盘口 · 归一化输出</p>
        </Reveal>

        <Reveal delay={0.1}>
          <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-sm">
            <div className="grid grid-cols-6 gap-4 px-6 py-3.5 border-b border-white/[0.06] text-[11px] font-semibold uppercase tracking-widest text-white/30">
              <span>交易所</span><span className="text-center">WS</span><span className="text-center">L2</span><span className="text-center">Kline</span><span className="text-center">REST</span><span>备注</span>
            </div>
            {EXCHANGES.map(({ name, ws, l2, kline, rest, note }, i) => (
              <motion.div key={name}
                className="grid grid-cols-6 gap-4 items-center px-6 py-4 border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02] transition-colors"
                initial={{ opacity: 0, x: -16 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08 }}
              >
                <span className="text-sm font-semibold text-white">{name}</span>
                {[ws, l2, kline, rest].map((v, j) => (
                  <span key={j} className="text-center">
                    {v ? <Check className="size-4 text-emerald-400 mx-auto" /> : <span className="text-white/15">—</span>}
                  </span>
                ))}
                <span className="text-xs text-white/35">{note}</span>
              </motion.div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─── 8. Stats ────────────────────────────────────────────────────────────────

export function Stats() {
  const data = [
    { n: 14, suffix: "+", label: "独立模块包", desc: "模块化 Monorepo" },
    { n: 8,  suffix: "",  label: "内置技能", desc: "量化专精 Skills" },
    { n: 3,  suffix: "",  label: "交易所原生接入", desc: "Binance · OKX · Polymarket" },
    { n: 100, suffix: "%", label: "本地运行", desc: "数据不离开你的机器" },
  ];
  return (
    <section className="py-24 border-y border-white/[0.04]">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
          {data.map(({ n, suffix, label, desc }, i) => (
            <Reveal key={label} delay={i * 0.07}>
              <div className="relative overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8 text-center group hover:border-cyan-500/20 transition-colors">
                <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/[0.04] to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                <div className="relative text-5xl font-black text-white">
                  <Counter to={n} suffix={suffix} />
                </div>
                <div className="relative mt-3 text-sm font-semibold text-white/70">{label}</div>
                <div className="relative mt-1 text-xs text-white/30">{desc}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── 9. Roadmap ──────────────────────────────────────────────────────────────

const ROADMAP = [
  {
    phase: "v0.1 ✓",
    title: "基础闭环",
    items: ["原生 WebSocket 适配器", "统一 L2 事件模型", "事件驱动回测引擎", "ReAct Agent + 8 技能", "桌面应用"],
    done: true,
  },
  {
    phase: "Next",
    title: "加密市场深化",
    items: ["永续合约支持", "链上数据集成", "清算级联监控", "CEX-DEX 跨市场套利"],
    done: false,
  },
  {
    phase: "Next",
    title: "预测市场专项",
    items: ["Polymarket 深度集成", "预测市场做市策略", "跨平台套利", "新闻驱动概率估算"],
    done: false,
  },
  {
    phase: "Future",
    title: "Agent 智能演进",
    items: ["参数自动寻优", "多 Agent 协作", "向量语义记忆", "自主研报生成"],
    done: false,
  },
];

export function Roadmap() {
  return (
    <section className="py-32">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <Reveal className="text-center mb-20">
          <SectionLabel text="Roadmap" />
          <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white">
            路线图
          </h2>
        </Reveal>

        <div className="relative">
          {/* vertical line */}
          <div className="absolute left-6 md:left-1/2 top-0 bottom-0 w-px bg-gradient-to-b from-cyan-500/30 via-violet-500/20 to-transparent" />

          <div className="space-y-12">
            {ROADMAP.map(({ phase, title, items, done }, i) => (
              <Reveal key={title} delay={i * 0.1}>
                <div className={`relative flex flex-col md:flex-row gap-8 ${i % 2 === 0 ? "" : "md:flex-row-reverse"}`}>
                  {/* dot */}
                  <div className="absolute left-6 md:left-1/2 -translate-x-1/2 z-10">
                    <div className={`size-4 rounded-full border-2 ${done ? "border-emerald-400 bg-emerald-400/30" : "border-cyan-500/50 bg-cyan-500/10"}`} />
                  </div>

                  <div className={`flex-1 pl-16 md:pl-0 ${i % 2 === 0 ? "md:pr-16 md:text-right" : "md:pl-16"}`}>
                    <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-[11px] font-semibold ${done ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25" : "bg-white/[0.04] text-white/40 border border-white/[0.08]"}`}>
                      {done && <Check className="size-3" />}{phase}
                    </span>
                    <h3 className="mt-3 text-xl font-bold text-white">{title}</h3>
                    <ul className={`mt-3 space-y-1.5 text-sm text-white/40 ${i % 2 === 0 ? "md:ml-auto" : ""}`}>
                      {items.map(item => (
                        <li key={item} className={`flex items-center gap-2 ${i % 2 === 0 ? "md:justify-end" : ""}`}>
                          <span className={`size-1 rounded-full shrink-0 ${done ? "bg-emerald-400" : "bg-white/20"}`} />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="hidden md:block flex-1" />
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── 10. CTA ──────────────────────────────────────────────────────────────────

export function CtaSection() {
  return (
    <section className="py-24 px-6">
      <Reveal>
        <div className="mx-auto max-w-5xl relative overflow-hidden rounded-[2rem] border border-cyan-500/15 bg-gradient-to-br from-cyan-950/40 via-[#0a0a0a] to-violet-950/30 p-12 md:p-16 text-center shadow-[0_0_80px_rgba(34,211,238,0.08)]">
          <div className="absolute inset-0 pointer-events-none"
            style={{ backgroundImage: "radial-gradient(circle at 30% 40%, rgba(34,211,238,0.08), transparent 50%), radial-gradient(circle at 70% 60%, rgba(139,92,246,0.06), transparent 50%)" }}
          />
          <div className="relative z-10">
            <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white">
              本地运行。完全开源。
            </h2>
            <p className="mt-5 mx-auto max-w-xl text-lg text-white/40">
              PnLClaw Community — AGPLv3 许可，专为严肃量化研究者构建。
            </p>
            <div className="mt-10 flex flex-wrap justify-center gap-4">
              <a href="/dashboard"
                className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-500 to-blue-600 px-8 py-3.5 text-sm font-semibold text-white shadow-[0_0_32px_rgba(34,211,238,0.3)] hover:shadow-[0_0_48px_rgba(34,211,238,0.5)] transition-shadow">
                打开 Dashboard <ArrowRight className="size-4" />
              </a>
              <a href="https://github.com/YicunAI/Pnlclaw-community" target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-8 py-3.5 text-sm font-medium text-white/70 hover:bg-white/[0.08] hover:text-white transition-all">
                <Github className="size-4" /> GitHub
              </a>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

// ─── Aggregate export ─────────────────────────────────────────────────────────

export function LandingSections() {
  return (
    <div className="bg-[#0a0a0a] text-white">
      <TickerMarquee />
      <CorePhilosophy />
      <WorkflowDemo />
      <WhyPnLClaw />
      <SkillsSystem />
      <Architecture />
      <Exchanges />
      <Stats />
      <Roadmap />
      <CtaSection />
      <Footer />
    </div>
  );
}

// ─── 11. Footer ───────────────────────────────────────────────────────────────

export function Footer() {
  return (
    <footer className="border-t border-white/[0.06] py-10">
      <div className="mx-auto max-w-7xl px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-white">PnLClaw</span>
          <span className="text-xs text-white/70">Community · AGPLv3 · v0.1</span>
        </div>
        <div className="flex items-center gap-6 text-sm text-white/80">
          <a href="https://github.com/YicunAI/Pnlclaw-community" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors flex items-center gap-1.5">
            <Github className="size-3.5" /> GitHub
          </a>
          <a href="mailto:yicun@pnlclaw.com" className="hover:text-white transition-colors flex items-center gap-1.5">
            <Mail className="size-3.5" /> Contact
          </a>
        </div>
      </div>
    </footer>
  );
}
