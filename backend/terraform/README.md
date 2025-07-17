# Terraform Infrastructure for Autoform

This Terraform configuration sets up PostgreSQL (RDS) and Redis (ElastiCache) in an existing AWS VPC.

## Prerequisites

- Terraform >= 1.0
- AWS CLI configured with appropriate credentials
- An existing VPC with at least 2 subnets in different availability zones

## Usage

1. **Initialize Terraform:**
   ```bash
   terraform init
   ```

2. **Create your variables file:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

3. **Edit `terraform.tfvars`** with your specific values:
   - `vpc_id`: Your existing VPC ID
   - `subnet_ids`: List of subnet IDs (minimum 2 for RDS)
   - `db_password`: Strong password for PostgreSQL
   - `allowed_cidr_blocks`: CIDR blocks that should have access

4. **Plan the deployment:**
   ```bash
   terraform plan
   ```

5. **Apply the configuration:**
   ```bash
   terraform apply
   ```

## Resources Created

- **RDS PostgreSQL Instance**
  - Subnet group
  - Security group
  - PostgreSQL 15.4 instance

- **ElastiCache Redis Cluster**
  - Subnet group
  - Security group
  - Parameter group
  - Redis 7.0 cluster

## Outputs

After successful deployment, Terraform will output:
- RDS endpoint and connection details
- Redis endpoint and connection details
- Security group IDs

## Security Features

- Encryption at rest enabled for both RDS and ElastiCache
- Transit encryption enabled for Redis
- No public access (private subnets only)
- Security groups restrict access to specified CIDR blocks

## State Management

Configure S3 backend in `main.tf` for production use:
```hcl
backend "s3" {
  bucket = "your-terraform-state-bucket"
  key    = "autoform/terraform.tfstate"
  region = "us-east-1"
}
```

## Cleanup

To destroy all resources:
```bash
terraform destroy
```

**Note:** In production, `deletion_protection` is enabled for RDS. You'll need to disable it before destroying.