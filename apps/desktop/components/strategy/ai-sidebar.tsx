"use client"

import React, { useState, useCallback, useRef, useEffect, useMemo } from "react"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { YamlEditor } from "@/components/strategy/yaml-editor"
import { ParamPanel } from "@/components/strategy/param-panel"
import { cn } from "@/lib/utils"
import { parseRichMarkdownToReact } from "@/lib/markdown-rich"
import {
  Send,
  Trash2,
  Loader2,
  FileCode,
  BarChart3,
  Lightbulb,
  MessageSquareText,
  SlidersHorizontal,
  Sparkles,
  ChevronRight,
  Plus,
  History,
  MessageCircle,
  X,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import {
  sendAgentChat,
  getBacktest,
  createChatSession,
  listChatSessions,
  getChatSessionMessages,
  saveChatSessionMessages,
  deleteChatSession,
  updateChatSessionTitle,
  type AgentChatContext,
  type AgentChatResult,
  type BacktestData,
  type StrategyData,
  type ChatSession,
} from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"

export interface AiSidebarProps {
  strategyId: string
  strategyName: string
  strategy: StrategyData | null
  symbol?: string
  timeframe?: string
  onStrategyChange: (updated: Partial<StrategyData>) => void
  onApplyYaml?: (yamlContent: string) => void
  onCollapse?: () => void
  onBacktestResult?: (result: BacktestData) => void
  onStrategyRefresh?: () => void
}

interface QuickReplyOption {
  id: string
  label: string
  value: string
  description?: string
}

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  reasoningSteps?: ReasoningStep[]
  quickReplies?: QuickReplyOption[]
}

interface ReasoningStep {
  type: "thinking" | "tool_call" | "tool_result" | "reflection"
  data: Record<string, unknown>
  timestamp: number
}

const skillDefs: { id: string; labelKey: string; icon: LucideIcon; prompt: string }[] = [
  {
    id: "strategy-coder",
    labelKey: "strategies.ai.strategyCoder",
    icon: FileCode,
    prompt: "Help me write a trading strategy based on {name}",
  },
  {
    id: "backtest-explain",
    labelKey: "strategies.ai.backtestExplain",
    icon: BarChart3,
    prompt: "Explain the latest backtest results for {name}",
  },
  {
    id: "strategy-draft",
    labelKey: "strategies.ai.strategyIdeas",
    icon: Lightbulb,
    prompt: "Suggest improvements for {name} strategy",
  },
]

type AiSidebarTab = "chat" | "yaml" | "params"

function newMessageId(): string {
  return `${Date.now().toString()}-${Math.random().toString(36).slice(2, 9)}`
}

function deltaTextFromData(data: unknown): string {
  if (typeof data === "string") return data
  if (data && typeof data === "object" && "text" in data) {
    const v = (data as { text: unknown }).text
    if (typeof v === "string") return v
  }
  return ""
}

function extractYamlBlock(content: string): string | null {
  const match = content.match(/```[yY][aA][mM][lL]\s*\r?\n([\s\S]*?)```/)
  return match?.[1]?.trim() || null
}

const BACKTEST_ID_RE = /Backtest Complete\s*[—–-]\s*ID:\s*(bt-[a-f0-9]+)/i
const BACKTEST_ID_FALLBACK_RE = /\b(bt-[a-f0-9]{6,})\b/

function extractBacktestId(toolOutput: string): string | null {
  const m = toolOutput.match(BACKTEST_ID_RE)
  if (m?.[1]) return m[1]
  const fb = toolOutput.match(BACKTEST_ID_FALLBACK_RE)
  return fb?.[1] ?? null
}

function normalizeQuickReplyId(raw: string, fallback: number): string {
  return raw.trim() || String(fallback + 1)
}

function extractStructuredQuickReplies(data: unknown): QuickReplyOption[] {
  if (!data || typeof data !== "object") return []
  const source = data as Record<string, unknown>
  const rawOptions =
    source.quick_replies ??
    source.quickReplies ??
    source.reply_options ??
    source.replyOptions ??
    source.suggested_replies ??
    source.suggestedReplies ??
    source.options

  if (!Array.isArray(rawOptions)) return []

  return rawOptions
    .map((item, index) => {
      if (typeof item === "string") {
        return {
          id: String(index + 1),
          label: item,
          value: item,
        }
      }
      if (!item || typeof item !== "object") return null
      const option = item as Record<string, unknown>
      const label = String(option.label ?? option.title ?? option.text ?? "").trim()
      const value = String(option.value ?? option.message ?? option.prompt ?? label).trim()
      const id = normalizeQuickReplyId(String(option.id ?? option.key ?? option.code ?? ""), index)
      const description = option.description != null ? String(option.description) : undefined
      if (!label || !value) return null
      return { id, label, value, description }
    })
    .filter((item): item is QuickReplyOption => item !== null)
    .slice(0, 6)
}

