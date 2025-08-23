'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { ChevronRight, Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'

const docSections = [
  {
    title: 'Documentation',
    slug: 'docs',
    items: [
      { title: 'Overview', slug: 'overview', href: '/docs' },
      { title: 'AWS Setup', slug: 'aws-setup', href: '/docs/aws-setup' },
      { title: 'Cost Breakdown', slug: 'cost-breakdown', href: '/docs/cost-breakdown' },
    ]
  }
]

interface DocsClientLayoutProps {
  children: React.ReactNode
}

export default function DocsClientLayout({ children }: DocsClientLayoutProps) {
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="py-8">
      <div className="max-w-6xl mx-auto w-full flex flex-col lg:flex-row relative">
        {/* Mobile sidebar toggle */}
        <div className="lg:hidden sticky top-0 z-40 bg-background border-b px-4 py-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>

        {/* Sidebar overlay for mobile */}
        {sidebarOpen && (
          <div
            className="lg:hidden fixed inset-0 z-30"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sidebar */}
        <aside
          className={cn(
            // On desktop: static, column, not fixed
            "lg:block lg:relative lg:w-64 lg:border-r lg:transition-none",
            // On mobile: fixed, slide in/out
            "fixed top-0 bottom-0 z-30 w-64 bg-background border-r overflow-y-auto transition-transform lg:translate-x-0",
            sidebarOpen ? "translate-x-0" : "-translate-x-full",
            "lg:sticky lg:top-0 lg:h-[calc(100vh-8rem)]"
          )}
        >
          <nav className="px-6 pb-6">
            {docSections.map((section) => (
              <div key={section.slug} className="mb-6">
                <h3 className="text-sm font-semibold uppercase tracking-wider mb-2">
                  {section.title}
                </h3>
                <ul className="space-y-1">
                  {section.items.map((item) => {
                    const isActive = pathname === item.href
                    return (
                      <li key={item.slug}>
                        <Link
                          href={item.href}
                          onClick={() => setSidebarOpen(false)}
                          className={cn(
                            "block px-3 py-2 text-sm rounded-md transition-colors",
                            isActive
                              ? "text-foreground font-medium"
                              : "text-muted-foreground hover:text-foreground"
                          )}
                        >
                          {item.title}
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 flex flex-col items-center">
          <div className="w-full max-w-4xl mx-auto px-6 py-8 lg:py-12">
            {/* Breadcrumb */}
            <nav className="flex items-center text-sm mb-8">
              <Link href="/" className="hover:text-muted-foreground">
                Home
              </Link>
              <ChevronRight className="h-4 w-4 mx-2" />
              <Link href="/docs" className="hover:text-muted-foreground">
                Docs
              </Link>
              {pathname !== '/docs' && (
                <>
                  <ChevronRight className="h-4 w-4 mx-2" />
                  <span className="">
                    {pathname.split('/').pop()?.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </span>
                </>
              )}
            </nav>

            {/* Page content */}
            <article className="prose prose-gray max-w-none">
              {children}
            </article>
          </div>
        </main>
      </div>
    </div>
  )
}