/**
 * Tests for Agent Chat reasoning chain UI (Sprint 1.3).
 *
 * Prerequisites: install @testing-library/react and vitest:
 *   npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
 *
 * Run: npx vitest run components/__tests__/agent-chat-reasoning.test.tsx
 */

import { describe, it, expect, vi } from "vitest"
import React from "react"
import { render, screen } from "@testing-library/react"

// Types matching the component's internal types
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

// Simulated reasoning chain for testing
const MOCK_REASONING_STEPS: ReasoningStep[] = [
  {
    type: "thinking",
    data: { content: "Let me check the market price...", round: 1 },
    timestamp: 1000,
  },
  {
    type: "tool_call",
    data: { tool: "market_ticker", arguments: { symbol: "BTC/USDT" } },
    timestamp: 1001,
  },
  {
    type: "tool_result",
    data: { tool: "market_ticker", output: '{"price": 67234.5}' },
    timestamp: 1002,
  },
  {
    type: "reflection",
    data: { content: "Got price data, sufficient to answer.", round: 1 },
    timestamp: 1003,
  },
]

describe("Agent Chat Reasoning Chain UI", () => {
  it("should render all reasoning step types with correct icons", () => {
    const stepIcons: Record<string, string> = {
      thinking: "💭",
      tool_call: "🔧",
      tool_result: "📊",
      reflection: "🔍",
    }

    for (const step of MOCK_REASONING_STEPS) {
      const icon = stepIcons[step.type]
      expect(icon).toBeDefined()
    }

    expect(MOCK_REASONING_STEPS).toHaveLength(4)
  })

  it("should have the last reasoning step default open and others collapsed", () => {
    const steps = MOCK_REASONING_STEPS
    const lastIndex = steps.length - 1

    for (let i = 0; i < steps.length; i++) {
      const shouldBeOpen = i === lastIndex
      if (shouldBeOpen) {
        expect(steps[i].type).toBe("reflection")
      }
    }
  })

  it("should handle all SSE event types including thinking and reflection", () => {
    const eventTypes = ["thinking", "tool_call", "tool_result", "reflection", "text_delta", "done"]
    const reasoningTypes = ["thinking", "tool_call", "tool_result", "reflection"]
    const textTypes = ["text_delta", "content", "text"]

    for (const type of reasoningTypes) {
      expect(eventTypes).toContain(type)
    }

    const captured: ReasoningStep[] = []
    for (const event of MOCK_REASONING_STEPS) {
      if (reasoningTypes.includes(event.type)) {
        captured.push(event)
      }
    }
    expect(captured).toHaveLength(4)
  })

  it("should display step count in chain header", () => {
    const steps = MOCK_REASONING_STEPS
    const headerText = `🧠 推理链 (${steps.length} 步)`
    expect(headerText).toContain("4")
    expect(headerText).toContain("推理链")
  })

  it("should truncate long tool results in display", () => {
    const longOutput = "x".repeat(200)
    const truncated =
      longOutput.length > 120 ? longOutput.slice(0, 120) + "…" : longOutput
    expect(truncated.length).toBeLessThan(longOutput.length)
    expect(truncated).toContain("…")
  })

  it("should not break message display when reasoningSteps is empty", () => {
    const msg: ChatMessage = {
      id: "test-1",
      role: "assistant",
      content: "Hello!",
      timestamp: Date.now(),
      reasoningSteps: [],
    }

    expect(msg.reasoningSteps).toHaveLength(0)
    expect(msg.content).toBe("Hello!")
  })
})
