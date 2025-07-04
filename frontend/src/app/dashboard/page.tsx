'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Project, Team } from '@/types'
import { apiClient } from '@/lib/api'
import { useAuth } from '@/lib/auth-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Plus, Users, ChevronDown, Settings,Github } from 'lucide-react'

export default function Dashboard() {
  const { isAuthenticated, isLoading } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [loading, setLoading] = useState(true)
  const [teamsLoading, setTeamsLoading] = useState(true)
  const [selectedTeam, setSelectedTeam] = useState<string>('') // team ID

  useEffect(() => {
    if (isAuthenticated && !isLoading) {
      fetchProjects()
      fetchTeams()
    } else if (!isLoading && !isAuthenticated) {
      setLoading(false)
      setTeamsLoading(false)
    }
  }, [isAuthenticated, isLoading])

  // Set first team as selected when teams load
  useEffect(() => {
    if (teams.length > 0 && !selectedTeam) {
      setSelectedTeam(teams[0].id)
    }
  }, [teams, selectedTeam])

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
          <h1 className="text-xl font-semibold mb-4">Please sign in</h1>
          <p>You need to be signed in to access the dashboard.</p>
        </div>
      </div>
    )
  }

  if (isLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  // Filter projects based on selected team
  const filteredProjects = selectedTeam 
    ? projects.filter(p => p.teamId === selectedTeam)
    : []

  const selectedTeamData = teams.find(t => t.id === selectedTeam)

  return (
    <div className="min-h-screen text-foreground">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {teams.length === 0 && !teamsLoading ? (
          <Card>
            <CardHeader>
              <CardTitle>Welcome to Autoform!</CardTitle>
              <CardDescription>
                Get started by creating your first team. Teams help you organize projects and manage AWS resources.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8">
                <div className="text-muted-foreground mb-4">
                  <Users className="mx-auto h-12 w-12" />
                </div>
                <h3 className="text-lg font-medium mb-2">Create your first team</h3>
                <p className="mb-6">
                  Teams allow you to manage projects, configure AWS credentials, and collaborate with others.
                </p>
                <CreateTeamButton onTeamCreated={fetchTeams} />
              </div>
            </CardContent>
          </Card>
        ) : (
          <div>
            <CardHeader>
              <h2 className="text-lg font-medium mb-4">Projects</h2>
              <div className="flex justify-between items-center">
                <div className="flex items-center space-x-2">
                  {/* New Project Button */}
                  {selectedTeam && (
                    <Link href={`/projects/new?team=${selectedTeam}`}>
                      <Button size="sm">
                        <Plus className="h-4 w-4" />
                        New Project
                      </Button>
                    </Link>
                  )}
                </div>
                <div className="flex items-center space-x-2">
                  {/* Team Switcher */}
                  {teams.length > 0 && (
                    <div className="flex items-center space-x-2">
                      <Select value={selectedTeam} onValueChange={setSelectedTeam}>
                        <SelectTrigger className="w-48">
                          <SelectValue placeholder="Select a team" />
                        </SelectTrigger>
                        <SelectContent>
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
                  )}
                  {selectedTeamData && (
                    <Button
                      size="sm"
                      onClick={() => window.location.href = `/teams/${selectedTeam}`}
                    >
                      <Settings className="h-4 w-4" />
                      Team Settings
                    </Button>
                  )}
                  {/* Create Team Button */}
                  <CreateTeamButton onTeamCreated={fetchTeams} />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {selectedTeam ? (
                <ProjectsList projects={filteredProjects} loading={loading} />
              ) : (
                <div className="text-center py-8">
                  <p className="">Select a team to view projects</p>
                </div>
              )}
            </CardContent>
          </div>
        )}
      </div>
    </div>
  )
}

function ProjectsList({ projects, loading }: { projects: Project[], loading: boolean }) {
  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
        <p className="mt-2">Loading projects...</p>
      </div>
    )
  }

  if (projects.length === 0) {
    return (
      <div className="text-center py-8">
        <div className="mb-4">
          <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-foreground mb-2">No projects yet</h3>
        <p className="mb-4">Get started by creating your first project for this team.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {projects.map((project) => (
        <div key={project.id} className="border border-gray-700 rounded p-4">
          <div className="flex justify-between items-start">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium">{project.name}</h3>
              </div>
              <div className="text-muted-foreground text-sm">{project.gitRepoUrl}</div>
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
            <label className="block text-sm font-medium mb-1">
              Team Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Enter team name"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">
              Description (optional)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
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
    <Button size="sm" onClick={() => window.location.href = '/teams/new'}>
      <Plus className="h-4 w-4" />
      New Team
    </Button>
  )
}