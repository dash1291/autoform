import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'

export async function POST(request: NextRequest) {
  console.log('=== VALIDATE REPO API CALLED ===')
  try {
    const session = await getServerSession(authOptions)
    console.log('Session object:', session ? 'exists' : 'null')
    console.log('User ID from session:', session?.user?.id)
    
    if (!session?.user?.id) {
      console.log('No session or user ID - returning 401')
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { gitRepoUrl } = await request.json()

    if (!gitRepoUrl) {
      return NextResponse.json({ error: 'Repository URL is required' }, { status: 400 })
    }

    // Validate GitHub URL format
    const gitUrlRegex = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\.git)?$/
    if (!gitUrlRegex.test(gitRepoUrl)) {
      return NextResponse.json({
        error: 'Please provide a valid GitHub repository URL',
        valid: false
      }, { status: 400 })
    }

    // Get user's GitHub token
    const user = await prisma.user.findUnique({
      where: { id: session.user.id },
      include: {
        accounts: {
          where: { provider: 'github' }
        }
      }
    })

    if (!user?.accounts?.[0]?.access_token) {
      // Try to refresh the token if we have a refresh token
      if (user?.accounts?.[0]?.refresh_token) {
        console.log('Attempting to refresh GitHub token...')
        try {
          const refreshResponse = await fetch('https://github.com/login/oauth/access_token', {
            method: 'POST',
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
              client_id: process.env.GITHUB_ID!,
              client_secret: process.env.GITHUB_SECRET!,
              refresh_token: user.accounts[0].refresh_token,
              grant_type: 'refresh_token',
            }),
          })

          const refreshData = await refreshResponse.json()
          console.log('Refresh response:', refreshData)

          if (refreshData.access_token) {
            // Update the access token in the database
            await prisma.account.update({
              where: { id: user.accounts[0].id },
              data: {
                access_token: refreshData.access_token,
                expires_at: refreshData.expires_in ? Math.floor(Date.now() / 1000) + refreshData.expires_in : null,
                refresh_token: refreshData.refresh_token || user.accounts[0].refresh_token,
              },
            })

            // Update the user object for the rest of the function
            user.accounts[0].access_token = refreshData.access_token
            console.log('Token refreshed successfully')
          } else {
            console.log('Failed to refresh token:', refreshData)
            return NextResponse.json({
              error: 'GitHub account not connected. Please sign out and sign in again to connect your GitHub account.',
              valid: false,
              needsReauth: true
            }, { status: 400 })
          }
        } catch (error) {
          console.error('Error refreshing token:', error)
          return NextResponse.json({
            error: 'GitHub account not connected. Please sign out and sign in again to connect your GitHub account.',
            valid: false,
            needsReauth: true
          }, { status: 400 })
        }
      } else {
        return NextResponse.json({
          error: 'GitHub account not connected. Please sign out and sign in again to connect your GitHub account.',
          valid: false,
          needsReauth: true
        }, { status: 400 })
      }
    }

    // Extract owner and repo from URL
    const match = gitRepoUrl.match(/github\.com\/([^\/]+)\/([^\/]+?)(?:\.git)?$/)
    if (!match) {
      return NextResponse.json({
        error: 'Invalid GitHub URL format',
        valid: false
      }, { status: 400 })
    }

    const [, owner, repo] = match

    // First, test if the token is valid with a simple API call
    try {
      const tokenTestResponse = await fetch('https://api.github.com/user', {
        headers: {
          'Authorization': `Bearer ${user.accounts[0].access_token}`,
          'User-Agent': 'Autopilot-PaaS',
          'Accept': 'application/vnd.github.v3+json'
        }
      })
      
      console.log(`Token test response: ${tokenTestResponse.status}`)
      
      if (tokenTestResponse.status === 401) {
        // Delete the expired token to force re-authentication
        await prisma.account.update({
          where: { id: user.accounts[0].id },
          data: { access_token: null }
        });
        
        return NextResponse.json({
          error: 'Your GitHub session has expired. Please sign out and sign in again to refresh your access.',
          valid: false,
          needsReauth: true
        }, { status: 401 })
      }
    } catch (error: any) {
      console.error('Token test failed:', error)
      return NextResponse.json({
        error: error?.message || 'Failed to validate GitHub token. Please try signing out and signing in again.',
        valid: false,
        needsReauth: true
      }, { status: 401 })
    }

    // Check repository access using GitHub API
    try {
      console.log(`Validating repository access for ${owner}/${repo}`)
      const tokenPreview = user.accounts?.[0]?.access_token?.substring(0, 4) + '...' + user.accounts?.[0]?.access_token?.slice(-4);
      console.log(`Using token: ${tokenPreview}`)
      
      const response = await fetch(`https://api.github.com/repos/${owner}/${repo}`, {
        headers: {
          'Authorization': `Bearer ${user.accounts?.[0]?.access_token}`,
          'User-Agent': 'Autopilot-PaaS',
          'Accept': 'application/vnd.github.v3+json'
        }
      })

      console.log(`GitHub API response status: ${response.status}`)
      const responseBody = await response.text()
      console.log(`GitHub API response body: ${responseBody}`)

      if (response.status === 200) {
        const repoData = JSON.parse(responseBody)
        console.log(`Repository found: ${repoData.full_name}, private: ${repoData.private}`)
        
        // Get available branches
        let branches = [repoData.default_branch]
        try {
          const branchesResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}/branches`, {
            headers: {
              'Authorization': `Bearer ${user.accounts?.[0]?.access_token}`,
              'User-Agent': 'Autopilot-PaaS',
              'Accept': 'application/vnd.github.v3+json'
            }
          })
          
          if (branchesResponse.ok) {
            const branchesData = await branchesResponse.json()
            branches = branchesData.map((branch: any) => branch.name)
            console.log(`Found ${branches.length} branches:`, branches)
          }
        } catch (error) {
          console.warn('Failed to fetch branches, using default branch only:', error)
        }
        
        return NextResponse.json({
          valid: true,
          repository: {
            name: repoData.name,
            fullName: repoData.full_name,
            private: repoData.private,
            defaultBranch: repoData.default_branch,
            description: repoData.description,
            branches: branches
          }
        })
      } else if (response.status === 404) {
        console.log(`GitHub API 404 response:`, responseBody)
        
        return NextResponse.json({
          error: 'Repository not found or you do not have access to this repository',
          valid: false,
          debug: { status: response.status, body: responseBody }
        }, { status: 404 })
      } else if (response.status === 403) {
        console.log(`GitHub API 403 response:`, responseBody)
        
        return NextResponse.json({
          error: 'Access denied. Please ensure you have read access to this repository',
          valid: false,
          debug: { status: response.status, body: responseBody }
        }, { status: 403 })
      } else if (response.status === 401) {
        console.log(`GitHub API 401 response:`, responseBody)
        
        return NextResponse.json({
          error: 'GitHub authentication failed. Please sign out and sign in again to refresh your token.',
          valid: false,
          debug: { status: response.status, body: responseBody }
        }, { status: 401 })
      } else {
        console.log(`GitHub API unexpected status ${response.status}:`, responseBody)
        throw new Error(`GitHub API returned status ${response.status}: ${responseBody}`)
      }
    } catch (error) {
      console.error('GitHub API error:', error)
      return NextResponse.json({
        error: 'Failed to validate repository access. Please try again.',
        valid: false,
        debug: { error: error instanceof Error ? error.message : 'Unknown error' }
      }, { status: 500 })
    }
  } catch (error) {
    console.error('Error validating repository:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}