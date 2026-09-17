"""AWS-hosting notes.

Recommended stack:

1. **ECR** — build & push the Docker image from repo Dockerfile.
2. **RDS PostgreSQL** — create DB, copy the connection string into
   Secrets Manager as `coworkhub/DATABASE_URL`.
3. **S3** — create a private bucket, e.g. `coworkhub-docs-prod`. Set env:
       STORAGE_BACKEND=s3
       AWS_S3_BUCKET=coworkhub-docs-prod
       AWS_REGION=us-east-1
   Attach an IAM role to the ECS task with `s3:PutObject`, `s3:GetObject`,
   `s3:DeleteObject` on `arn:aws:s3:::coworkhub-docs-prod/*`.
4. **ECS Fargate service** — 2 vCPU / 4 GB, gunicorn on port 8000, ALB
   in front, health check `/healthz`.
5. **SES** — verified sender for MAIL_DEFAULT_SENDER; use SMTP creds.
6. **CloudFront** in front of S3 for public assets (optional).
7. **CloudWatch** for logs/metrics; alarm on 5xx from ALB.
8. **EventBridge schedule** to hit an internal endpoint that runs monthly
   billing (or run `flask billing-run` as a scheduled ECS task).

## Suggested Terraform layout

```
deploy/
  terraform/
    modules/
      network/         # VPC, subnets
      db/              # RDS
      storage/         # S3 + IAM
      compute/         # ECS + ALB
    envs/
      dev/
      prod/
```

Left as an exercise — the app itself is 12-factor and reads all config
from env vars.
"""
