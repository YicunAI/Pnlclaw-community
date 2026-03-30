import { enMessages } from "./messages/en"
import { zhCNMessages } from "./messages/zh-CN"
import type { Locale, MessageKey, TranslateParams } from "./types"

export const LOCALE_STORAGE_KEY = "pnlclaw-locale"
export const DEFAULT_LOCALE: Locale = "en"

export const messages = {
  en: enMessages,
  "zh-CN": zhCNMessages,
} as const

export function isLocale(value: string): value is Locale {
  return value === "en" || value === "zh-CN"
}

export function formatMessage(template: string, params?: TranslateParams): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = params[key]
    return value === undefined ? `{${key}}` : String(value)
  })
}

export function resolveMessage(
  locale: Locale,
  key: MessageKey,
  params?: TranslateParams
): string {
  const template = messages[locale][key] ?? messages[DEFAULT_LOCALE][key] ?? key
  return formatMessage(template, params)
}
