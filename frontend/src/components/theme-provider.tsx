"use client"

import * as React from "react"
import { ThemeProvider as NextThemesProvider } from "next-themes"
// import { type ThemeProviderProps } from "next-themes/dist/types"

interface ThemeProviderProps {
  children: React.ReactNode
  attribute?: string
  defaultTheme?: string
  forcedTheme?: string
  enableSystem?: boolean
  disableTransitionOnChange?: boolean
}

export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  return <NextThemesProvider {...props as any}>{children}</NextThemesProvider>
}