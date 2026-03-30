"use client"

import React from "react"

export function parseInlineMarkdown(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let remaining = text
  let key = 0

  while (remaining) {
    const strongMatch = remaining.match(/\*\*(.+?)\*\*/)
    const codeMatch = remaining.match(/`(.+?)`/)
    const italicMatch = remaining.match(/\*(.+?)\*/)

    const matches = [
      strongMatch ? { type: "strong" as const, match: strongMatch } : null,
      codeMatch ? { type: "code" as const, match: codeMatch } : null,
      italicMatch ? { type: "italic" as const, match: italicMatch } : null,
    ].filter((item): item is { type: "strong" | "code" | "italic"; match: RegExpMatchArray } => item !== null)

    if (matches.length === 0) break

    matches.sort((a, b) => (a.match.index ?? 0) - (b.match.index ?? 0))
    const nextMatch = matches[0]
    const matchIndex = nextMatch.match.index ?? 0
    const before = remaining.slice(0, matchIndex)
    if (before) parts.push(before)

    if (nextMatch.type === "strong") {
      parts.push(
        <strong key={key++} className="font-semibold text-foreground">
          {nextMatch.match[1]}
        </strong>
      )
    } else if (nextMatch.type === "code") {
      parts.push(
        <code
          key={key++}
          className="rounded-md border border-primary/20 bg-primary/10 px-1.5 py-0.5 font-mono text-[12px] text-primary"
        >
          {nextMatch.match[1]}
        </code>
      )
    } else {
      parts.push(
        <em key={key++} className="italic text-foreground/80">
          {nextMatch.match[1]}
        </em>
      )
    }

    remaining = remaining.slice(matchIndex + nextMatch.match[0].length)
  }

  if (remaining) parts.push(remaining)
  return parts.length === 1 ? parts[0] : <>{parts}</>
}

function renderStepCard(line: string, key: string) {
  const match = line.match(/^Step\s*(\d+)\s*[:.-]?\s*(.+)$/i)
  if (!match) return null

  return (
    <div
      key={key}
      className="my-4 rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent px-4 py-3 shadow-sm"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground shadow-sm">
          {match[1]}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-primary/80">
            Step {match[1]}
          </p>
          <div className="mt-1 text-[14px] font-medium leading-6 text-foreground">
            {parseInlineMarkdown(match[2])}
          </div>
        </div>
      </div>
    </div>
  )
}

