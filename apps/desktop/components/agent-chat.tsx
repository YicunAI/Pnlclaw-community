"use client"

import React, { useState, useCallback, useRef, useEffect } from "react"
import { X, Send, Trash2, Minus, History, Plus, ChevronLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { sendAgentChat, listChatSessions, getChatSessionMessages, deleteChatSession, saveChatSessionMessages, type ChatSession, type ChatMessageRecord } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"
import { useDashboardRealtime } from "@/components/providers/dashboard-realtime-provider"

interface ReasoningStep {
  type: "thinking" | "tool_call" | "tool_result" | "reflection"
  data: Record<string, unknown>
  timestamp: number
}

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: number
  reasoningSteps?: ReasoningStep[]
}

export function parseMarkdownToReact(text: string, isGenerating?: boolean): React.ReactNode[] {
  const elements: React.ReactNode[] = []

  // Extract and render tool_call tags
  const toolCallMatches = text.match(/<tool_call>[\s\S]*?<\/tool_call>/g)
  if (toolCallMatches && toolCallMatches.length > 0) {
    elements.push(
      <details key="tool-calls" className="my-3 rounded-lg border border-primary/30 bg-primary/5">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-primary hover:bg-primary/10 rounded-t-lg">
          🔧 工具调用 ({toolCallMatches.length}) - 点击查看 AI 的思考过程
        </summary>
        <div className="px-3 py-2 space-y-2 text-xs">
          {toolCallMatches.map((match, idx) => {
            try {
              const jsonStr = match.replace(/<\/?tool_call>/g, '').trim()
              const toolCall = JSON.parse(jsonStr)
              return (
                <div key={idx} className="bg-muted/50 rounded p-2 font-mono">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-primary font-bold">→ {toolCall.name}</span>
                  </div>
                  <div className="text-muted-foreground text-[11px] pl-3">
                    {JSON.stringify(toolCall.arguments, null, 2)}
                  </div>
                </div>
              )
            } catch (e) {
              return (
                <div key={idx} className="bg-muted/50 rounded p-2 font-mono text-[11px] text-muted-foreground">
                  {match}
                </div>
              )
            }
          })}
        </div>
      </details>
    )
  }

  const cleanedText = text.replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
  const lines = cleanedText.split('\n')
  let i = 0

  let inReasoning = false
  let reasoningLines: string[] = []

  const flushReasoning = (isCompleted: boolean) => {
    if (reasoningLines.length > 0) {
      elements.push(
        <div key={`reasoning-${i}`} className={cn(
          "my-3 p-3 rounded-xl border-l-[3px] text-[13px] font-mono whitespace-pre-wrap leading-relaxed shadow-sm",
          isCompleted 
            ? "bg-amber-500/5 border-amber-500/50 text-amber-700/80 dark:text-amber-400/80" 
            : "bg-blue-500/5 border-blue-500/50 text-blue-700/80 dark:text-blue-400/80 animate-pulse"
        )}>
          <div className="flex items-center gap-1.5 mb-1.5 opacity-90 font-bold">
            <span className="text-sm">🤔</span> 
            {isCompleted ? "Internal Reasoning" : "Thinking..."}
          </div>
          {reasoningLines.join('\n')}
        </div>
      )
      reasoningLines = []
    }
  }

  while (i < lines.length) {
    let line = lines[i]

    if (inReasoning) {
      if (line.includes('</reasoning>')) {
        reasoningLines.push(line.replace('</reasoning>', ''))
        flushReasoning(true)
        inReasoning = false
      } else {
        reasoningLines.push(line)
      }
      i++
      continue
    }

    if (line.includes('<reasoning>')) {
      inReasoning = true
      const contentAfter = line.substring(line.indexOf('<reasoning>') + '<reasoning>'.length)
      if (contentAfter.includes('</reasoning>')) {
         reasoningLines.push(contentAfter.replace('</reasoning>', ''))
         flushReasoning(true)
         inReasoning = false
      } else {
         reasoningLines.push(contentAfter)
      }
      i++
      continue
    }

    // Headers
    if (line.startsWith('### ')) {
      elements.push(<h3 key={`h3-${i}`} className="text-sm font-bold mt-5 mb-2 text-primary flex items-center gap-2"><div className="w-1.5 h-1.5 rounded-full bg-primary" />{parseInlineMarkdown(line.replace(/^###\s*/, ''))}</h3>)
      i++
      continue
    }
    if (line.startsWith('## ')) {
      elements.push(<h2 key={`h2-${i}`} className="text-base font-bold mt-5 mb-2 text-foreground border-b border-border pb-1"><span className="text-primary mr-1">#</span>{parseInlineMarkdown(line.replace(/^##\s*/, ''))}</h2>)
      i++
      continue
    }
    if (line.startsWith('# ')) {
      elements.push(<h1 key={`h1-${i}`} className="text-lg font-black mt-6 mb-4 bg-gradient-to-r from-primary to-blue-500 bg-clip-text text-transparent">{parseInlineMarkdown(line.replace(/^#\s*/, ''))}</h1>)
      i++
      continue
    }

    // Blockquote
    if (line.startsWith('> ')) {
      elements.push(
        <blockquote key={`quote-${i}`} className="border-l-4 border-primary/50 bg-primary/5 px-4 py-2 my-3 text-muted-foreground italic rounded-r-lg text-[13px]">
          {parseInlineMarkdown(line.replace(/^>\s*/, ''))}
        </blockquote>
      )
      i++
      continue
    }

    // Unordered List
    if (line.match(/^[-*]\s/)) {
      const listItems: string[] = []
      while (i < lines.length && lines[i].match(/^[-*]\s/)) {
        listItems.push(lines[i].replace(/^[-*]\s/, ''))
        i++
      }
      elements.push(
        <ul key={`ul-${i}`} className="space-y-1.5 my-3">
          {listItems.map((item, idx) => (
            <li key={`uli-${i}-${idx}`} className="flex items-start gap-2 text-[13px]">
              <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-primary/60 shrink-0" />
              <span className="flex-1 leading-relaxed">{parseInlineMarkdown(item)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    // Ordered List
    if (line.match(/^\d+\.\s/)) {
      const listItems: string[] = []
      const startI = i;
      while (i < lines.length && lines[i].match(/^\d+\.\s/)) {
        listItems.push(lines[i].replace(/^\d+\.\s/, ''))
        i++
      }
      elements.push(
        <ol key={`ol-${startI}`} className="space-y-1.5 my-3 list-decimal list-inside text-primary font-medium text-[13px]">
          {listItems.map((item, idx) => (
            <li key={`oli-${startI}-${idx}`} className="leading-relaxed">
              <span className="text-foreground font-normal ml-1">{parseInlineMarkdown(item)}</span>
            </li>
          ))}
        </ol>
      )
      continue
    }

    // Tables
    if (line.includes('|') && line.trim().startsWith('|')) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim().startsWith('|')) {
        if (!lines[i].match(/^[\s|:-]+$/)) {
          tableLines.push(lines[i])
        }
        i++
      }
      if (tableLines.length > 0) {
        const rows = tableLines.map(l => l.split('|').map(c => c.trim()).filter(c => c))
        elements.push(
          <div key={`table-${i}`} className="overflow-x-auto my-3 rounded-lg border border-border">
            <table className="min-w-full border-collapse text-xs">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  {rows[0].map((cell, idx) => (
                    <th key={`th-${i}-${idx}`} className="px-3 py-2 text-left font-semibold text-foreground">
                      {parseInlineMarkdown(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.slice(1).map((row, rowIdx) => (
                  <tr key={`tr-${i}-${rowIdx}`} className="hover:bg-muted/30 transition-colors">
                    {row.map((cell, cellIdx) => (
                      <td key={`td-${i}-${rowIdx}-${cellIdx}`} className="px-3 py-2 text-muted-foreground">
                        {parseInlineMarkdown(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
      continue
    }

    // Empty Lines
    if (line.trim() === '') {
      elements.push(<div key={`br-${i}`} className="h-1.5" />)
      i++
      continue
    }

    // Paragraph
    elements.push(<p key={`p-${i}`} className="my-1.5 text-[14px] leading-relaxed relative flex items-center flex-wrap">
      {parseInlineMarkdown(line)}
      {isGenerating && i === lines.length - 1 && !inReasoning && (
        <span className="inline-block w-2 h-4 bg-primary shadow-[0_0_8px_rgba(var(--primary),0.6)] rounded-sm animate-[pulse_0.8s_cubic-bezier(0.4,0,0.6,1)_infinite] ml-1 align-middle translate-y-px" />
      )}
    </p>)
    i++
  }

  // Flush any unterminated reasoning
  if (inReasoning) {
    flushReasoning(false)
  }

  // If entirely empty but generating, show standalone cursor
  if (elements.length === 0 && isGenerating) {
    return [<span key="only-cursor" className="inline-block w-2 h-4 bg-primary shadow-[0_0_8px_rgba(var(--primary),0.6)] rounded-sm animate-[pulse_0.8s_cubic-bezier(0.4,0,0.6,1)_infinite] align-middle mt-1" />]
  }

  return elements
}

function parseInlineMarkdown(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let remaining = text
  let key = 0

  while (remaining) {
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/)
    if (boldMatch) {
      const before = remaining.slice(0, boldMatch.index)
      if (before) parts.push(before)
      parts.push(<strong key={key++} className="font-semibold text-primary">{boldMatch[1]}</strong>)
      remaining = remaining.slice((boldMatch.index || 0) + boldMatch[0].length)
      continue
    }

    const italicMatch = remaining.match(/\*(.+?)\*/)
    if (italicMatch) {
      const before = remaining.slice(0, italicMatch.index)
      if (before) parts.push(before)
      parts.push(<em key={key++} className="italic text-foreground/80">{italicMatch[1]}</em>)
      remaining = remaining.slice((italicMatch.index || 0) + italicMatch[0].length)
      continue
    }

    const codeMatch = remaining.match(/`(.+?)`/)
    if (codeMatch) {
      const before = remaining.slice(0, codeMatch.index)
      if (before) parts.push(before)
      parts.push(<code key={key++} className="bg-primary/10 text-primary px-1.5 py-0.5 rounded text-[12px] font-mono border border-primary/20">{codeMatch[1]}</code>)
      remaining = remaining.slice((codeMatch.index || 0) + codeMatch[0].length)
      continue
    }

    parts.push(remaining)
    break
  }

  return parts.length === 1 ? parts[0] : <>{parts}</>
}


const STEP_ICONS: Record<string, string> = {
  thinking: "💭",
  tool_call: "🔧",
  tool_result: "📊",
  reflection: "🔍",
}

const STEP_LABELS: Record<string, string> = {
  thinking: "思考",
  tool_call: "工具调用",
  tool_result: "工具结果",
  reflection: "反思",
}

function ReasoningStepItem({ step, defaultOpen }: { step: ReasoningStep; defaultOpen: boolean }) {
  const icon = STEP_ICONS[step.type] ?? "•"
  const label = STEP_LABELS[step.type] ?? step.type

  let summary: string
  if (step.type === "thinking" || step.type === "reflection") {
    summary = String((step.data as Record<string, unknown>).content ?? "")
  } else if (step.type === "tool_call") {
    const d = step.data as Record<string, unknown>
    summary = `${d.tool ?? "unknown"}(${JSON.stringify(d.arguments ?? {})})`
  } else if (step.type === "tool_result") {
    const d = step.data as Record<string, unknown>
    const output = String(d.output ?? d.result ?? "")
    summary = output.length > 120 ? output.slice(0, 120) + "…" : output
  } else {
    summary = JSON.stringify(step.data)
  }

  return (
    <details open={defaultOpen} className="group">
      <summary className="cursor-pointer flex items-center gap-1.5 py-1 text-xs text-muted-foreground hover:text-foreground select-none">
        <span>{icon}</span>
        <span className="font-medium">{label}</span>
        <span className="text-[11px] opacity-60 truncate max-w-[280px]">{summary}</span>
      </summary>
      <div className="ml-6 mt-1 mb-2 text-[11px] bg-muted/40 rounded-lg p-2 font-mono whitespace-pre-wrap break-all">
        {step.type === "tool_call"
          ? JSON.stringify(step.data, null, 2)
          : summary}
      </div>
    </details>
  )
}

function ReasoningChain({ steps, isComplete }: { steps: ReasoningStep[]; isComplete: boolean }) {
  const [isOpen, setIsOpen] = useState(!isComplete)

  useEffect(() => {
    if (isComplete) {
      setIsOpen(false)
    }
  }, [isComplete])

  if (!steps || steps.length === 0) return null

  return (
    <div className="mb-2 rounded-lg border border-primary/20 bg-primary/5 overflow-hidden">
      <details 
        open={isOpen} 
        onToggle={(e) => setIsOpen(e.currentTarget.open)}
        className="group"
      >
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-primary hover:bg-primary/10 flex items-center justify-between select-none">
          <span>🧠 推理链 ({steps.length} 步)</span>
          <span className="text-[10px] opacity-60 group-open:hidden">点击展开</span>
        </summary>
        <div className="px-3 pb-2 space-y-0.5">
          {steps.map((step, idx) => (
            <ReasoningStepItem
              key={`${step.type}-${idx}`}
              step={step}
              defaultOpen={idx === steps.length - 1}
            />
          ))}
        </div>
      </details>
    </div>
  )
}

function MessageBubble({ msg, isGenerating }: { msg: ChatMessage; isGenerating?: boolean }) {
  const isUser = msg.role === "user"
  const hasReasoning = !isUser && msg.reasoningSteps && msg.reasoningSteps.length > 0
  const hasContent = msg.content.trim().length > 0

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[85%]", isUser ? "" : "")}>
        {hasReasoning && (
          <ReasoningChain steps={msg.reasoningSteps!} isComplete={msg.content.length > 0} />
        )}
        {(!hasReasoning || hasContent || isUser) && (
          <div
            className={cn(
              "rounded-2xl px-4 py-2.5 text-sm leading-relaxed break-words",
              isUser
                ? "bg-primary text-primary-foreground rounded-br-md"
                : "bg-muted text-foreground rounded-bl-md"
            )}
          >
            {isUser ? msg.content : parseMarkdownToReact(msg.content, isGenerating)}
          </div>
        )}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-muted rounded-2xl rounded-bl-md px-4 py-3 flex gap-1.5 items-center">
        <span className="h-2 w-2 rounded-full bg-muted-foreground/60 animate-bounce" />
        <span className="h-2 w-2 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:150ms]" />
        <span className="h-2 w-2 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  )
}

export function AgentChat() {
  const { t } = useI18n()
  const { marketSubscription } = useDashboardRealtime()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // History sidebar
  const [showHistory, setShowHistory] = useState(false)
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
    })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading, scrollToBottom])

  useEffect(() => {
    if (open) textareaRef.current?.focus()
  }, [open])

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    const res = await listChatSessions(undefined, 50)
    if (res.data) setSessions(res.data)
    setHistoryLoading(false)
  }, [])

  const handleShowHistory = useCallback(() => {
    setShowHistory(true)
    loadHistory()
  }, [loadHistory])

  const handleNewChat = useCallback(() => {
    setMessages([])
    setSessionId(undefined)
    setShowHistory(false)
  }, [])

  const handleLoadSession = useCallback(async (sid: string) => {
    const res = await getChatSessionMessages(sid, 200)
    if (res.data) {
      const loaded: ChatMessage[] = res.data.map((r: ChatMessageRecord) => ({
        id: r.id,
        role: r.role,
        content: r.content,
        timestamp: new Date(r.created_at).getTime(),
        reasoningSteps: Array.isArray(r.extra?.reasoningSteps)
          ? (r.extra.reasoningSteps as ReasoningStep[])
          : undefined,
      }))
      setMessages(loaded)
      setSessionId(sid)
    }
    setShowHistory(false)
  }, [])

  const handleDeleteSession = useCallback(async (sid: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await deleteChatSession(sid)
    setSessions((prev) => prev.filter((s) => s.id !== sid))
    if (sessionId === sid) {
      setMessages([])
      setSessionId(undefined)
    }
  }, [sessionId])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput("")
    if (textareaRef.current) textareaRef.current.style.height = ""
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    let response = ""
    let hasError = false
    const assistantId = crypto.randomUUID()
    const reasoningSteps: ReasoningStep[] = []

    const chatContext = {
      symbol: marketSubscription.symbol,
      timeframe: marketSubscription.interval,
      exchange: marketSubscription.exchange,
      market_type: marketSubscription.marketType,
    }

    const chatResult = await sendAgentChat(text, (event) => {
      const isReasoningEvent =
        event.type === "thinking" ||
        event.type === "tool_call" ||
        event.type === "tool_result" ||
        event.type === "reflection"

      if (isReasoningEvent) {
        reasoningSteps.push({
          type: event.type as ReasoningStep["type"],
          data: typeof event.data === "object" && event.data !== null
            ? (event.data as Record<string, unknown>)
            : {},
          timestamp: Date.now(),
        })
        updateAssistantMessage()
      } else if (
        event.type === "text_delta" ||
        event.type === "text" ||
        event.type === "content"
      ) {
        const chunk =
          typeof event.data === "object" && event.data !== null
            ? (event.data as Record<string, unknown>).text ?? ""
            : event.data
        response += String(chunk)
        updateAssistantMessage()
      } else if (event.type === "error") {
        hasError = true
      }

      function updateAssistantMessage() {
        setMessages((prev) => {
          const updated = [...prev]
          const lastIdx = updated.findIndex((m) => m.id === assistantId)
          const assistantMsg: ChatMessage = {
            id: assistantId,
            role: "assistant",
            content: response,
            timestamp: Date.now(),
            reasoningSteps: [...reasoningSteps],
          }
          if (lastIdx >= 0) {
            updated[lastIdx] = assistantMsg
          } else {
            updated.push(assistantMsg)
          }
          return updated
        })
      }
    }, chatContext, sessionId)
    if (chatResult.sessionId) setSessionId(chatResult.sessionId)

    if (!response) {
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: hasError
            ? t("agent.errorOccurred")
            : t("agent.noResponse"),
          timestamp: Date.now(),
        },
      ])
    }

    setLoading(false)

    // Auto-save messages to backend
    setMessages((prev) => {
      if (chatResult.sessionId || sessionId) {
        const sid = chatResult.sessionId ?? sessionId!
        saveChatSessionMessages(sid, prev.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          extra: m.reasoningSteps ? { reasoningSteps: m.reasoningSteps } : {},
        })))
      }
      return prev
    })
  }, [input, loading, t, sessionId, marketSubscription])

  const handleClear = useCallback(() => {
    setMessages([])
    setSessionId(undefined)
  }, [])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend]
  )

  // Global keyboard shortcut: Ctrl/Cmd + J to toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "j") {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
      if (e.key === "Escape" && open) {
        setOpen(false)
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [open])

  return (
    <>
      {/* Floating Action Button */}
      <button
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "fixed bottom-6 right-6 z-50 flex items-center justify-center",
          "h-14 w-14 rounded-full transition-all duration-300",
          "bg-white text-black hover:scale-110 active:scale-95",
          "shadow-[0_0_15px_rgba(0,0,0,0.2)] hover:shadow-[0_0_25px_rgba(0,0,0,0.3)]",
          open && "scale-0 opacity-0 pointer-events-none"
        )}
        title={`${t("agent.title")} (Ctrl+J)`}
      >
        <img 
          src="/logo2.svg" 
          alt="Logo" 
          className="h-7 w-7 transition-all duration-500 animate-logo-glow" 
        />
        {messages.length > 0 && (
          <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-emerald-500 text-[10px] font-bold text-white flex items-center justify-center shadow-lg">
            {messages.filter((m) => m.role === "assistant").length}
          </span>
        )}
      </button>

      {/* Chat Panel */}
      <div
        className={cn(
          "fixed bottom-6 right-6 z-50 flex flex-col",
          "w-[520px] h-[calc(100vh-100px)]",
          "rounded-2xl border border-border bg-card shadow-2xl",
          "transition-all duration-300 origin-bottom-right",
          open
            ? "scale-100 opacity-100"
            : "scale-75 opacity-0 pointer-events-none"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2.5">
            {showHistory ? (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setShowHistory(false)}
                title={t("agent.backToChat")}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                <img src="/logo2.svg" alt="Logo" className="h-5 w-5 brightness-0 invert dark:invert-0 grayscale opacity-80" />
              </div>
            )}
            <div>
              <h3 className="text-sm font-semibold">
                {showHistory ? t("agent.history") : t("agent.title")}
              </h3>
              <p className="text-[11px] text-muted-foreground leading-none mt-0.5">
                {showHistory ? "" : loading ? t("agent.thinking") : t("agent.subtitle")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {!showHistory && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={handleNewChat}
                  title={t("agent.newChat")}
                >
                  <Plus className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={handleShowHistory}
                  title={t("agent.history")}
                >
                  <History className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={handleClear}
                  title={t("agent.clear")}
                  disabled={messages.length === 0}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setOpen(false)}
              title={t("agent.minimize")}
            >
              <Minus className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setOpen(false)}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* History Sidebar */}
        {showHistory ? (
          <div className="flex-1 overflow-y-auto">
            {historyLoading ? (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                {t("common.loading")}
              </div>
            ) : sessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
                <History className="h-8 w-8 opacity-30" />
                <p className="text-sm">{t("agent.historyEmpty")}</p>
              </div>
            ) : (
              <div className="py-2 divide-y divide-border">
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    className={cn(
                      "w-full text-left px-4 py-3 hover:bg-muted/60 transition-colors flex items-start justify-between gap-2",
                      s.id === sessionId && "bg-muted/40"
                    )}
                    onClick={() => handleLoadSession(s.id)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">
                        {s.title || s.id.slice(0, 16)}
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {s.message_count ?? 0} {t("agent.sessionMessages")} · {new Date(s.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={(e) => handleDeleteSession(s.id, e)}
                      title={t("agent.deleteSession")}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
        <>
        <div className="flex-1 overflow-y-auto px-4" ref={scrollRef}>
          <div className="py-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-center py-12 space-y-3">
                <div className="mx-auto h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <img src="/logo2.svg" alt="Logo" className="h-8 w-8 brightness-0 invert dark:invert-0 grayscale opacity-80" />
                </div>
                <div>
                  <p className="text-sm font-medium">{t("agent.welcomeTitle")}</p>
                  <p className="text-xs text-muted-foreground mt-1 max-w-[260px] mx-auto">
                    {t("agent.welcomeDesc")}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 justify-center pt-2">
                  {[
                    t("agent.quickStrategy"),
                    t("agent.quickAnalysis"),
                    t("agent.quickExplain"),
                  ].map((q) => (
                    <button
                      key={q}
                      className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-muted transition-colors"
                      onClick={() => {
                        setInput(q)
                        textareaRef.current?.focus()
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, idx) => (
              <MessageBubble key={msg.id} msg={msg} isGenerating={loading && idx === messages.length - 1} />
            ))}
            {loading && <TypingIndicator />}
          </div>
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-border shrink-0">
          <form
            className="flex gap-2 items-end"
            onSubmit={(e) => {
              e.preventDefault()
              handleSend()
            }}
          >
            <textarea
              ref={textareaRef}
              placeholder={t("agent.inputPlaceholder")}
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                const el = e.target
                el.style.height = "0"
                el.style.height = `${Math.min(el.scrollHeight, 200)}px`
              }}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={1}
              className="flex-1 max-h-[200px] min-h-[40px] resize-none overflow-y-auto rounded-xl bg-muted/50 border-0 px-3 py-2.5 text-sm leading-[1.6] text-foreground shadow-none outline-none placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring"
            />
            <Button
              type="submit"
              size="icon"
              className="h-10 w-10 rounded-xl shrink-0 mb-0.5"
              disabled={loading || !input.trim()}
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
          <p className="text-[10px] text-muted-foreground text-center mt-2">
            Ctrl+J {t("agent.toggleShortcut")}
          </p>
        </div>
        </>
        )}
      </div>
    </>
  )
}
