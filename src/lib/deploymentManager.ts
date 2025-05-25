import { exec } from 'child_process'
import { promisify } from 'util'

const execAsync = promisify(exec)

interface ActiveDeployment {
  projectId: string
  deploymentId: string
  processes: {
    cloneProcess?: any
    buildProcess?: any
    pushProcess?: any
  }
  aborted: boolean
}

class DeploymentManager {
  private activeDeployments = new Map<string, ActiveDeployment>()

  registerDeployment(projectId: string, deploymentId: string) {
    this.activeDeployments.set(projectId, {
      projectId,
      deploymentId,
      processes: {},
      aborted: false
    })
    console.log(`Registered deployment ${deploymentId} for project ${projectId}`)
  }

  markAsAborted(projectId: string) {
    const deployment = this.activeDeployments.get(projectId)
    if (deployment) {
      deployment.aborted = true
      console.log(`Marked deployment ${deployment.deploymentId} as aborted`)
      
      // Try to kill any running processes
      this.killProcesses(deployment)
    }
  }

  isAborted(projectId: string): boolean {
    const deployment = this.activeDeployments.get(projectId)
    return deployment?.aborted || false
  }

  setCloneProcess(projectId: string, process: any) {
    const deployment = this.activeDeployments.get(projectId)
    if (deployment) {
      deployment.processes.cloneProcess = process
    }
  }

  setBuildProcess(projectId: string, process: any) {
    const deployment = this.activeDeployments.get(projectId)
    if (deployment) {
      deployment.processes.buildProcess = process
    }
  }

  setPushProcess(projectId: string, process: any) {
    const deployment = this.activeDeployments.get(projectId)
    if (deployment) {
      deployment.processes.pushProcess = process
    }
  }

  private killProcesses(deployment: ActiveDeployment) {
    const { processes } = deployment
    
    try {
      if (processes.cloneProcess) {
        processes.cloneProcess.kill('SIGTERM')
        console.log('Killed clone process')
      }
      if (processes.buildProcess) {
        processes.buildProcess.kill('SIGTERM')
        console.log('Killed build process')
      }
      if (processes.pushProcess) {
        processes.pushProcess.kill('SIGTERM')
        console.log('Killed push process')
      }
    } catch (error) {
      console.warn('Error killing processes:', error)
    }
  }

  completeDeployment(projectId: string) {
    this.activeDeployments.delete(projectId)
    console.log(`Completed deployment for project ${projectId}`)
  }

  // Enhanced exec that can be aborted
  async execWithAbort(command: string, projectId: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const process = exec(command, (error, stdout, stderr) => {
        if (error) {
          reject(error)
        } else {
          resolve(stdout)
        }
      })

      // Check if deployment was aborted
      const checkAborted = () => {
        if (this.isAborted(projectId)) {
          process.kill('SIGTERM')
          reject(new Error('Deployment aborted by user'))
          return
        }
        setTimeout(checkAborted, 1000) // Check every second
      }
      checkAborted()
    })
  }

  getActiveDeployments(): string[] {
    return Array.from(this.activeDeployments.keys())
  }
}

// Singleton instance
export const deploymentManager = new DeploymentManager()