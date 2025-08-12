import { getDocBySlug } from '@/lib/docs'
import { notFound } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'
import DocsContentWrapper from '@/components/DocsContentWrapper'

export default async function AwsSetupPage() {
  const doc = await getDocBySlug('aws-setup')
  
  if (!doc) {
    notFound()
  }

  return (
    <AuthGuard>
      <DocsContentWrapper content={doc.content} />
    </AuthGuard>
  )
}