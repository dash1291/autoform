import { getDocBySlug } from '@/lib/docs'
import { notFound } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'
import DocsContentWrapper from '@/components/DocsContentWrapper'

export default async function DocsPage() {
  const doc = await getDocBySlug('')
  
  if (!doc) {
    notFound()
  }

  return (
    <AuthGuard>
      <DocsContentWrapper content={doc.content} />
    </AuthGuard>
  )
}