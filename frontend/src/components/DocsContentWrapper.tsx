'use client'

import { useEffect, useRef } from 'react'

interface DocsContentWrapperProps {
  content: string
}

export default function DocsContentWrapper({ content }: DocsContentWrapperProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (contentRef.current) {
      // Add click event listeners to all copy buttons
      const copyButtons = contentRef.current.querySelectorAll('.copy-policy-btn')
      
      copyButtons.forEach((button) => {
        button.addEventListener('click', handleCopy)
      })

      // Cleanup function
      return () => {
        copyButtons.forEach((button) => {
          button.removeEventListener('click', handleCopy)
        })
      }
    }
  }, [content])

  const handleCopy = async (event: Event) => {
    const button = event.currentTarget as HTMLButtonElement
    const contentToCopy = button.getAttribute('data-copy-content')
    
    if (!contentToCopy) return

    try {
      // Decode HTML entities back to original characters
      const decodedContent = contentToCopy
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>');
      
      await navigator.clipboard.writeText(decodedContent)
      
      // Update button text temporarily
      const originalHTML = button.innerHTML
      button.innerHTML = `
        <svg class="check-icon h-4 w-4 mr-2 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
        </svg>
        Copied!
      `
      button.classList.add('bg-green-50', 'border-green-300', 'text-green-700')
      
      // Reset after 2 seconds
      setTimeout(() => {
        button.innerHTML = originalHTML
        button.classList.remove('bg-green-50', 'border-green-300', 'text-green-700')
      }, 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  return (
    <div 
      ref={contentRef}
      className="prose prose-gray max-w-none"
      dangerouslySetInnerHTML={{ __html: content }}
    />
  )
}
