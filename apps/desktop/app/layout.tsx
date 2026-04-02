import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import { I18nProvider } from "@/components/i18n/i18n-provider"
import { AuthProvider } from "@/components/auth/AuthProvider"
import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "PnLClaw - Crypto Quantitative Trading Platform",
  description:
    "Local-first crypto quantitative research, backtesting, and paper trading platform",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`} suppressHydrationWarning>
        <AuthProvider>
          <I18nProvider>{children}</I18nProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
