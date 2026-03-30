import type { enMessages } from "./messages/en"

export type Locale = "en" | "zh-CN"

export type MessageKey = keyof typeof enMessages
export type MessageMap = Record<MessageKey, string>
export type TranslateParams = Record<string, string | number>
