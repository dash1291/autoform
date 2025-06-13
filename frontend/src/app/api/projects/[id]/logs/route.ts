import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import AWS from 'aws-sdk'

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const projectId = params.id
    const url = new URL(request.url)
    const startTime = url.searchParams.get('startTime')
    const endTime = url.searchParams.get('endTime')
    const limit = parseInt(url.searchParams.get('limit') || '100')

    // Get the project to ensure user owns it
    const project = await prisma.project.findFirst({
      where: {
        id: projectId,
        userId: session.user.id
      }
    })

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    }

    // Initialize CloudWatch Logs client
    const region = process.env.AWS_REGION || 'us-east-1'
    AWS.config.update({ region })
    const cloudWatchLogs = new AWS.CloudWatchLogs({ region })

    const logGroupName = `/ecs/${project.name}`
    
    try {
      // Check if log group exists
      await cloudWatchLogs.describeLogGroups({
        logGroupNamePrefix: logGroupName
      }).promise()
    } catch (error) {
      return NextResponse.json({ 
        error: 'Log group not found. Application may not be deployed yet.',
        logs: []
      }, { status: 404 })
    }

    // Get log streams
    const logStreamsResponse = await cloudWatchLogs.describeLogStreams({
      logGroupName,
      orderBy: 'LastEventTime',
      descending: true,
      limit: 5 // Get latest 5 streams
    }).promise()

    if (!logStreamsResponse.logStreams || logStreamsResponse.logStreams.length === 0) {
      return NextResponse.json({ 
        logs: [],
        message: 'No log streams found'
      })
    }

    // Get logs from all streams
    const allLogs: any[] = []
    
    for (const logStream of logStreamsResponse.logStreams) {
      if (!logStream.logStreamName) continue
      
      try {
        const logsResponse = await cloudWatchLogs.getLogEvents({
          logGroupName,
          logStreamName: logStream.logStreamName,
          limit: Math.floor(limit / logStreamsResponse.logStreams.length),
          startTime: startTime ? parseInt(startTime) : undefined,
          endTime: endTime ? parseInt(endTime) : undefined,
          startFromHead: false // Get most recent logs first
        }).promise()

        if (logsResponse.events) {
          const formattedLogs = logsResponse.events.map(event => ({
            timestamp: event.timestamp,
            message: event.message,
            logStreamName: logStream.logStreamName,
            formattedTime: new Date(event.timestamp!).toISOString()
          }))
          
          allLogs.push(...formattedLogs)
        }
      } catch (streamError) {
        console.error(`Error fetching logs from stream ${logStream.logStreamName}:`, streamError)
      }
    }

    // Sort logs by timestamp (most recent first)
    allLogs.sort((a, b) => b.timestamp - a.timestamp)

    // Limit total logs
    const limitedLogs = allLogs.slice(0, limit)

    return NextResponse.json({
      logs: limitedLogs,
      logGroupName,
      totalStreams: logStreamsResponse.logStreams.length
    })

  } catch (error) {
    console.error('Error fetching CloudWatch logs:', error)
    return NextResponse.json(
      { error: 'Failed to fetch logs' },
      { status: 500 }
    )
  }
}