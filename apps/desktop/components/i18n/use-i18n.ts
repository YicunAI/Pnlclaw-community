"use client"

import { useI18nContext } from "./i18n-provider"

export function useI18n() {
  return useI18nContext()
}
