import * as AWS from 'aws-sdk';

export const createLocalStackConfig = () => {
  return {
    endpoint: process.env.LOCALSTACK_ENDPOINT || 'http://localhost:4566',
    region: 'us-east-1',
    accessKeyId: 'test',
    secretAccessKey: 'test',
    s3ForcePathStyle: true,
    disableSSL: true
  };
};

export const setupLocalStackAWS = () => {
  const config = createLocalStackConfig();
  AWS.config.update(config);
  
  return {
    ec2: new AWS.EC2(config),
    ecs: new AWS.ECS(config),
    elbv2: new AWS.ELBv2(config),
    iam: new AWS.IAM(config),
    logs: new AWS.CloudWatchLogs(config),
    secretsManager: new AWS.SecretsManager(config),
    sts: new AWS.STS(config)
  };
};

export const waitForResource = async (
  checkFn: () => Promise<boolean>,
  timeout: number = 30000,
  interval: number = 1000
): Promise<void> => {
  const start = Date.now();
  
  while (Date.now() - start < timeout) {
    if (await checkFn()) {
      return;
    }
    await new Promise(resolve => setTimeout(resolve, interval));
  }
  
  throw new Error(`Resource not ready after ${timeout}ms`);
};

export const generateTestProjectName = (): string => {
  return `test-project-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};