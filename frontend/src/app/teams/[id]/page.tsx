'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { Spinner } from '@/components/ui/spinner'
import { Team, TeamMember, TeamMemberRole } from '@/types'
import { apiClient } from '@/lib/api'
import { useAuth } from '@/lib/auth-client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Users, Mail, Settings, Trash2, UserMinus, Crown, Shield, User } from 'lucide-react'
import TeamAwsConfiguration from '@/components/TeamAwsConfiguration'
import TabNavButton from '@/components/TabNavButton'
import { FormInput } from '@/components/ui/FormInput'

export default function TeamDetail() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const teamId = params.id as string
  const initialTab = searchParams.get('tab') || 'team-settings'

  const [team, setTeam] = useState<Team | null>(null)
  const [members, setMembers] = useState<TeamMember[]>([])
  const [loading, setLoading] = useState(true)
  const [membersLoading, setMembersLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'members' | 'settings' | 'team-settings'>(initialTab as any || 'members')

  useEffect(() => {
    if (isAuthenticated && !authLoading && teamId) {
      fetchTeam()
    }
  }, [isAuthenticated, authLoading, teamId])

  const fetchTeam = async () => {
    try {
      const data = await apiClient.getTeam(teamId)
      setTeam(data)
      setMembers(data.members || [])
      setMembersLoading(false)
    } catch (error: any) {
      setError(error.message || 'Failed to fetch team')
    } finally {
      setLoading(false)
    }
  }

  const fetchMembers = async () => {
    try {
      const data = await apiClient.getTeam(teamId)
      setMembers(data.members || [])
    } catch (error) {
      console.error('Failed to fetch team members:', error)
    } finally {
      setMembersLoading(false)
    }
  }

  const handleAddMember = async (githubUsername: string, role: TeamMemberRole) => {
    try {
      await apiClient.addTeamMember(teamId, { githubUsername, role })
      fetchTeam() // Refresh team data including members
    } catch (error: any) {
      setError(error.message || 'Failed to add member')
    }
  }

  const handleRemoveMember = async (memberId: string) => {
    if (confirm('Are you sure you want to remove this member from the team?')) {
      try {
        await apiClient.removeTeamMember(teamId, memberId)
        fetchTeam() // Refresh team data including members
      } catch (error: any) {
        setError(error.message || 'Failed to remove member')
      }
    }
  }


  const getRoleIcon = (role: TeamMemberRole) => {
    switch (role) {
      case TeamMemberRole.OWNER:
        return <Crown className="h-4 w-4" />
      case TeamMemberRole.ADMIN:
        return <Shield className="h-4 w-4" />
      case TeamMemberRole.MEMBER:
        return <User className="h-4 w-4" />
      default:
        return <User className="h-4 w-4" />
    }
  }

  const getRoleBadgeColor = (role: TeamMemberRole) => {
    switch (role) {
      case TeamMemberRole.OWNER:
        return 'bg-yellow-100 text-yellow-800'
      case TeamMemberRole.ADMIN:
        return 'bg-blue-100 text-blue-800'
      case TeamMemberRole.MEMBER:
        return 'bg-gray-100 text-gray-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  if (!authLoading && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-semibold mb-4">Please sign in</h1>
          <p className="text-gray-600">You need to be signed in to view team details.</p>
        </div>
      </div>
    )
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-normal mb-4">Error</h1>
          <p className="text-muted-foreground mb-4">{error}</p>
          <Button size="sm" onClick={() => router.push('/dashboard')}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    )
  }

  if (!team) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Team not found</h1>
          <p className="text-gray-600 mb-4">The team you're looking for doesn't exist or you don't have access to it.</p>
          <Button onClick={() => router.push('/dashboard')}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    )
  }

  const isOwner = team.userRole === TeamMemberRole.OWNER
  const canManageMembers = isOwner || team.userRole === TeamMemberRole.ADMIN

  return (
    <div className="min-h-screen">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg">{team.name}</h1>
            </div>
            <div className="flex items-center space-x-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => router.push('/dashboard')}
              >
                Back to Dashboard
              </Button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6">
          <div className="border-b border-gray-700">
            <nav className="-mb-px flex space-x-8">
              {isOwner && (
                <TabNavButton
                  active={activeTab === 'team-settings'}
                  onClick={() => setActiveTab('team-settings')}
                >
                  Team Settings
                </TabNavButton>
              )}
              <TabNavButton
                active={activeTab === 'members'}
                onClick={() => setActiveTab('members')}
              >
                Members
              </TabNavButton>
              <TabNavButton
                active={activeTab === 'settings'}
                onClick={() => setActiveTab('settings')}
              >
                AWS Settings
              </TabNavButton>
            </nav>
          </div>
        </div>

        <div className="space-y-6">
          {activeTab === 'members' && (
            <Card>
              <CardHeader>
                <div className="flex justify-between items-center">
                  <div>
                    <CardTitle>Team Members</CardTitle>
                    <CardDescription>
                      Manage who has access to this team's projects
                    </CardDescription>
                  </div>
                  {canManageMembers && (
                    <AddMemberButton onAddMember={handleAddMember} />
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <MembersList 
                  members={members} 
                  loading={membersLoading}
                  canManageMembers={canManageMembers}
                  onRemoveMember={handleRemoveMember}
                />
              </CardContent>
            </Card>
          )}

          {activeTab === 'settings' && (
            <Card>
              <CardContent className="p-8">
                <TeamAwsConfiguration teamId={teamId} />
              </CardContent>
            </Card>
          )}

          {activeTab === 'team-settings' && isOwner && (
            <Card>
              <CardHeader>
                <CardTitle>Team Settings</CardTitle>
              </CardHeader>
              <CardContent>
                <TeamSettings team={team} />
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function MembersList({ 
  members, 
  loading, 
  canManageMembers, 
  onRemoveMember 
}: { 
  members: TeamMember[]
  loading: boolean
  canManageMembers: boolean
  onRemoveMember: (memberId: string) => void
}) {
  if (loading) {
    return (
      <div className="text-center py-8">
        <Spinner className="mx-auto" />
        <p className="mt-2">Loading members...</p>
      </div>
    )
  }

  if (members.length === 0) {
    return (
      <div className="text-center py-8">
        <Users className="mx-auto h-8 w-8" />
        <h3 className="text-lg mb-2">No members yet</h3>
        <p className="text-sm">Invite team members to start collaborating.</p>
      </div>
    )
  }

  const getRoleIcon = (role: TeamMemberRole) => {
    switch (role) {
      case TeamMemberRole.OWNER:
        return <Crown className="h-4 w-4 text-yellow-600" />
      case TeamMemberRole.ADMIN:
        return <Shield className="h-4 w-4 text-blue-600" />
      case TeamMemberRole.MEMBER:
        return <User className="h-4 w-4 text-gray-600" />
      default:
        return <User className="h-4 w-4 text-gray-600" />
    }
  }

  return (
    <div className="space-y-4">
      {members.map((member) => (
        <div key={member.id} className="flex items-center justify-between p-4 border border-bordee rounded-lg">
          <div className="flex items-center space-x-3">
            <div className="flex-shrink-0">
              {member.user?.image ? (
                <img 
                  className="h-10 w-10 rounded-full" 
                  src={member.user.image} 
                  alt={member.user.name || 'User'} 
                />
              ) : (
                <div className="h-10 w-10 rounded-full flex items-center justify-center">
                  <User className="h-6 w-6" />
                </div>
              )}
            </div>
            <div>
              <p className="text-sm font-medium">
                {member.user?.name || 'Unknown User'}
              </p>
              <p className="text-sm text-muted-foreground">{member.user?.email}</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <div className="flex items-center space-x-1">
              {getRoleIcon(member.role)}
              <span className="text-sm text-muted-foreground">{member.role}</span>
            </div>
            {canManageMembers && member.role !== TeamMemberRole.OWNER && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRemoveMember(member.id)}
                className="text-red-600 hover:text-red-700"
              >
                <UserMinus className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function AddMemberButton({ onAddMember }: { onAddMember: (githubUsername: string, role: TeamMemberRole) => void }) {
  const [showForm, setShowForm] = useState(false)
  const [githubUsername, setGithubUsername] = useState('')
  const [role, setRole] = useState<TeamMemberRole>(TeamMemberRole.MEMBER)
  const [isAdding, setIsAdding] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!githubUsername.trim()) return

    setIsAdding(true)
    try {
      await onAddMember(githubUsername.trim(), role)
      setGithubUsername('')
      setRole(TeamMemberRole.MEMBER)
      setShowForm(false)
    } catch (error) {
      console.error('Failed to add member:', error)
    } finally {
      setIsAdding(false)
    }
  }

  if (showForm) {
    return (
      <div className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormInput
            id="github-username"
            label="GitHub Username"
            value={githubUsername}
            onChange={(value) => setGithubUsername(value as string)}
            placeholder="username"
            helpText="Enter the GitHub username (without @)"
            required
          />
          <div>
            <label className="block text-sm font mb-2">
              Role
            </label>
            <Select value={role} onValueChange={(value) => setRole(value as TeamMemberRole)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TeamMemberRole.MEMBER}>Member</SelectItem>
                <SelectItem value={TeamMemberRole.ADMIN}>Admin</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex space-x-2">
            <Button size="sm" type="submit" disabled={isAdding || !githubUsername.trim()}>
              {isAdding ? 'Adding...' : 'Add Member'}
            </Button>
            <Button size="sm" type="button" variant="outline" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    )
  }

  return (
    <Button size="sm" onClick={() => setShowForm(true)}>
      <Users className="h-4 w-4 mr-2" />
      Add Member
    </Button>
  )
}

function TeamSettings({ team }: { team: Team }) {
  const [editName, setEditName] = useState(team.name)
  const [editDescription, setEditDescription] = useState(team.description || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSave = async () => {
    if (!editName.trim()) {
      setError('Team name is required')
      return
    }

    setSaving(true)
    setError('')
    try {
      await apiClient.updateTeam(team.id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined
      })
      // Refresh the page to show updated data
      window.location.reload()
    } catch (err: any) {
      setError(err.message || 'Failed to update team')
    } finally {
      setSaving(false)
    }
  }


  return (
    <div className="space-y-8">
      <div>
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}
        
        <div className="space-y-4">
          <FormInput
            id="team-name"
            label="Team Name"
            value={editName}
            onChange={(value) => setEditName(value as string)}
            placeholder="Enter team name"
            required
          />
          <div>
            <label className="block text-sm font mb-2">
              Description
            </label>
            <textarea
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              className="w-full text-sm px-3 py-3 border bg-popover border-gray-700 rounded focus:ring-blue-500 focus:border-blue-500"
              rows={3}
              placeholder="Enter team description (optional)"
            />
          </div>
          
          <div>
            <Button
              onClick={handleSave}
              disabled={saving || !editName.trim()}
              size="sm"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </div>
      </div>


      <div className="border-t pt-6">
        <h3 className="text-lg font-medium text-destructive mb-4">Danger Zone</h3>
        <div className="border border-destructive rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-medium text-destructive">Delete Team</h4>
              <p className="text-sm text-destructive mt-1">
                This action cannot be undone. All team projects will become personal projects.
              </p>
            </div>
            <Button variant="outline" className="text-destructive border-destructive hover:bg-destructive hover:text-foreground">
              <Trash2 className="h-4 w-4 mr-2" />
              Delete Team
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}