function extractQuickReplies(content: string): { cleanedContent: string; quickReplies: QuickReplyOption[] } {
  const lines = content.split("\n")
  const quickReplies: QuickReplyOption[] = []
  const cleaned: string[] = []
  let inOptionSection = false

  for (const line of lines) {
    const trimmed = line.trim()
    if (
      !inOptionSection &&
      /如果你愿意|你可以直接回复|你回复数字即可|下一步可以直接帮你做其中一个|你回复\s*[A-Z]/i.test(trimmed)
    ) {
      inOptionSection = true
      cleaned.push(line)
      continue
    }

    const numbered = trimmed.match(/^([1-9A-Z])\s*[).、:-]?\s+(.+)$/)
    if (inOptionSection && numbered) {
      const fullLabel = numbered[2].trim().replace(/\*\*/g, "")
      quickReplies.push({
        id: normalizeQuickReplyId(numbered[1], quickReplies.length),
        label: fullLabel,
        value: fullLabel,
      })
      continue
    }

    const bulleted = trimmed.match(/^[-*]\s+(.+)$/)
    if (inOptionSection && bulleted) {
      const label = bulleted[1].trim().replace(/\*\*/g, "")
      quickReplies.push({
        id: String(quickReplies.length + 1),
        label,
        value: label,
      })
      continue
    }

    cleaned.push(line)
  }

  return {
    cleanedContent: cleaned.join("\n").trim(),
    quickReplies: quickReplies.slice(0, 6),
  }
}

function cleanReasoningText(raw: string): string {
  return raw
    .replace(/<\/?reasoning>/gi, "")
    .replace(/^(?:Step|Round)\s*\d+\s*[:：]?\s*(?:Think|Reflect|Act|Observe|Analyze|Decide)?\s*/gim, "")
    .trim()
}

function formatReasoningSummary(step: ReasoningStep): string {
  if (step.type === "thinking" || step.type === "reflection") {
    return cleanReasoningText(String(step.data.content ?? step.data.summary ?? ""))
  }
  if (step.type === "tool_call") {
    const tool = String(step.data.tool ?? step.data.name ?? "unknown")
    const args = step.data.arguments ?? step.data.input ?? {}
    return `${tool}(${JSON.stringify(args)})`
  }
  const output = cleanReasoningText(String(step.data.output ?? step.data.result ?? step.data.content ?? ""))
  return output.length > 120 ? `${output.slice(0, 120)}…` : output
}

const STEP_TONES: Record<ReasoningStep["type"], { icon: string; tone: string }> = {
  thinking: { icon: "🧠", tone: "border-sky-500/20 bg-sky-500/8 text-sky-200" },
  tool_call: { icon: "⚙️", tone: "border-violet-500/20 bg-violet-500/8 text-violet-200" },
  tool_result: { icon: "📊", tone: "border-emerald-500/20 bg-emerald-500/8 text-emerald-200" },
  reflection: { icon: "💡", tone: "border-amber-500/20 bg-amber-500/8 text-amber-200" },
}

const STEP_LABEL_KEYS = {
  thinking: "strategies.ai.stepThinking",
  tool_call: "strategies.ai.stepToolCall",
  tool_result: "strategies.ai.stepToolResult",
  reflection: "strategies.ai.stepReflection",
} as const

