import { getDocBySlug } from '@/lib/docs'
import { notFound } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'

export default async function AwsSetupPage() {
  const doc = await getDocBySlug('aws-setup')
  
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