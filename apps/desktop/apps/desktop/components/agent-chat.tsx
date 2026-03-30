"use client"

import React, { useState, useCallback, useRef, useEffect } from "react"
import { Bot, X, Send, Trash2, Minus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { sendAgentChat } from "@/lib/api-client"
import { useI18n } from "@/components/i18n/use-i18n"

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: number
}

function parseMarkdownToReact(text: string): React.ReactNode[] {
  const elements: React.ReactNode[] = []
  const lines = text.split('\n')
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // 标题
    if (line.startsWith('###')) {
      elements.push(<h3 key={i} className="text-base font-bold mt-3 mb-2">{line.replace(/^###\s*/, '')}</h3>)
      i++
      continue
    }
    if (line.startsWith('##')) {
      elements.push(<h2 key={i} className="text-lg font-bold mt-3 mb-2">{line.replace(/^##\s*/, '')}</h2>)
      i++
      continue
    }
    if (line.startsWith('#')) {
      elements.push(<h1 key={i} className="text-xl font-bold mt-3 mb-2">{line.replace(/^#\s*/, '')}</h1>)
      i++
      continue
    }

    // 列表项
    if (line.match(/^[-*]\s/)) {
      const listItems: string[] = []
      while (i < lines.length && lines[i].match(/^[-*]\s/)) {
        listItems.push(lines[i].replace(/^[-*]\s/, ''))
        i++
      }
      elements.push(
        <ul key={i} className="list-disc list-inside space-y-1 my-2">
          {listItems.map((item, idx) => (
            <li key={idx}>{parseInlineMarkdown(item)}</li>
          ))}
        </ul>
      )
      continue
    }

    // 表格
    if (line.includes('|')) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].includes('|')) {
        if (!lines[i].match(/^[\s|:-]+$/)) { // 跳过分隔线
          tableLines.push(lines[i])
        }
        i++
      }
      if (tableLines.length > 0) {
        const rows = tableLines.map(l => l.split('|').map(c => c.trim()).filter(c => c))
        elements.push(
          <div key={i} className="overflow-x-auto my-2">
            <table className="min-w-full border-collapse border border-border text-xs">
              <thead>
                <tr className="bg-muted">
                  {rows[0].map((cell, idx) => (
                    <th key={idx} className="border border-border px-2 py-1 text-left font-semibold">
                      {parseInlineMarkdown(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(1).map((row, rowIdx) => (
                  <tr key={rowIdx}>
                    {row.map((cell, cellIdx) => (
                      <td key={cellIdx} className="border border-border px-2 py-1">
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

    // 空行
    if (line.trim() === '') {
      elements.push(<br key={i} />)
      i++
      continue
    }

    // 普通段落
    elements.push(<p key={i} className="my-1">{parseInlineMarkdown(line)}</p>)
    i++
  }

  return elements
}

function parseInlineMarkdown(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let remaining = text
  let key = 0

  while (remaining) {
    // 粗体 **text**
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/)
    if (boldMatch) {
      const before = remaining.slice(0, boldMatch.index)
      if (before) parts.push(before)
      parts.push(<strong key={key++} className="font-bold">{boldMatch[1]}</strong>)
      remaining = remaining.slice((boldMatch.index || 0) + boldMatch[0].length)
      continue
    }

    // 斜体 *text*
    const italicMatch = remaining.match(/\*(.+?)\*/)
    if (italicMatch) {
      const before = remaining.slice(0, italicMatch.index)
      if (before) parts.push(before)
      parts.push(<em key={key++} className="italic">{italicMatch[1]}</em>)
      remaining = remaining.slice((italicMatch.index || 0) + italicMatch[0].length)
      continue
    }

    // 行内代码 `code`
    const codeMatch = remaining.match(/`(.+?)`/)
    if (codeMatch) {
      const before = remaining.slice(0, codeMatch.index)
      if (before) parts.push(before)
      parts.push(<code key={key++} className="bg-muted px-1 py-0.5 rounded text-xs font-mono">{codeMatch[1]}</code>)
      remaining = remaining.slice((codeMatch.index || 0) + codeMatch[0].length)
      continue
    }

    // 没有更多格式，添加剩余文本
    parts.push(remaining)
    break
  }

  return parts.length === 1 ? parts[0] : <>{parts}</>
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user"
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed break-words",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-md"
            : "bg-muted text-foreground rounded-bl-md"
        )}
      >
        {isUser ? msg.content : parseMarkdownToReact(msg.content)}
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
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

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
    if (open) inputRef.current?.focus()
  }, [open])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput("")
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

    await sendAgentChat(text, (event) => {
      if (
        event.type === "text_delta" ||
        event.type === "text" ||
        event.type === "content"
      ) {
        const chunk =
          typeof event.data === "object" && event.data !== null
            ? (event.data as Record<string, unknown>).text ?? ""
            : event.data
        response += String(chunk)

        setMessages((prev) => {
          const updated = [...prev]
          const lastIdx = updated.findIndex((m) => m.id === assistantId)
          const assistantMsg: ChatMessage = {
            id: assistantId,
            role: "assistant",
            content: response,
            timestamp: Date.now(),
          }
          if (lastIdx >= 0) {
            updated[lastIdx] = assistantMsg
          } else {
            updated.push(assistantMsg)
          }
          return updated
        })
      } else if (event.type === "error") {
        hasError = true
      }
    })

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
  }, [input, loading, t])

  const handleClear = useCallback(() => {
    setMessages([])
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
          "h-14 w-14 rounded-full shadow-lg transition-all duration-300",
          "bg-primary text-primary-foreground hover:scale-105 active:scale-95",
          "hover:shadow-primary/25 hover:shadow-xl",
          open && "scale-0 opacity-0 pointer-events-none"
        )}
        title={`AI ${t("agent.title")} (Ctrl+J)`}
      >
        <Bot className="h-6 w-6" />
        {messages.length > 0 && (
          <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-emerald-500 text-[10px] font-bold text-white flex items-center justify-center">
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
            <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="text-sm font-semibold">{t("agent.title")}</h3>
              <p className="text-[11px] text-muted-foreground leading-none mt-0.5">
                {loading ? t("agent.thinking") : t("agent.subtitle")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
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

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4" ref={scrollRef}>
          <div className="py-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-center py-12 space-y-3">
                <div className="mx-auto h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <Bot className="h-6 w-6 text-primary" />
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
                        inputRef.current?.focus()
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
            {loading && <TypingIndicator />}
          </div>
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-border shrink-0">
          <form
            className="flex gap-2 items-center"
            onSubmit={(e) => {
              e.preventDefault()
              handleSend()
            }}
          >
            <Input
              ref={inputRef}
              placeholder={t("agent.inputPlaceholder")}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              className="flex-1 h-10 rounded-xl bg-muted/50 border-0 focus-visible:ring-1"
            />
            <Button
              type="submit"
              size="icon"
              className="h-10 w-10 rounded-xl shrink-0"
              disabled={loading || !input.trim()}
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
          <p className="text-[10px] text-muted-foreground text-center mt-2">
            Ctrl+J {t("agent.toggleShortcut")}
          </p>
        </div>
      </div>
    </>
  )
}
