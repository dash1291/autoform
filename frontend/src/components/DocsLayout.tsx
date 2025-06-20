import DocsClientLayout from './DocsClientLayout'

interface DocsLayoutProps {
  children: React.ReactNode
}

export default function DocsLayout({ children }: DocsLayoutProps) {
  return <DocsClientLayout>{children}</DocsClientLayout>
}