terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    # Configure your backend settings
    bucket = "autoform-terraform"
    key    = "autoform/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# Data source to get availability zones
data "aws_availability_zones" "available" {
  state = "available"
}

# Use the existing VPC
data "aws_vpc" "selected" {
  id = var.vpc_id
}