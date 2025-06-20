import DocsClientLayout from './DocsClientLayout'
import Navbar from './Navbar'

interface DocsLayoutProps {
  children: React.ReactNode
}

export default function DocsLayout({ children }: DocsLayoutProps) {
  return (
    <>
      <Navbar />
      <DocsClientLayout>{children}</DocsClientLayout>
    </>
  )
}