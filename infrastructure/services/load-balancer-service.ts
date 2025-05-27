import * as AWS from 'aws-sdk';

export interface LoadBalancerServiceConfig {
  projectName: string;
  region?: string;
  vpcId: string;
  subnetIds: string[];
  securityGroupId: string;
  containerPort?: number;
}

export class LoadBalancerService {
  private elbv2: AWS.ELBv2;
  private projectName: string;
  private region: string;
  private containerPort: number;
  
  public loadBalancerArn: string;
  public loadBalancerDns: string;
  public targetGroupArn: string;
  public listenerArn: string;

  constructor(private config: LoadBalancerServiceConfig) {
    this.projectName = config.projectName;
    this.region = config.region || 'us-east-1';
    this.containerPort = config.containerPort || 3000;
    
    AWS.config.update({ region: this.region });
    this.elbv2 = new AWS.ELBv2();
  }

  async initialize(): Promise<void> {
    // Create or find load balancer
    const lbResult = await this.createOrFindLoadBalancer();
    this.loadBalancerArn = lbResult.arn;
    this.loadBalancerDns = lbResult.dns;

    // Create target group
    this.targetGroupArn = await this.createTargetGroup();

    // Create listener
    this.listenerArn = await this.createListener();
  }

  private async createOrFindLoadBalancer(): Promise<{ arn: string; dns: string }> {
    try {
      // Check if load balancer already exists
      const lbs = await this.elbv2.describeLoadBalancers({
        Names: [`${this.projectName}-alb`]
      }).promise();

      if (lbs.LoadBalancers && lbs.LoadBalancers.length > 0) {
        const lb = lbs.LoadBalancers[0];
        console.log(`Found existing load balancer: ${lb.LoadBalancerArn}`);
        return {
          arn: lb.LoadBalancerArn!,
          dns: lb.DNSName!
        };
      }
    } catch (error) {
      console.log('No existing load balancer found, creating new one');
    }

    // Create new load balancer
    const result = await this.elbv2.createLoadBalancer({
      Name: `${this.projectName}-alb`,
      Subnets: this.config.subnetIds,
      SecurityGroups: [this.config.securityGroupId],
      Tags: [{ Key: 'Name', Value: `${this.projectName}-alb` }]
    }).promise();

    const lb = result.LoadBalancers![0];
    console.log(`Created new load balancer: ${lb.LoadBalancerArn}`);
    
    return {
      arn: lb.LoadBalancerArn!,
      dns: lb.DNSName!
    };
  }

  private async createTargetGroup(): Promise<string> {
    // Always create a new target group (they're cheap and ensure fresh health checks)
    const result = await this.elbv2.createTargetGroup({
      Name: `${this.projectName}-tg`,
      Port: this.containerPort,
      Protocol: 'HTTP',
      VpcId: this.config.vpcId,
      TargetType: 'ip',
      HealthCheckEnabled: true,
      HealthCheckIntervalSeconds: 30,
      HealthCheckPath: '/health',
      HealthCheckPort: 'traffic-port',
      HealthCheckProtocol: 'HTTP',
      HealthCheckTimeoutSeconds: 5,
      HealthyThresholdCount: 2,
      UnhealthyThresholdCount: 2,
      Matcher: { HttpCode: '200' },
      Tags: [{ Key: 'Name', Value: `${this.projectName}-tg` }]
    }).promise();

    const targetGroup = result.TargetGroups![0];
    console.log(`Created target group: ${targetGroup.TargetGroupArn}`);
    return targetGroup.TargetGroupArn!;
  }

  private async createListener(): Promise<string> {
    try {
      // Check if listener already exists
      const listeners = await this.elbv2.describeListeners({
        LoadBalancerArn: this.loadBalancerArn
      }).promise();

      // Update existing listener to point to new target group
      if (listeners.Listeners && listeners.Listeners.length > 0) {
        const listener = listeners.Listeners[0];
        
        await this.elbv2.modifyListener({
          ListenerArn: listener.ListenerArn!,
          DefaultActions: [{
            Type: 'forward',
            TargetGroupArn: this.targetGroupArn
          }]
        }).promise();

        console.log(`Updated existing listener: ${listener.ListenerArn}`);
        return listener.ListenerArn!;
      }
    } catch (error) {
      console.log('No existing listener found, creating new one');
    }

    // Create new listener
    const result = await this.elbv2.createListener({
      LoadBalancerArn: this.loadBalancerArn,
      Port: 80,
      Protocol: 'HTTP',
      DefaultActions: [{
        Type: 'forward',
        TargetGroupArn: this.targetGroupArn
      }],
      Tags: [{ Key: 'Name', Value: `${this.projectName}-listener` }]
    }).promise();

    const listener = result.Listeners![0];
    console.log(`Created new listener: ${listener.ListenerArn}`);
    return listener.ListenerArn!;
  }
}