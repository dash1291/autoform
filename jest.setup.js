// Global test setup
if (process.env.NODE_ENV === 'test') {
  // Set up LocalStack endpoints for integration tests
  process.env.AWS_ACCESS_KEY_ID = 'test';
  process.env.AWS_SECRET_ACCESS_KEY = 'test';
  process.env.AWS_SESSION_TOKEN = 'test';
  process.env.AWS_DEFAULT_REGION = 'us-east-1';
  
  // LocalStack endpoints
  process.env.LOCALSTACK_ENDPOINT = 'http://localhost:4566';
}