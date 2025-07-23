#!/usr/bin/env python3
"""
Debug deployment issues: health checks and over-provisioning
"""

import boto3
import json
import sys
from utils.aws_client import create_client

def debug_deployment_issues(region="us-east-1"):
    """Debug current deployment state"""
    
    # Initialize clients
    ecs = create_client("ecs", region)
    elbv2 = create_client("elbv2", region)
    autoscaling = create_client("autoscaling", region)
    ec2 = create_client("ec2", region)
    
    print("🔍 DEBUGGING DEPLOYMENT ISSUES")
    print("=" * 60)
    
    # 1. List all ECS clusters
    print("\n1. ECS CLUSTERS:")
    try:
        clusters_response = ecs.list_clusters()
        for cluster_arn in clusters_response['clusterArns']:
            cluster_name = cluster_arn.split('/')[-1]
            print(f"   📦 {cluster_name}")
            
            # Get cluster details
            cluster_details = ecs.describe_clusters(
                clusters=[cluster_arn],
                include=['CAPACITY_PROVIDERS', 'ATTACHMENTS']
            )
            
            if cluster_details['clusters']:
                cluster = cluster_details['clusters'][0]
                print(f"      Status: {cluster.get('status', 'Unknown')}")
                print(f"      Active Services: {cluster.get('activeServicesCount', 0)}")
                print(f"      Running Tasks: {cluster.get('runningTasksCount', 0)}")
                print(f"      Pending Tasks: {cluster.get('pendingTasksCount', 0)}")
                print(f"      Capacity Providers: {cluster.get('capacityProviders', [])}")
                
                # List services in this cluster
                services_response = ecs.list_services(cluster=cluster_arn)
                if services_response['serviceArns']:
                    print(f"      Services:")
                    for service_arn in services_response['serviceArns']:
                        service_name = service_arn.split('/')[-1]
                        print(f"         🔸 {service_name}")
                        
                        # Get service details
                        service_details = ecs.describe_services(
                            cluster=cluster_arn,
                            services=[service_arn]
                        )
                        
                        if service_details['services']:
                            service = service_details['services'][0]
                            print(f"            Status: {service.get('status', 'Unknown')}")
                            print(f"            Desired: {service.get('desiredCount', 0)}")
                            print(f"            Running: {service.get('runningCount', 0)}")
                            print(f"            Pending: {service.get('pendingCount', 0)}")
                            
                            # Check load balancers
                            load_balancers = service.get('loadBalancers', [])
                            if load_balancers:
                                print(f"            Load Balancer: {load_balancers[0].get('targetGroupArn', 'None')}")
                            
                            # Check capacity provider strategy
                            cp_strategy = service.get('capacityProviderStrategy', [])
                            if cp_strategy:
                                print(f"            Capacity Provider: {cp_strategy[0].get('capacityProvider', 'None')}")
                            
                            # Check for events (recent deployments, health issues)
                            events = service.get('events', [])[:3]  # Last 3 events
                            if events:
                                print(f"            Recent Events:")
                                for event in events:
                                    print(f"               - {event.get('createdAt', '')}: {event.get('message', '')}")
                
                # List tasks in this cluster
                print(f"      Tasks:")
                tasks_response = ecs.list_tasks(cluster=cluster_arn)
                if tasks_response['taskArns']:
                    task_details = ecs.describe_tasks(
                        cluster=cluster_arn,
                        tasks=tasks_response['taskArns']
                    )
                    
                    for task in task_details['tasks']:
                        task_id = task['taskArn'].split('/')[-1]
                        print(f"         🔸 {task_id}")
                        print(f"            Status: {task.get('lastStatus', 'Unknown')}")
                        print(f"            Health: {task.get('healthStatus', 'Unknown')}")
                        print(f"            CPU/Memory: {task.get('cpu', 'N/A')}/{task.get('memory', 'N/A')}")
                        
                        # Check container instance
                        if task.get('containerInstanceArn'):
                            container_instance_id = task['containerInstanceArn'].split('/')[-1]
                            print(f"            Container Instance: {container_instance_id}")
    except Exception as e:
        print(f"   ❌ Error listing clusters: {e}")
    
    # 2. Check Auto Scaling Groups
    print("\n2. AUTO SCALING GROUPS:")
    try:
        asg_response = autoscaling.describe_auto_scaling_groups()
        for asg in asg_response['AutoScalingGroups']:
            if 'ecs' in asg['AutoScalingGroupName'].lower():
                print(f"   📊 {asg['AutoScalingGroupName']}")
                print(f"      Min/Max/Desired: {asg['MinSize']}/{asg['MaxSize']}/{asg['DesiredCapacity']}")
                print(f"      Current Instances: {len(asg['Instances'])}")
                
                for instance in asg['Instances']:
                    print(f"         🖥️  {instance['InstanceId']} - {instance['LifecycleState']} - {instance['HealthStatus']}")
                
                # Check scaling activities
                activities_response = autoscaling.describe_scaling_activities(
                    AutoScalingGroupName=asg['AutoScalingGroupName'],
                    MaxRecords=5
                )
                
                if activities_response['Activities']:
                    print(f"      Recent Scaling Activities:")
                    for activity in activities_response['Activities'][:3]:
                        print(f"         - {activity.get('StartTime', '')}: {activity.get('Description', '')}")
                        if activity.get('StatusMessage'):
                            print(f"           Status: {activity.get('StatusMessage', '')}")
    except Exception as e:
        print(f"   ❌ Error checking ASGs: {e}")
    
    # 3. Check Load Balancers and Target Groups
    print("\n3. LOAD BALANCERS:")
    try:
        lb_response = elbv2.describe_load_balancers()
        for lb in lb_response['LoadBalancers']:
            print(f"   🔗 {lb['LoadBalancerName']}")
            print(f"      DNS: {lb['DNSName']}")
            print(f"      State: {lb['State']['Code']}")
            
            # Get target groups
            tg_response = elbv2.describe_target_groups(LoadBalancerArn=lb['LoadBalancerArn'])
            for tg in tg_response['TargetGroups']:
                print(f"      Target Group: {tg['TargetGroupName']}")
                print(f"         Type: {tg['TargetType']}")
                print(f"         Port: {tg['Port']}")
                print(f"         Health Check: {tg['HealthCheckPath']} (interval: {tg['HealthCheckIntervalSeconds']}s)")
                
                # Check target health
                targets_response = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])
                if targets_response['TargetHealthDescriptions']:
                    print(f"         Targets:")
                    for target in targets_response['TargetHealthDescriptions']:
                        target_id = target['Target']['Id']
                        target_port = target['Target'].get('Port', 'N/A')
                        health_state = target['TargetHealth']['State']
                        health_reason = target['TargetHealth'].get('Reason', '')
                        print(f"            🎯 {target_id}:{target_port} - {health_state}")
                        if health_reason:
                            print(f"               Reason: {health_reason}")
                else:
                    print(f"         ⚠️  No targets registered")
    except Exception as e:
        print(f"   ❌ Error checking load balancers: {e}")
    
    # 4. Check EC2 Instances
    print("\n4. EC2 INSTANCES:")
    try:
        instances_response = ec2.describe_instances(
            Filters=[
                {'Name': 'instance-state-name', 'Values': ['running', 'pending']},
                {'Name': 'tag:Cluster', 'Values': ['*']}  # ECS instances should have cluster tag
            ]
        )
        
        for reservation in instances_response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                instance_type = instance['InstanceType']
                state = instance['State']['Name']
                
                # Get cluster tag
                cluster_tag = 'Unknown'
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Cluster':
                        cluster_tag = tag['Value']
                        break
                
                print(f"   🖥️  {instance_id} ({instance_type}) - {state}")
                print(f"      Cluster: {cluster_tag}")
                print(f"      Private IP: {instance.get('PrivateIpAddress', 'N/A')}")
                
                # Check security groups
                sg_ids = [sg['GroupId'] for sg in instance['SecurityGroups']]
                print(f"      Security Groups: {sg_ids}")
    except Exception as e:
        print(f"   ❌ Error checking EC2 instances: {e}")
    
    # 5. Check Capacity Providers
    print("\n5. CAPACITY PROVIDERS:")
    try:
        cp_response = ecs.describe_capacity_providers()
        for cp in cp_response['capacityProviders']:
            if cp['name'] not in ['FARGATE', 'FARGATE_SPOT']:
                print(f"   ⚙️  {cp['name']}")
                print(f"      Status: {cp['status']}")
                
                asg_provider = cp.get('autoScalingGroupProvider', {})
                if asg_provider:
                    print(f"      ASG: {asg_provider.get('autoScalingGroupArn', 'N/A').split('/')[-1]}")
                    
                    managed_scaling = asg_provider.get('managedScaling', {})
                    if managed_scaling:
                        print(f"      Managed Scaling: {managed_scaling.get('status', 'Unknown')}")
                        print(f"      Target Capacity: {managed_scaling.get('targetCapacity', 'N/A')}%")
                        print(f"      Termination Protection: {asg_provider.get('managedTerminationProtection', 'Unknown')}")
    except Exception as e:
        print(f"   ❌ Error checking capacity providers: {e}")
    
    print("\n" + "=" * 60)
    print("🏁 DEBUG COMPLETE")

if __name__ == "__main__":
    debug_deployment_issues()