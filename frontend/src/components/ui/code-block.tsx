'use client'

import { useState } from 'react'
import { Button } from './button'
import { Check, Copy } from 'lucide-react'

interface CodeBlockProps {
  code: string
  language?: string
  showCopyButton?: boolean
}

export function CodeBlock({ code, language = 'json', showCopyButton = true }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy text: ', err)
    }
  }

  return (
    <div className="relative">
      {showCopyButton && (
        <Button
          variant="outline"
          size="sm"
          className="absolute right-2 top-2 z-10"
          onClick={copyToClipboard}
        >
          {copied ? (
            <>
              <Check className="h-4 w-4 mr-2" />
              Copied!
            </>
          ) : (
            <>
              <Copy className="h-4 w-4 mr-2" />
              Copy
            </>
          )}
        </Button>
      )}
      <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto">
        <code className={`language-${language}`}>{code}</code>
      </pre>
    </div>
  )
}