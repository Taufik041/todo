terraform {
  required_version = ">=1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  backend "s3" {
    bucket         = "taufik-todo-tfstate"
    key            = "eks/terraform.tfstate"
    region         = "ap-south-1"
    use_lockfile     = true
  }
}


provider "aws" {
  region = "ap-south-1"
}