export function parseRichMarkdownToReact(text: string, isGenerating?: boolean): React.ReactNode[] {
  const elements: React.ReactNode[] = []
  const lines = text.replace(/<tool_call>[\s\S]*?<\/tool_call>/g, "").split("\n")
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    if (!trimmed) {
      elements.push(<div key={`spacer-${i}`} className="h-3" />)
      i++
      continue
    }

    const stepCard = renderStepCard(trimmed, `step-${i}`)
    if (stepCard) {
      elements.push(stepCard)
      i++
      continue
    }

    const codeFenceMatch = trimmed.match(/^```([\w-]+)?$/)
    if (codeFenceMatch) {
      const language = codeFenceMatch[1] || "text"
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i])
        i++
      }
      if (i < lines.length) i++
      const codeContent = codeLines.join("\n")
      elements.push(
        <div key={`code-${i}`} className="my-4 overflow-hidden rounded-2xl border border-border bg-[#0b1020] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
          <div className="flex items-center justify-between border-b border-white/5 bg-white/[0.03] px-3 py-2">
            <div className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-400/80" />
              <span className="h-2 w-2 rounded-full bg-amber-400/80" />
              <span className="h-2 w-2 rounded-full bg-emerald-400/80" />
            </div>
            <span className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{language}</span>
          </div>
          <pre className="overflow-x-auto px-4 py-3 text-[12px] leading-6 text-slate-100">
            <code>{codeContent}</code>
          </pre>
        </div>
      )
      continue
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""))
        i++
      }
      elements.push(
        <blockquote
          key={`quote-${i}`}
          className="my-4 rounded-2xl border border-sky-500/15 bg-sky-500/5 px-4 py-3 text-[13px] leading-6 text-sky-50/90 shadow-sm"
        >
          <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.16em] text-sky-300/80">
            Insight
          </div>
          <div className="space-y-2 text-muted-foreground">
            {quoteLines.map((quoteLine, idx) => (
              <p key={`quote-line-${idx}`}>{parseInlineMarkdown(quoteLine)}</p>
            ))}
          </div>
        </blockquote>
      )
      continue
    }

    if (trimmed.startsWith("|") && trimmed.includes("|")) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        if (!lines[i].match(/^[\s|:-]+$/)) tableLines.push(lines[i])
        i++
      }
      const rows = tableLines.map((row) => row.split("|").map((cell) => cell.trim()).filter(Boolean))
      if (rows.length > 0) {
        elements.push(
          <div key={`table-${i}`} className="my-5 overflow-hidden rounded-2xl border border-border bg-card/60 shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-[12px]">
                <thead className="bg-muted/50">
                  <tr>
                    {rows[0].map((cell, idx) => (
                      <th
                        key={`th-${i}-${idx}`}
                        className="border-b border-border px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground"
                      >
                        {parseInlineMarkdown(cell)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(1).map((row, rowIdx) => (
                    <tr key={`tr-${i}-${rowIdx}`} className="border-b border-border/70 last:border-b-0 hover:bg-muted/30">
                      {row.map((cell, cellIdx) => (
                        <td key={`td-${i}-${rowIdx}-${cellIdx}`} className="px-4 py-3 align-top text-[13px] leading-6 text-foreground/90">
                          {parseInlineMarkdown(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      }
      continue
    }

    if (trimmed.startsWith("### ")) {
      elements.push(
        <h3 key={`h3-${i}`} className="mt-6 mb-3 flex items-center gap-2 text-[15px] font-semibold text-primary">
          <span className="h-2 w-2 rounded-full bg-primary/70" />
          {parseInlineMarkdown(trimmed.replace(/^###\s*/, ""))}
        </h3>
      )
      i++
      continue
    }

    if (trimmed.startsWith("## ")) {
      elements.push(
        <h2 key={`h2-${i}`} className="mt-7 mb-3 border-b border-border pb-2 text-[17px] font-semibold text-foreground">
          {parseInlineMarkdown(trimmed.replace(/^##\s*/, ""))}
        </h2>
      )
      i++
      continue
    }

    if (trimmed.startsWith("# ")) {
      elements.push(
        <h1 key={`h1-${i}`} className="mt-8 mb-4 text-[20px] font-bold tracking-tight text-foreground">
          {parseInlineMarkdown(trimmed.replace(/^#\s*/, ""))}
        </h1>
      )
      i++
      continue
    }

    if (/^[-*]\s/.test(trimmed)) {
      const listItems: string[] = []
      while (i < lines.length && /^[-*]\s/.test(lines[i].trim())) {
        listItems.push(lines[i].trim().replace(/^[-*]\s/, ""))
        i++
      }
      elements.push(
        <ul key={`ul-${i}`} className="my-4 space-y-2">
          {listItems.map((item, idx) => (
            <li key={`li-${i}-${idx}`} className="flex items-start gap-3 text-[14px] leading-7 text-foreground/90">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
              <span className="min-w-0 flex-1">{parseInlineMarkdown(item)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    if (/^\d+\.\s/.test(trimmed)) {
      const listItems: string[] = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        listItems.push(lines[i].trim().replace(/^\d+\.\s/, ""))
        i++
      }
      elements.push(
        <ol key={`ol-${i}`} className="my-4 space-y-3">
          {listItems.map((item, idx) => (
            <li key={`oli-${i}-${idx}`} className="flex items-start gap-3 rounded-xl border border-border/70 bg-background/40 px-3 py-2 text-[14px] leading-7 text-foreground/90">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[12px] font-semibold text-primary">
                {idx + 1}
              </span>
              <span className="min-w-0 flex-1">{parseInlineMarkdown(item)}</span>
            </li>
          ))}
        </ol>
      )
      continue
    }

    if (trimmed === "---" || trimmed === "***") {
      elements.push(<hr key={`hr-${i}`} className="my-6 border-border/50" />)
      i++
      continue
    }

    elements.push(
      <p key={`p-${i}`} className="my-3 text-[14px] leading-7 text-foreground/90">
        {parseInlineMarkdown(line)}
        {isGenerating && i === lines.length - 1 && (
          <span className="ml-1 inline-block h-4 w-2 translate-y-px animate-[pulse_0.8s_cubic-bezier(0.4,0,0.6,1)_infinite] rounded-sm bg-primary align-middle" />
        )}
      </p>
    )
    i++
  }

  return elements
}
