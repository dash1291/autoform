'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertTriangle, Loader2, CheckCircle, XCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface DeleteProjectDialogProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  projectName: string
  onSuccess: () => void
}

export function DeleteProjectDialog({
  isOpen,
  onClose,
  projectId,
  projectName,
  onSuccess,
}: DeleteProjectDialogProps) {
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletionResult, setDeletionResult] = useState<{
    deleted: string[]
    failed: string[]
    errors: string[]
  } | null>(null)

  const handleDelete = async () => {
    setIsDeleting(true)
    setError(null)
    setDeletionResult(null)

    try {
      // Always delete infrastructure
      const result = await apiClient.deleteProject(projectId, true)
      
      if (result.infrastructure_deletion?.resources) {
        setDeletionResult({
          deleted: result.infrastructure_deletion.resources.deleted || [],
          failed: result.infrastructure_deletion.resources.failed || [],
          errors: result.infrastructure_deletion.resources.errors || [],
        })
        
        // If there were failures but the project was deleted, show success after a delay
        if (result.infrastructure_deletion.resources.failed?.length) {
          setTimeout(() => {
            onSuccess()
          }, 3000)
        } else {
          // Complete success
          setTimeout(() => {
            onSuccess()
          }, 2000)
        }
      } else {
        // No infrastructure deletion, just project deletion
        onSuccess()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete project')
      setIsDeleting(false)
    }
  }

  const handleClose = () => {
    if (!isDeleting) {
      setError(null)
      setDeletionResult(null)
      onClose()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Delete Project</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete <strong>{projectName}</strong>?
          </DialogDescription>
        </DialogHeader>

        {!deletionResult && (
          <>
            <div className="space-y-4">
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  <strong>This action cannot be undone.</strong> All project data and AWS infrastructure will be permanently deleted.
                </AlertDescription>
              </Alert>

              <div className="space-y-2">
                <p className="text-sm font-medium">The following will be deleted:</p>
                <ul className="text-sm text-muted-foreground ml-4 list-disc space-y-1">
                  <li>Project database records and configuration</li>
                  <li>All deployments and environment data</li>
                  <li>ECS services and tasks</li>
                  <li>Load balancers and target groups</li>
                  <li>Security groups (project-specific)</li>
                  <li>ECR repository and container images</li>
                  <li>CloudWatch logs</li>
                  <li>S3 build artifacts</li>
                </ul>
                <Alert className="mt-4">
                  <AlertDescription className="text-sm">
                    <strong>Note:</strong> Shared resources (VPC, subnets, ECS clusters) will be preserved for use by other projects.
                  </AlertDescription>
                </Alert>
              </div>
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </>
        )}

        {deletionResult && (
          <div className="space-y-4">
            {deletionResult.deleted.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-2 flex items-center">
                  <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                  Successfully Deleted Resources
                </h4>
                <ul className="text-sm text-muted-foreground ml-6 list-disc max-h-40 overflow-y-auto">
                  {deletionResult.deleted.map((resource, i) => (
                    <li key={i}>{resource}</li>
                  ))}
                </ul>
              </div>
            )}

            {deletionResult.failed.length > 0 && (
              <Alert variant="destructive">
                <XCircle className="h-4 w-4" />
                <AlertDescription>
                  <div>
                    <p className="font-medium">Some resources failed to delete:</p>
                    <ul className="text-sm mt-2 ml-4 list-disc">
                      {deletionResult.failed.map((resource, i) => (
                        <li key={i}>{resource}</li>
                      ))}
                    </ul>
                  </div>
                </AlertDescription>
              </Alert>
            )}

            {deletionResult.errors.length > 0 && (
              <Alert variant="destructive">
                <AlertDescription>
                  <div>
                    <p className="font-medium">Errors encountered:</p>
                    <ul className="text-sm mt-2 ml-4 list-disc">
                      {deletionResult.errors.map((error, i) => (
                        <li key={i}>{error}</li>
                      ))}
                    </ul>
                  </div>
                </AlertDescription>
              </Alert>
            )}

            {!deletionResult.failed.length && !deletionResult.errors.length && (
              <Alert>
                <CheckCircle className="h-4 w-4" />
                <AlertDescription>
                  Project and infrastructure deleted successfully. Redirecting...
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}

        <DialogFooter>
          {!deletionResult && (
            <>
              <Button variant="outline" onClick={handleClose} disabled={isDeleting}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  'Delete Project'
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}