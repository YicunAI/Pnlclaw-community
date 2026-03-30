"use client"

import React, { createContext, useContext, useEffect, useMemo, useState } from "react"
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  isLocale,
  resolveMessage,
} from "@/lib/i18n"
import type { Locale, MessageKey, TranslateParams } from "@/lib/i18n/types"

type I18nContextValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: MessageKey, params?: TranslateParams) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>(DEFAULT_LOCALE)

  useEffect(() => {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY)
    if (stored && isLocale(stored)) {
      setLocale(stored)
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
    document.documentElement.lang = locale
  }, [locale])

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key: MessageKey, params?: TranslateParams) =>
        resolveMessage(locale, key, params),
    }),
    [locale]
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18nContext() {
  const value = useContext(I18nContext)
  if (!value) {
    throw new Error("useI18nContext must be used inside I18nProvider")
  }
  return value
}
