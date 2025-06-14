'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Project, Team } from '@/types'
import { apiClient } from '@/lib/api'
import { useAuth } from '@/lib/auth-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Plus, Users, ChevronDown, Settings } from 'lucide-react'

export default function Dashboard() {
  const { isAuthenticated, isLoading } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [loading, setLoading] = useState(true)
  const [teamsLoading, setTeamsLoading] = useState(true)
  const [selectedTeam, setSelectedTeam] = useState<string>('personal') // 'personal' or team ID

  useEffect(() => {
    if (isAuthenticated && !isLoading) {
      fetchProjects()
      fetchTeams()
    } else if (!isLoading && !isAuthenticated) {
      setLoading(false)
      setTeamsLoading(false)
    }
  }, [isAuthenticated, isLoading])

  const fetchProjects = async () => {
    try {
      const data = await apiClient.getProjects()
      setProjects(data)
    } catch (error) {
      console.error('Failed to fetch projects:', error)
    } finally {
      setLoading(false)
    }
  }

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

  if (!isLoading && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Please sign in</h1>
          <p className="text-gray-600">You need to be signed in to access the dashboard.</p>
        </div>
      </div>
    )
  }

  if (isLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  // Filter projects based on selected team
  const filteredProjects = selectedTeam === 'personal' 
    ? projects.filter(p => !p.teamId)
    : projects.filter(p => p.teamId === selectedTeam)

  const selectedTeamData = selectedTeam === 'personal' 
    ? null 
    : teams.find(t => t.id === selectedTeam)

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Card>
          <CardHeader>
            <h2 className="text-lg font-medium text-gray-900 mb-4">Projects</h2>
            <div className="flex justify-between items-center">
              <div className="flex items-center space-x-4">
                
                
                {/* Team Switcher */}
                <div className="flex items-center space-x-2">
                  <Select value={selectedTeam} onValueChange={setSelectedTeam}>
                    <SelectTrigger className="w-48">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="personal">
                        <div className="flex items-center space-x-2">
                          <div className="h-4 w-4 rounded-full bg-gray-300"></div>
                          <span>Personal Projects</span>
                        </div>
                      </SelectItem>
                      {teams.map((team) => (
                        <SelectItem key={team.id} value={team.id}>
                          <div className="flex items-center space-x-2">
                            <Users className="h-4 w-4" />
                            <span>{team.name}</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="flex items-center space-x-2">
                {/* Team Management Button */}
                {selectedTeam !== 'personal' && selectedTeamData && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.location.href = `/teams/${selectedTeam}`}
                  >
                    <Settings className="h-4 w-4 mr-2" />
                    Manage Team
                  </Button>
                )}
                
                {/* Create Team Button */}
                {selectedTeam === 'personal' && (
                  <CreateTeamButton onTeamCreated={fetchTeams} />
                )}
                
                {/* New Project Button */}
                <Link href={`/projects/new${selectedTeam !== 'personal' ? `?team=${selectedTeam}` : ''}`}>
                  <Button>
                    <Plus className="h-4 w-4 mr-2" />
                    New Project
                  </Button>
                </Link>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <ProjectsList projects={filteredProjects} loading={loading} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function ProjectsList({ projects, loading }: { projects: Project[], loading: boolean }) {
  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="text-gray-600 mt-2">Loading projects...</p>
      </div>
    )
  }

  if (projects.length === 0) {
    return (
      <div className="text-center py-8">
        <div className="text-gray-400 mb-4">
          <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">No projects yet</h3>
        <p className="text-gray-600 mb-4">Get started by creating your first project.</p>
        <Link href="/projects/new">
          <Button>Create Project</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {projects.map((project) => (
        <div key={project.id} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50">
          <div className="flex justify-between items-start">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-medium text-gray-900">{project.name}</h3>
                {project.team && (
                  <span className="inline-flex items-center px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                    <Users className="h-3 w-3 mr-1" />
                    {project.team.name}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600">{project.gitRepoUrl}</p>
              <div className="mt-2">
                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                  project.status === 'DEPLOYED' ? 'bg-green-100 text-green-800' :
                  project.status === 'FAILED' ? 'bg-red-100 text-red-800' :
                  'bg-yellow-100 text-yellow-800'
                }`}>
                  {project.status}
                </span>
              </div>
            </div>
            <div className="flex space-x-2">
              {project.domain && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(`http://${project.domain}`, '_blank')}
                >
                  View App
                </Button>
              )}
              <Button
                variant="default"
                size="sm"
                onClick={() => window.location.href = `/projects/${project.id}`}
              >
                Settings
              </Button>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}


function CreateTeamButton({ onTeamCreated }: { onTeamCreated: () => void }) {
  const [isCreating, setIsCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    setIsCreating(true)
    try {
      await apiClient.createTeam({
        name: name.trim(),
        description: description.trim() || undefined
      })
      setName('')
      setDescription('')
      setShowForm(false)
      onTeamCreated()
    } catch (error) {
      console.error('Failed to create team:', error)
    } finally {
      setIsCreating(false)
    }
  }

  if (showForm) {
    return (
      <div className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Team Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Enter team name"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description (optional)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Enter team description"
            />
          </div>
          <div className="flex space-x-2">
            <Button type="submit" disabled={isCreating || !name.trim()}>
              {isCreating ? 'Creating...' : 'Create Team'}
            </Button>
            <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    )
  }

  return (
    <Button onClick={() => setShowForm(true)}>
      <Plus className="h-4 w-4 mr-2" />
      New Team
    </Button>
  )
}