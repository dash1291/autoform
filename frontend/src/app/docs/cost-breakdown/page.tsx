import { getDocBySlug } from '@/lib/docs'
import { notFound } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'

export default async function CostBreakdownPage() {
  const doc = await getDocBySlug('cost-breakdown')
  
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

export const metadata = {
  title: 'AWS Cost Breakdown - Autoform Documentation',
  description: 'Understand the costs of resources created by Autoform deployments'
}