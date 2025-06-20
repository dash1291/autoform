import { getDocBySlug } from '@/lib/docs'
import { notFound } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'

export default async function DocsPage() {
  const doc = await getDocBySlug('')
  
  if (!doc) {
    notFound()
  }

  return (
    <AuthGuard>
      <div 
        className="prose prose-gray max-w-none"
        dangerouslySetInnerHTML={{ __html: doc.content }}
      />
    </AuthGuard>
  )
}