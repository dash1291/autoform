'use client'

import { useState } from 'react'
import { Project } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface ResourceConfigurationProps {
  projectId: string
  project: Project
  onUpdate: () => void
}

export default function ResourceConfiguration({ projectId, project, onUpdate }: ResourceConfigurationProps) {
  const [formData, setFormData] = useState({
    cpu: project.cpu || 256,
    memory: project.memory || 512,
    diskSize: project.diskSize || 21,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const response = await fetch(`/api/projects/${projectId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      })

      if (response.ok) {
        setSuccess('Resource configuration updated successfully!')
        onUpdate()
      } else {
        const data = await response.json()
        setError(data.error || 'Failed to update resource configuration')
      }
    } catch (err) {
      setError('Failed to update resource configuration')
    } finally {
      setLoading(false)
    }
  }

  // Check if form data has changed from original values
  const hasChanges = 
    formData.cpu !== (project.cpu || 256) ||
    formData.memory !== (project.memory || 512) ||
    formData.diskSize !== (project.diskSize || 21)

  const isDeploying = project.status === 'DEPLOYING' || project.status === 'BUILDING' || project.status === 'CLONING'

  return (
    <Card>
      <CardHeader>
        <CardTitle>Resource Configuration</CardTitle>
        <CardDescription>
          Configure CPU, memory, and storage resources for your deployment
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="cpu">CPU (units)</Label>
              <Select
                value={formData.cpu.toString()}
                onValueChange={(value) => setFormData({ ...formData, cpu: parseInt(value) })}
                disabled={isDeploying}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="256">256 (0.25 vCPU)</SelectItem>
                  <SelectItem value="512">512 (0.5 vCPU)</SelectItem>
                  <SelectItem value="1024">1024 (1 vCPU)</SelectItem>
                  <SelectItem value="2048">2048 (2 vCPU)</SelectItem>
                  <SelectItem value="4096">4096 (4 vCPU)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">AWS Fargate CPU allocation</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="memory">Memory (MB)</Label>
              <Select
                value={formData.memory.toString()}
                onValueChange={(value) => setFormData({ ...formData, memory: parseInt(value) })}
                disabled={isDeploying}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="512">512 MB</SelectItem>
                  <SelectItem value="1024">1 GB</SelectItem>
                  <SelectItem value="2048">2 GB</SelectItem>
                  <SelectItem value="4096">4 GB</SelectItem>
                  <SelectItem value="8192">8 GB</SelectItem>
                  <SelectItem value="16384">16 GB</SelectItem>
                  <SelectItem value="30720">30 GB</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Container memory limit</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="diskSize">Disk Size (GB)</Label>
              <Input
                id="diskSize"
                type="number"
                min="21"
                max="200"
                value={formData.diskSize}
                onChange={(e) => setFormData({ ...formData, diskSize: parseInt(e.target.value) || 21 })}
                disabled={isDeploying}
              />
              <p className="text-xs text-muted-foreground">Ephemeral storage (21-200 GB)</p>
            </div>
          </div>

          {error && (
            <div className="bg-destructive/15 border border-destructive/20 rounded-lg p-4">
              <p className="text-destructive">{error}</p>
            </div>
          )}

          {success && (
            <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800/30 rounded-lg p-4">
              <p className="text-green-800 dark:text-green-400">{success}</p>
            </div>
          )}

          {isDeploying && (
            <div className="bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800/30 rounded-lg p-4">
              <p className="text-yellow-800 dark:text-yellow-400">
                Cannot modify resource configuration while deployment is in progress.
              </p>
            </div>
          )}

          <div className="flex space-x-4">
            <Button
              type="submit"
              disabled={loading || isDeploying || !hasChanges}
            >
              {loading ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}