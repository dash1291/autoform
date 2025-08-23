'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { apiClient } from '@/lib/api'
import { useAuth } from '@/lib/auth-client'
import { Team } from '@/types'
import { Users, ArrowLeft } from 'lucide-react'

export default function NewTeamPage() {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState('')
  const [formData, setFormData] = useState({
    name: '',
    description: ''
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.name.trim()) return

    setIsCreating(true)
    setError('')
    
    try {
      const team = await apiClient.createTeam({
        name: formData.name.trim(),
        description: formData.description.trim() || undefined
      }) as Team
      
      // Redirect to AWS settings for the newly created team
      router.push(`/teams/${team.id}?tab=settings`)
    } catch (error: any) {
      console.error('Failed to create team:', error)
      setError(error.message || 'Failed to create team')
    } finally {
      setIsCreating(false)
    }
  }

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  if (!isLoading && !isAuthenticated) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <h1 className="text-xl font-semibold mb-4">Please sign in</h1>
          <p className="text-gray-600">You need to be signed in to create a team.</p>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="bg-background">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <Button
            variant="ghost"
            onClick={() => router.push('/dashboard')}
            className="mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Dashboard
          </Button>
          <div className="text-center">
            <div className="text-blue-600 mb-4">
              <Users className="mx-auto h-6 w-6" />
            </div>
            <h1 className="text-xl text-foreground">Create New Team</h1>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Team Details</CardTitle>
            <CardDescription>
              Provide basic information about your team. You can always change this later.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {error && (
              <div className="border border-destructive rounded-lg p-3 mb-6">
                <p className="text-destructive text-sm">{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <Label htmlFor="name">Team Name *</Label>
                <Input
                  id="name"
                  type="text"
                  value={formData.name}
                  onChange={(e) => handleInputChange('name', e.target.value)}
                  className="mt-1"
                  placeholder="Enter team name"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  Choose a descriptive name for your team
                </p>
              </div>

              <div>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={formData.description}
                  onChange={(e) => handleInputChange('description', e.target.value)}
                  className="mt-1"
                  rows={3}
                  placeholder="Enter team description (optional)"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Optional description to help team members understand the team's purpose
                </p>
              </div>

              <div className="flex space-x-4 pt-4">
                <Button
                  type="submit"
                  disabled={isCreating || !formData.name.trim()}
                  className="flex-1"
                >
                  {isCreating ? 'Creating Team...' : 'Create Team'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => router.push('/dashboard')}
                  disabled={isCreating}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}