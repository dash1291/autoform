'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAuth } from '@/lib/auth-client'
import { apiClient } from '@/lib/api'
import { Team } from '@/types'
import { CheckCircle } from "lucide-react";

import { FormInput } from '@/components/ui/FormInput'

export default function NewProject() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [formData, setFormData] = useState({
    name: '',
    gitRepoUrl: '',
    teamId: '', // team is required
    branch: 'main', // default branch
    subdirectory: '',
    cpu: 256,
    memory: 512,
    diskSize: 21,
  })
  const [projectCreated, setProjectCreated] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [validating, setValidating] = useState(false)
  const [repoInfo, setRepoInfo] = useState<any>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [teamsLoading, setTeamsLoading] = useState(true)

  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      fetchTeams()
      
      // Set team from query parameter if provided
      const teamParam = searchParams.get('team')
      if (teamParam) {
        setFormData(prev => ({ ...prev, teamId: teamParam }))
      }
    }
  }, [isAuthenticated, authLoading, searchParams])

  const fetchTeams = async () => {
    try {
      const data = await apiClient.getTeams()
      setTeams(data)
    } catch (error) {
      console.error('Failed to fetch teams:', error)
    } finally {
      setTeamsLoading(false)
    }
  }

  const validateRepository = async (url: string) => {
    if (!url || !url.includes('github.com')) return

    console.log('Starting repository validation for:', url)
    console.log('Auth status:', isAuthenticated ? 'authenticated' : 'not authenticated')
    
    setValidating(true)
    setError('')
    setRepoInfo(null)

    try {
      console.log('Making fetch request to validate repository')
      const data = await apiClient.validateRepository(url)
      console.log('Response data:', data)

      if (data.valid && data.repository) {
        const repository = data.repository
        setRepoInfo(repository)
        // Auto-fill project name and branch if empty
        if (!formData.name && repository.name) {
          setFormData(prev => ({ 
            ...prev, 
            name: repository.name,
            branch: repository.defaultBranch 
          }))
        } else if (repository.defaultBranch) {
          setFormData(prev => ({ 
            ...prev, 
            branch: repository.defaultBranch 
          }))
        }
      } else {
        setError(data.detail || 'Unknown error occurred')
        
        // If re-authentication is needed, show special message
        if (data.needsReauth) {
          setError((data.error || 'Authentication needed') + ' Click here to refresh your GitHub connection.')
        }
      }
    } catch (err) {
      setError('Failed to validate repository')
    } finally {
      setValidating(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isAuthenticated) return

    setLoading(true)
    setError('')

    try {
      // Validate repository first if not already validated
      if (!repoInfo) {
        await validateRepository(formData.gitRepoUrl)
        if (!repoInfo) {
          setLoading(false)
          return
        }
      }

      const newProject = await apiClient.createProject({
        name: formData.name,
        gitRepoUrl: formData.gitRepoUrl,
        teamId: formData.teamId
      })
      setProjectCreated(newProject)
    } catch (err: any) {
      setError(err.message || 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  if (!authLoading && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-semibold mb-4">Please sign in</h1>
          <p className="text-gray-600">You need to be signed in to create a project.</p>
        </div>
      </div>
    )
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  // Show environment creation step after project is created
  if (projectCreated) {
    return (
      <div className="min-h-screen">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="mb-8">
            <h1 className="text-lg">Project Created Successfully!</h1>
            <p className="text-muted-foreground mt-2">
              Your project "{projectCreated.name}" has been created. Now let's set up your first environment.
            </p>
          </div>
          <div className="shadow rounded-lg py-6">
            <div className="space-y-4">
              <Button 
                onClick={() => router.push(`/projects/${projectCreated.id}?tab=environments`)}
                className=""
              >
                Set Up Environment
              </Button>
              <Button 
                variant="outline" 
                onClick={() => router.push('/dashboard')}
                className="ml-2"
              >
                Skip for Now (Go to Dashboard)
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-4 mt-4 w-full text-center">
          <h1 className="text-lg">Create New Project</h1>
        </div>
        <div className="shadow rounded-lg p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <FormInput
                id="name"
                label="Project Name"
                value={formData.name}
                onChange={(value) => setFormData({ ...formData, name: value as string })}
                placeholder="my-awesome-app"
                required
                helpText="This will be used as the container name and resource prefix"
                type="text"
              />
            </div>

            <div>
              <label htmlFor="team" className="block text-sm mb-2">
                Team <span className="text-red-500">*</span>
              </label>
              {teams.length === 0 && !teamsLoading ? (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                  <p className="text-yellow-800 text-sm mb-2">
                    You need to create a team before creating a project.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => router.push('/dashboard')}
                  >
                    Go to Dashboard
                  </Button>
                </div>
              ) : (
                <Select 
                  value={formData.teamId} 
                  onValueChange={(value) => setFormData({ ...formData, teamId: value })}
                  disabled={teamsLoading}
                  required
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a team" />
                  </SelectTrigger>
                  <SelectContent>
                    {teams.map((team) => (
                      <SelectItem key={team.id} value={team.id}>
                        {team.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <p className="text-xs mt-1 text-muted-foreground">
                {teamsLoading 
                  ? 'Loading teams...' 
                  : teams.length > 0 
                    ? 'Projects must belong to a team for AWS credential and resource management'
                    : 'Create a team first to organize your projects and AWS resources'
                }
              </p>
            </div>

            <div>
              <FormInput
                id="gitRepoUrl"
                label="Git Repository URL"
                helpText='Can be public or private repository. Private repos use your GitHub authentication.'
                value={formData.gitRepoUrl}
                onChange={(value) => {
                  setFormData({ ...formData, gitRepoUrl: value as string })
                  setRepoInfo(null)
                }}
                placeholder="https://github.com/username/repository"
                required
                type="url"
                rightElement={validating ? (
                  <Spinner size="sm" />
                ) : undefined}
                bottomElement={
                  <>
                    {repoInfo && (
                      <div className="mt-2 p-3 bg-popover border border-gray-700 rounded">
                        <div className="flex items-center">
                          <span className="text-success-foreground text-sm">✅ Repository validated</span>
                          {repoInfo.private && (
                            <span className="ml-2 px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded">Private</span>
                          )}
                        </div>
                        <p className="text-sm mt-1">
                          <strong>{repoInfo.fullName}</strong>
                        </p>
                      </div>
                    )}
                    <div className="flex items-center justify-between mt-1">
                      <p className="text-sm text-gray-500">
                      </p>
                      {formData.gitRepoUrl && !repoInfo && (
                        <button
                          type="button"
                          onClick={() => validateRepository(formData.gitRepoUrl)}
                          disabled={validating}
                          className="text-sm text-blue-400 hover:text-blue-700 disabled:opacity-50"
                        >
                          {validating ? 'Validating...' : 'Save'}
                        </button>
                      )}
                    </div>
                  </>
                }
              />
            </div>

            <div>
              <FormInput
                id="subdirectory"
                label="Subdirectory (Optional)"
                value={formData.subdirectory}
                onChange={(value) => setFormData({ ...formData, subdirectory: value as string })}
                placeholder="e.g., backend or apps/api"
                helpText="Specify a subdirectory if your application code is not in the repository root"
                type="text"
              />
            </div>

            {error && (
              <div className="bg-popover border border-destructive rounded-lg p-4">
                <p className="text-destructive">{error}</p>
              </div>
            )}

            <div className="flex space-x-4">
              <Button
                type="submit"
                disabled={loading}
                className="flex-1"
              >
                {loading ? 'Creating...' : 'Create Project'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push('/dashboard')}
              >
                Cancel
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}