function ReasoningProgress({
  steps,
  isComplete,
}: {
  steps: ReasoningStep[]
  isComplete: boolean
}) {
  const { t } = useI18n()
  const [isOpen, setIsOpen] = useState(!isComplete)

  useEffect(() => {
    if (isComplete) {
      setIsOpen(false)
      return
    }
    setIsOpen(true)
  }, [isComplete, steps.length])

  if (!steps.length) return null

  const latest = steps[steps.length - 1]
  const latestSummary = formatReasoningSummary(latest) || t(STEP_LABEL_KEYS[latest.type])

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-primary/15 bg-background/60 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full border-b border-border/70 bg-primary/5 px-3 py-2 text-left transition-colors hover:bg-primary/8"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-primary/80">
              {t("strategies.ai.progress")}
            </p>
            <p className="mt-1 truncate text-[13px] text-foreground/90">{latestSummary}</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="rounded-full border border-primary/15 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
              {t("strategies.ai.stepsCount").replace("{count}", String(steps.length))}
            </div>
            <span className="text-xs text-muted-foreground">{isOpen ? t("strategies.ai.stepsCollapse") : t("strategies.ai.stepsExpand")}</span>
          </div>
        </div>
      </button>
      {isOpen && (
        <div className="space-y-2 px-3 py-3">
          {steps.map((step, idx) => {
            const visual = STEP_TONES[step.type]
            const label = t(STEP_LABEL_KEYS[step.type])
            const summary = formatReasoningSummary(step)
            const isLatest = idx === steps.length - 1
            return (
              <div key={`${step.type}-${idx}-${step.timestamp}`} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div
                    className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-[13px] shadow-sm",
                      visual.tone,
                      isLatest && "ring-2 ring-primary/20"
                    )}
                  >
                    {visual.icon}
                  </div>
                  {idx < steps.length - 1 && <div className="mt-1 h-full w-px bg-border/80" />}
                </div>
                <div className="min-w-0 flex-1 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-foreground">{label}</span>
                    {isLatest && (
                      <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                        {t("strategies.ai.stepsCurrent")}
                      </span>
                    )}
                  </div>
                  {summary ? (
                    <p className="mt-1 whitespace-pre-wrap break-words text-[12px] leading-6 text-muted-foreground">
                      {summary}
                    </p>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function AssistantQuickReplies({
  options,
  disabled,
  onSelect,
}: {
  options: QuickReplyOption[]
  disabled: boolean
  onSelect: (value: string) => void
}) {
  if (!options.length) return null

  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center gap-2">
        <Sparkles className="h-3.5 w-3.5 text-primary" />
        <p className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">快捷选择</p>
      </div>
      <div className="space-y-2">
        {options.map((option) => (
          <button
            key={`${option.id}-${option.value}`}
            type="button"
            onClick={() => onSelect(option.value)}
            disabled={disabled}
            className="group w-full rounded-2xl border border-border/70 bg-background/60 px-3 py-3 text-left text-[13px] font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 disabled:pointer-events-none disabled:opacity-50"
          >
            <div className="flex items-center gap-3">
              <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-[12px] font-semibold text-primary">
                {option.id}
              </span>
              <div className="min-w-0 flex-1">
                <div>{option.label}</div>
                {option.description ? (
                  <p className="mt-1 text-[11px] leading-5 text-muted-foreground">{option.description}</p>
                ) : null}
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground transition-colors group-hover:text-primary" />
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function AssistantMessageContent({
  content,
  generating,
  reasoningSteps,
  quickReplies,
  onQuickReplySelect,
  onApplyYaml,
  applyLabel,
}: {
  content: string
  generating: boolean
  reasoningSteps?: ReasoningStep[]
  quickReplies?: QuickReplyOption[]
  onQuickReplySelect: (value: string) => void
  onApplyYaml?: (yamlContent: string) => void
  applyLabel: string
}) {
  const yamlBlock = extractYamlBlock(content)
  const { cleanedContent: rawCleaned, quickReplies: extractedQuickReplies } = useMemo(
    () => extractQuickReplies(content),
    [content]
  )
  const cleanedContent = useMemo(() => cleanReasoningText(rawCleaned), [rawCleaned])
  const mergedQuickReplies = quickReplies?.length ? quickReplies : extractedQuickReplies
  const isComplete = useMemo(() => {
    if (!reasoningSteps?.length) return false
    if (!cleanedContent.trim()) return false
    const latest = reasoningSteps[reasoningSteps.length - 1]
    return latest.type === "reflection" || !generating
  }, [cleanedContent, generating, reasoningSteps])

  return (
    <div className="space-y-3">
      <ReasoningProgress steps={reasoningSteps ?? []} isComplete={isComplete} />
      {!!cleanedContent && (
        <div className={cn(
          "strategy-ai-richtext",
          "text-[13px] leading-6",
          "[&_strong]:font-semibold [&_em]:italic"
        )}>
          {parseRichMarkdownToReact(cleanedContent, generating)}
        </div>
      )}
      <AssistantQuickReplies
        options={mergedQuickReplies ?? []}
        disabled={generating}
        onSelect={onQuickReplySelect}
      />
      {yamlBlock && onApplyYaml && (
        <Button
          size="sm"
          variant="outline"
          className="h-8 rounded-xl border-primary/20 bg-primary/5 text-[11px] hover:bg-primary/10"
          onClick={() => onApplyYaml(yamlBlock)}
        >
          {applyLabel}
        </Button>
      )}
    </div>
  )
}

function AssistantEmptyState({
  title,
  subtitle,
}: {
  title: string
  subtitle: string
}) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-primary/15 bg-primary/10 shadow-sm">
        <img src="/logo2.svg" alt="PnLClaw" className="h-6 w-6" />
      </div>
      <h3 className="mt-3 text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1 max-w-[260px] text-[12px] leading-5 text-muted-foreground">{subtitle}</p>
    </div>
  )
}

function PanelSection({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[22px] border border-border/70 bg-background/35">
      <div className="shrink-0 border-b border-border/70 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-primary/80">{eyebrow}</p>
        <h3 className="mt-1 text-sm font-semibold text-foreground">{title}</h3>
        <p className="mt-1 text-[12px] leading-5 text-muted-foreground">{description}</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">{children}</div>
    </div>
  )
}

export function AiSidebar({
  strategyId,
  strategyName,
  strategy,
  onStrategyRefresh,
  symbol,
  timeframe,
  onStrategyChange,
  onApplyYaml,
  onBacktestResult,
  onCollapse,
}: AiSidebarProps) {
  const { t } = useI18n()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [generating, setGenerating] = useState(false)
  const [activeTab, setActiveTab] = useState<AiSidebarTab>("chat")
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef(false)
  const mountedRef = useRef(true)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [heartbeatText, setHeartbeatText] = useState<string>("")
  const [lastFailedMessage, setLastFailedMessage] = useState<string>("")
  const [reconnecting, setReconnecting] = useState(false)
  const lastAssistantIdRef = useRef<string>("")
  const lastCleanContentRef = useRef<string>("")
  const lastCleanStepsRef = useRef<ReasoningStep[]>([])

  const messagesRef = useRef<ChatMessage[]>([])
  const sessionIdRef = useRef<string | undefined>(undefined)
  const skipNextSaveRef = useRef(false)
  messagesRef.current = messages
  sessionIdRef.current = sessionId

  const lastSavedTitleRef = useRef<string>("")

  const flushSave = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
    const sid = sessionIdRef.current
    const msgs = messagesRef.current
    if (!sid || msgs.length === 0) return
    const payload = msgs.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      extra: m.reasoningSteps ?? {},
    }))
    void saveChatSessionMessages(sid, payload)
    const firstUser = msgs.find((m) => m.role === "user")
    if (firstUser) {
      const title = firstUser.content.slice(0, 40) + (firstUser.content.length > 40 ? "…" : "")
      if (title !== lastSavedTitleRef.current) {
        lastSavedTitleRef.current = title
        void updateChatSessionTitle(sid, title)
      }
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    const handleBeforeUnload = () => flushSave()
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => {
      mountedRef.current = false
      window.removeEventListener("beforeunload", handleBeforeUnload)
      flushSave()
    }
  }, [flushSave])

  // Load session list + latest session on mount / strategyId change
  useEffect(() => {
    let cancelled = false
    async function load() {
      const listRes = await listChatSessions(strategyId)
      if (cancelled) return
      const list = listRes.data ?? []
      setSessions(list)

      if (list.length > 0) {
        const latest = list[0]
        setSessionId(latest.id)
        const msgRes = await getChatSessionMessages(latest.id)
        if (cancelled) return
        const loaded = (msgRes.data ?? []).map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          reasoningSteps: Array.isArray(m.extra) ? m.extra as unknown as ReasoningStep[] : undefined,
        }))
        skipNextSaveRef.current = true
        setMessages(loaded)
      } else {
        setSessionId(undefined)
        skipNextSaveRef.current = true
        setMessages([])
      }
    }
    void load()
    return () => { cancelled = true }
  }, [strategyId])

  // Debounced save to backend whenever messages change (skip server-loaded data)
  useEffect(() => {
    if (skipNextSaveRef.current) {
      skipNextSaveRef.current = false
      return
    }
    if (!sessionId || messages.length === 0) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      flushSave()
    }, 1500)
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current) }
  }, [messages, sessionId, flushSave])

  const scrollToBottom = useCallback(() => {
    const el = messagesEndRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, generating, scrollToBottom])

  const refreshSessionList = useCallback(async () => {
    const res = await listChatSessions(strategyId)
    if (mountedRef.current && res.data) setSessions(res.data)
  }, [strategyId])

  const handleNewConversation = useCallback(async () => {
    setTimeout(() => flushSave(), 150)
    skipNextSaveRef.current = true
    setMessages([])
    setShowHistory(false)
    const tempId = `temp-${Date.now()}`
    setSessionId(tempId)
    const res = await createChatSession(strategyId, "")
    if (res.data) {
      setSessionId(res.data.id)
      setSessions((prev) => [res.data!, ...prev])
    }
  }, [strategyId, flushSave])

  const handleSwitchSession = useCallback((targetId: string) => {
    if (targetId === sessionId) {
      setShowHistory(false)
      return
    }
    // Delay the save so the GET for the new session fires first and isn't
    // blocked behind the write lock on the backend.
    setTimeout(() => flushSave(), 150)
    setSessionId(targetId)
    skipNextSaveRef.current = true
    setMessages([])
    setShowHistory(false)
    getChatSessionMessages(targetId).then((msgRes) => {
      if (!mountedRef.current) return
      const loaded = (msgRes.data ?? []).map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
        reasoningSteps: Array.isArray(m.extra) ? m.extra as unknown as ReasoningStep[] : undefined,
      }))
      skipNextSaveRef.current = true
      setMessages(loaded)
    })
  }, [sessionId, flushSave])

  const handleDeleteSession = useCallback((targetId: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== targetId))
    if (targetId === sessionId) {
      setSessionId(undefined)
      setMessages([])
    }
    void deleteChatSession(targetId)
  }, [sessionId])

  const handleClear = useCallback(() => {
    const sid = sessionId
    setMessages([])
    setSessionId(undefined)
    setActiveTab("chat")
    if (sid) {
      setSessions((prev) => prev.filter((s) => s.id !== sid))
      void deleteChatSession(sid)
    }
  }, [sessionId])

  const sendWithText = useCallback(
    async (messageText: string, opts?: { resume?: boolean }) => {
      const text = messageText.trim()
      if (!text || sendingRef.current) return
      sendingRef.current = true

      const isResume = !!opts?.resume

      let effectiveSessionId = sessionId
      if (!isResume && !effectiveSessionId) {
        const res = await createChatSession(strategyId, text.slice(0, 40))
        if (res.data) {
          effectiveSessionId = res.data.id
          setSessionId(effectiveSessionId)
          setSessions((prev) => {
            if (prev.some((s) => s.id === res.data!.id)) return prev
            return [res.data! as ChatSession, ...prev]
          })
        }
      }

      let assistantId: string
      if (isResume && lastAssistantIdRef.current) {
        assistantId = lastAssistantIdRef.current
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: lastCleanContentRef.current, reasoningSteps: lastCleanStepsRef.current }
              : m
          )
        )
      } else {
        const userId = newMessageId()
        assistantId = newMessageId()
        setMessages((prev) => [
          ...prev,
          { id: userId, role: "user", content: text },
          { id: assistantId, role: "assistant", content: "", reasoningSteps: [] },
        ])
        setInput("")
        if (textareaRef.current) textareaRef.current.style.height = ""
      }
      setGenerating(true)

      const context: AgentChatContext = {
        intent: "strategy_chat",
        strategy_id: strategyId,
        strategy_name: strategyName,
        symbol,
        timeframe,
      }

      let saveToolFired = false

      const onEvent = (event: { type: string; data: unknown }) => {
        if (!mountedRef.current) return

        if (event.type === "heartbeat") {
          const hbData = event.data as Record<string, unknown> | undefined
          const step = String(hbData?.step ?? "processing")
          setHeartbeatText(step)
          return
        }

        const isReasoningEvent =
          event.type === "thinking" ||
          event.type === "tool_call" ||
          event.type === "tool_result" ||
          event.type === "reflection"

        if (isReasoningEvent) {
          setHeartbeatText("")
          const step: ReasoningStep = {
            type: event.type as ReasoningStep["type"],
            data:
              typeof event.data === "object" && event.data !== null
                ? (event.data as Record<string, unknown>)
                : { content: String(event.data ?? "") },
            timestamp: Date.now(),
          }
          const structuredQuickReplies = extractStructuredQuickReplies(event.data)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    reasoningSteps: [...(m.reasoningSteps ?? []), step],
                    quickReplies: structuredQuickReplies.length ? structuredQuickReplies : m.quickReplies,
                  }
                : m
            )
          )

          if (event.type === "tool_result") {
            const toolData = event.data as Record<string, unknown> | undefined
            const toolName = String(toolData?.tool ?? "")
            const toolOutput = String(toolData?.output ?? "")
            if (toolName === "backtest_run" && onBacktestResult) {
              const btId = extractBacktestId(toolOutput)
              if (btId) {
                getBacktest(btId).then((res) => {
                  if (res.data && mountedRef.current) {
                    onBacktestResult(res.data)
                  }
                })
              }
            }
            if (
              (toolName === "save_strategy_version" || toolName === "deploy_strategy" || toolName === "stop_strategy") &&
              onStrategyRefresh
            ) {
              saveToolFired = true
              onStrategyRefresh()
            }
          }
          return
        }

        if (event.type === "text_delta" || event.type === "text") {
          setHeartbeatText("")
          const chunk = deltaTextFromData(event.data)
          if (!chunk) return
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId) return m
              const nextContent = m.content + chunk
              const { quickReplies } = extractQuickReplies(nextContent)
              return { ...m, content: nextContent, quickReplies: m.quickReplies?.length ? m.quickReplies : quickReplies }
            })
          )
          return
        }
        if (event.type === "reconnecting") {
          setReconnecting(true)
          const rd = event.data as Record<string, unknown> | undefined
          setHeartbeatText(
            t("strategies.ai.reconnecting") ||
            `重连中 (${rd?.attempt ?? ""}/${rd?.maxAttempts ?? ""})...`
          )
          return
        }
        if (event.type === "reconnected") {
          setReconnecting(false)
          setHeartbeatText(t("strategies.ai.reconnected") || "已重连，继续处理...")
          return
        }
        if (event.type === "error") {
          setHeartbeatText("")
          setReconnecting(false)
          const err =
            typeof event.data === "string"
              ? event.data
              : event.data != null
                ? String(event.data)
                : "Error"
          setMessages((prev) => {
            const current = prev.find((m) => m.id === assistantId)
            lastCleanContentRef.current = current?.content ?? ""
            lastCleanStepsRef.current = current?.reasoningSteps ?? []
            lastAssistantIdRef.current = assistantId
            return prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: m.content + (m.content ? "\n\n" : "") + `⚠️ ${err}`,
                  }
                : m
            )
          })
          setLastFailedMessage(text)
          setGenerating(false)
          return
        }
        if (event.type === "done") {
          setHeartbeatText("")
          setReconnecting(false)
          const doneData = event.data as Record<string, unknown> | undefined
          const errorMsg = doneData?.error
          if (errorMsg) {
            setMessages((prev) => {
              const current = prev.find((m) => m.id === assistantId)
              lastCleanContentRef.current = current?.content ?? ""
              lastCleanStepsRef.current = current?.reasoningSteps ?? []
              lastAssistantIdRef.current = assistantId
              return prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: m.content + (m.content ? "\n\n" : "") + `⚠️ ${String(errorMsg)}`,
                    }
                  : m
              )
            })
            setLastFailedMessage(text)
          } else {
            setLastFailedMessage("")
          }
          setGenerating(false)
          setTimeout(() => flushSave(), 50)

          if (!errorMsg && onApplyYaml) {
            setMessages((prev) => {
              const last = prev.find((m) => m.id === assistantId)
              if (last?.content) {
                const yaml = extractYamlBlock(last.content)
                if (yaml) onApplyYaml(yaml)
              }
              return prev
            })
          }

          if (saveToolFired && onStrategyRefresh) {
            setTimeout(() => onStrategyRefresh(), 300)
          }
        }
      }

      const controller = new AbortController()
      abortRef.current = controller
      const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000)

      try {
        const result: AgentChatResult = await sendAgentChat(
          text, onEvent, context, effectiveSessionId, controller.signal,
          isResume ? { resume: true } : undefined,
        )
        if (mountedRef.current && result.sessionId) setSessionId(result.sessionId)
      } finally {
        clearTimeout(timeout)
        abortRef.current = null
        sendingRef.current = false
        if (mountedRef.current) {
          setGenerating(false)
          setHeartbeatText("")
          setReconnecting(false)
        }
      }
    },
    [strategyId, strategyName, symbol, timeframe, sessionId, onBacktestResult, onStrategyRefresh, refreshSessionList, flushSave]
  )

  const handleSend = useCallback(() => {
    void sendWithText(input)
  }, [input, sendWithText])

  const handleQuickReplySelect = useCallback(
    (value: string) => {
      void sendWithText(value)
    },
    [sendWithText]
  )

  const handleSkillClick = useCallback(
    (skill: (typeof skillDefs)[number]) => {
      const prompt = skill.prompt.replace(/\{name\}/g, strategyName)
      setInput(prompt)
      setActiveTab("chat")
      void sendWithText(prompt)
    },
    [strategyName, sendWithText]
  )

  return (
    <Tabs
      value={activeTab}
      onValueChange={(value) => setActiveTab(value as AiSidebarTab)}
      className="flex h-full min-h-0 flex-col overflow-hidden"
    >
      <div className="shrink-0 border-b border-border/60 px-2.5 py-1.5">
        <div className="flex items-center gap-1.5">
          <img src="/logo2.svg" alt="PnLClaw" className="h-4 w-4 shrink-0" />
          <span className="truncate text-[13px] font-semibold text-foreground">{t("strategies.studio.aiHelper")}</span>
          {symbol && <span className="text-[10px] text-muted-foreground">{symbol}</span>}
          {timeframe && <span className="text-[10px] text-muted-foreground">{timeframe}</span>}
          {sessionId && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" title="Live" />}
          <div className="ml-auto flex items-center gap-0.5">
            <button
              type="button"
              onClick={() => void handleNewConversation()}
              disabled={generating}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
              title={t("strategies.ai.newConversation")}
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => { setShowHistory((v) => !v); void refreshSessionList() }}
              className={cn("rounded-md p-1 transition-colors", showHistory ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground")}
              title={t("strategies.ai.history")}
            >
              <History className="h-3.5 w-3.5" />
            </button>
            {onCollapse && (
              <button
                type="button"
                onClick={onCollapse}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {showHistory && (
          <div className="mt-1.5 max-h-44 overflow-y-auto rounded-lg border border-border/70 bg-card/90 p-1.5">
            {sessions.length === 0 ? (
              <p className="py-2 text-center text-[11px] text-muted-foreground">{t("strategies.ai.noHistory")}</p>
            ) : (
              <div className="space-y-0.5">
                {sessions.map((s) => (
                  <div
                    key={s.id}
                    className={cn(
                      "group flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors",
                      s.id === sessionId ? "bg-primary/10 text-foreground" : "cursor-pointer hover:bg-muted/60"
                    )}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-1.5"
                      onClick={() => void handleSwitchSession(s.id)}
                    >
                      <MessageCircle className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-[11px]">
                        {s.title || t("strategies.ai.untitledSession")}
                      </span>
                      <span className="shrink-0 text-[9px] text-muted-foreground">{s.message_count ?? 0}</span>
                    </button>
                    <button
                      type="button"
                      className="hidden h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover:flex"
                      onClick={(e) => { e.stopPropagation(); void handleDeleteSession(s.id) }}
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <TabsList className="mt-1.5 grid h-8 w-full grid-cols-3 rounded-lg bg-muted/50 p-0.5">
          <TabsTrigger value="chat" className="gap-1 rounded-md text-[11px] data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm">
            <MessageSquareText className="h-3 w-3" />
            {t("strategies.studio.aiHelper")}
          </TabsTrigger>
          <TabsTrigger value="yaml" className="gap-1 rounded-md text-[11px] data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm">
            <FileCode className="h-3 w-3" />
            YAML
          </TabsTrigger>
          <TabsTrigger value="params" className="gap-1 rounded-md text-[11px] data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm">
            <SlidersHorizontal className="h-3 w-3" />
            {t("strategies.studio.paramsTab")}
          </TabsTrigger>
        </TabsList>
      </div>

      <TabsContent value="chat" className="mt-0 flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Messages area — takes all available space */}
        <div className="min-h-0 flex-1 overflow-y-auto px-2.5 py-2.5" ref={messagesEndRef}>
          <div className="space-y-2.5">
            {messages.length === 0 ? (
              <AssistantEmptyState
                title={t("strategies.studio.aiHelper")}
                subtitle="直接描述你想构建、解释或优化的策略，助手会结合当前策略上下文继续完成。"
              />
            ) : (
              messages.map((msg) => {
                const isLatestAssistant = msg.role === "assistant" && msg.id === messages[messages.length - 1]?.id

                return (
                  <div key={msg.id} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                    <div
                      className={cn(
                        "max-w-[92%] rounded-2xl border px-3 py-2.5 shadow-sm",
                        msg.role === "user"
                          ? "border-primary/20 bg-primary/10 text-foreground"
                          : "border-border/70 bg-background/65 text-muted-foreground"
                      )}
                    >
                      {msg.role === "user" ? (
                        <p className="whitespace-pre-wrap text-[13px] leading-6 text-foreground">{msg.content}</p>
                      ) : (
                        <AssistantMessageContent
                          content={msg.content}
                          generating={generating && isLatestAssistant}
                          reasoningSteps={msg.reasoningSteps}
                          quickReplies={msg.quickReplies}
                          onQuickReplySelect={handleQuickReplySelect}
                          onApplyYaml={onApplyYaml}
                          applyLabel={t("strategies.studio.applyChanges")}
                        />
                      )}
                    </div>
                  </div>
                )
              })
            )}

            {generating && (
              <div className={`flex items-center gap-2 rounded-2xl border px-3 py-2 text-xs ${
                reconnecting
                  ? "border-amber-500/40 bg-amber-500/5 text-amber-400"
                  : "border-border/70 bg-background/40 text-muted-foreground"
              }`}>
                <Loader2 className="h-3 w-3 animate-spin" />
                <span>{heartbeatText || t("strategies.ai.thinking")}</span>
              </div>
            )}

            {!generating && lastFailedMessage && (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 rounded-lg border-amber-500/30 bg-amber-500/5 text-[11px] text-amber-400 hover:bg-amber-500/10"
                  onClick={() => {
                    const msg = lastFailedMessage
                    setLastFailedMessage("")
                    void sendWithText(msg, { resume: true })
                  }}
                >
                  ↻ {t("strategies.ai.retry") || "继续"}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Bottom: quick action buttons + input */}
        <div className="shrink-0 border-t border-border/70 bg-card/80 px-2.5 py-2 backdrop-blur-sm">
          <div className="mb-1.5 flex flex-wrap gap-1.5">
            {skillDefs.map((skill) => {
              const Icon = skill.icon
              return (
                <button
                  key={skill.id}
                  type="button"
                  onClick={() => handleSkillClick(skill)}
                  disabled={generating}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 bg-background/50 px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary disabled:pointer-events-none disabled:opacity-50"
                >
                  <Icon className="h-3 w-3" />
                  {t(skill.labelKey as Parameters<typeof t>[0])}
                </button>
              )
            })}
          </div>
          <div className="flex items-end gap-2 rounded-xl border border-border/70 bg-background/55 px-2 py-1.5">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                const el = e.target
                el.style.height = "0"
                el.style.height = `${Math.min(el.scrollHeight, 160)}px`
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder={t("strategies.ai.askPlaceholder")}
              className="max-h-[160px] min-h-[32px] flex-1 resize-none overflow-y-auto border-0 bg-transparent px-1 py-1 text-[13px] leading-[1.6] text-foreground shadow-none outline-none placeholder:text-muted-foreground focus-visible:ring-0"
              disabled={generating}
              rows={1}
            />
            <Button
              size="icon"
              className="mb-0.5 h-8 w-8 shrink-0 rounded-xl"
              onClick={handleSend}
              disabled={!input.trim() || generating}
            >
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="yaml" className="mt-0 min-h-0 flex-1 overflow-hidden px-3 pb-3">
        <PanelSection
          eyebrow="Config artifact"
          title={t("strategies.studio.yamlTab")}
          description="Review the generated strategy structure and edit YAML without leaving the copilot workspace."
        >
          {strategy ? <YamlEditor strategy={strategy} onChange={onStrategyChange} /> : null}
        </PanelSection>
      </TabsContent>

      <TabsContent value="params" className="mt-0 min-h-0 flex-1 overflow-hidden px-3 pb-3">
        <PanelSection
          eyebrow="Parameter board"
          title={t("strategies.studio.paramsTab")}
          description="Tune strategy settings and rules with the same assistant-side workspace framing."
        >
          {strategy ? <ParamPanel strategy={strategy} onChange={onStrategyChange} /> : null}
        </PanelSection>
      </TabsContent>
    </Tabs>
  )
}
