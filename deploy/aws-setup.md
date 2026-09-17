# CoWorkHub — AWS setup guide

This guide walks through provisioning a production-ready deployment of
CoWorkHub on **AWS** using **EC2** as the compute tier. It covers everything a
new operator needs: VPC, security groups, RDS PostgreSQL, S3, SES, IAM roles
and policies, Secrets Manager, EC2 provisioning, DNS + TLS, CloudWatch Logs,
and post-deploy verification.

An optional ECS Fargate variant is included at the end for teams that prefer
managed containers.

> **Convention.** Replace values inside `<angle brackets>` with your own before
> running commands. All examples assume region `us-east-1`; adjust as needed.

> **India-first defaults.** CoWorkHub ships with **INR / ₹**, Indian number
> grouping (`12,34,56,789`), **`Asia/Kolkata`** timezone, `%d-%b-%Y` date
> format, and **GST 18%** pre-configured. For lowest latency to Indian
> customers, use region **`ap-south-1` (Mumbai)** everywhere in this guide —
> RDS, S3, SES, EC2, and ALB. All of these defaults can be changed after
> deployment from **Admin → System settings**.

---

## 0. Prerequisites

- An AWS account with admin (or equivalent) access.
- AWS CLI v2 installed and authenticated: `aws configure`.
- A public DNS domain you can create records in (Route 53 is easiest).
- Docker installed locally if you want to build/push the image from your
  workstation instead of on the EC2 host.

**Target architecture**

```
                  ┌────────────┐
   users ───►     │ Route 53   │ coworkhub.example.com
                  └─────┬──────┘
                        │ ALIAS
                  ┌─────▼──────┐        ┌──────────────┐
                  │    ALB     │──►     │  ACM cert    │
                  │ (HTTPS 443)│        └──────────────┘
                  └─────┬──────┘
                        │ HTTP 8000
                 ┌──────▼───────┐
                 │   EC2 (asg)  │  Docker container → gunicorn (Flask)
                 │  IAM role    │
                 └──────┬───────┘
             ┌──────────┼─────────────┬────────────────┐
             ▼          ▼             ▼                ▼
       ┌──────────┐ ┌────────┐ ┌───────────────┐ ┌──────────────┐
       │ RDS      │ │  S3    │ │ SES (email)   │ │ Secrets Mgr  │
       │ Postgres │ │documents │ notifications │ │ DB + Flask   │
       └──────────┘ └────────┘ └───────────────┘ └──────────────┘
```

You can start with a single EC2 (no ALB) and add the ALB + Auto Scaling later.

---

## 1. Naming & IDs (fill this in first)

Pick names once; the rest of the guide reuses them.

| Placeholder | Example | Your value |
|-------------|---------|------------|
| `<REGION>` | `us-east-1` | |
| `<ACCOUNT_ID>` | `123456789012` | |
| `<DOMAIN>` | `coworkhub.example.com` | |
| `<VPC_CIDR>` | `10.20.0.0/16` | |
| `<APP_SG>` | `sg-app-coworkhub` | |
| `<DB_SG>` | `sg-db-coworkhub` | |
| `<ALB_SG>` | `sg-alb-coworkhub` | |
| `<S3_BUCKET>` | `coworkhub-docs-prod-<ACCOUNT_ID>` | |
| `<DB_INSTANCE>` | `coworkhub-prod` | |
| `<DB_MASTER_USER>` | `coworkhub` | |
| `<APP_INSTANCE_ROLE>` | `CoWorkHubAppRole` | |
| `<KEY_PAIR>` | `coworkhub-ec2` | |

Export them into the shell you'll run commands from:

```bash
export REGION=ap-south-1              # Mumbai — recommended for India
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export DOMAIN=coworkhub.example.com
export S3_BUCKET=coworkhub-docs-prod-$ACCOUNT_ID
```

---

## 2. Networking (VPC, subnets, security groups)

If you already have a VPC, skip to security groups.

### 2.1 Create VPC + subnets

```bash
# VPC
VPC_ID=$(aws ec2 create-vpc --cidr-block 10.20.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=coworkhub}]' \
  --query Vpc.VpcId --output text)

aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames

# Two public subnets (for ALB + NAT), two private subnets (for EC2 + RDS)
PUB_A=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.20.1.0/24 \
    --availability-zone ${REGION}a --query Subnet.SubnetId --output text)
PUB_B=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.20.2.0/24 \
    --availability-zone ${REGION}b --query Subnet.SubnetId --output text)
PRIV_A=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.20.11.0/24 \
    --availability-zone ${REGION}a --query Subnet.SubnetId --output text)
PRIV_B=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.20.12.0/24 \
    --availability-zone ${REGION}b --query Subnet.SubnetId --output text)

# IGW + default route for public subnets, NAT GW for private subnets
IGW=$(aws ec2 create-internet-gateway --query InternetGateway.InternetGatewayId --output text)
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW
# ... (create route tables, NAT, EIP as usual)
```

For a smaller footprint you can start with **two public subnets only** and put
EC2 there directly. Skip the NAT GW to save ~$32/month. For anything customer-
facing, place EC2 in private subnets behind an ALB.

### 2.2 Security groups

Three groups, layered:

| SG | Inbound | Outbound |
|----|---------|----------|
| `<ALB_SG>` | 443 from `0.0.0.0/0`, 80 from `0.0.0.0/0` (redirect) | all |
| `<APP_SG>` | 8000 from `<ALB_SG>` (or 80/443 from `0.0.0.0/0` if no ALB), 22 from your admin IP | all |
| `<DB_SG>` | 5432 from `<APP_SG>` only | none needed |

```bash
ALB_SG=$(aws ec2 create-security-group --vpc-id $VPC_ID \
  --group-name coworkhub-alb --description "ALB" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80  --cidr 0.0.0.0/0

APP_SG=$(aws ec2 create-security-group --vpc-id $VPC_ID \
  --group-name coworkhub-app --description "App EC2" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $APP_SG --protocol tcp --port 8000 --source-group $ALB_SG
aws ec2 authorize-security-group-ingress --group-id $APP_SG --protocol tcp --port 22   --cidr <YOUR_ADMIN_IP>/32

DB_SG=$(aws ec2 create-security-group --vpc-id $VPC_ID \
  --group-name coworkhub-db --description "Postgres" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $DB_SG --protocol tcp --port 5432 --source-group $APP_SG
```

---

## 3. RDS PostgreSQL

The app needs Postgres 14+. Recommended: **db.t4g.small** for staging,
**db.m6g.large** for production with Multi-AZ.

```bash
# Subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name coworkhub-db-subnets \
  --db-subnet-group-description "CoWorkHub DB subnets" \
  --subnet-ids $PRIV_A $PRIV_B

# Generate a strong password and stash it in Secrets Manager (step 6)
DB_PASSWORD=$(openssl rand -base64 24 | tr -d '=+/' | cut -c1-32)

aws rds create-db-instance \
  --db-instance-identifier coworkhub-prod \
  --engine postgres --engine-version 16.4 \
  --db-instance-class db.t4g.small \
  --allocated-storage 20 --storage-type gp3 --storage-encrypted \
  --master-username coworkhub --master-user-password "$DB_PASSWORD" \
  --db-name coworkhub \
  --vpc-security-group-ids $DB_SG \
  --db-subnet-group-name coworkhub-db-subnets \
  --backup-retention-period 7 \
  --deletion-protection \
  --publicly-accessible false \
  --multi-az   # remove for staging
```

When it becomes `available`:

```bash
DB_HOST=$(aws rds describe-db-instances --db-instance-identifier coworkhub-prod \
  --query 'DBInstances[0].Endpoint.Address' --output text)
echo $DB_HOST
```

Your `DATABASE_URL` will be:

```
postgresql+psycopg2://coworkhub:<DB_PASSWORD>@<DB_HOST>:5432/coworkhub?sslmode=require
```

---

## 4. S3 bucket for documents

CoWorkHub stores contracts, KYC files, floor maps, and invoice PDFs in S3
(prefix `documents/` by default). The bucket must be **private**; the app
generates signed URLs when serving them.

```bash
aws s3api create-bucket --bucket $S3_BUCKET --region $REGION \
  --create-bucket-configuration LocationConstraint=$REGION

# Block all public access
aws s3api put-public-access-block --bucket $S3_BUCKET \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

# Server-side encryption (SSE-S3; upgrade to SSE-KMS if you need per-bucket keys)
aws s3api put-bucket-encryption --bucket $S3_BUCKET \
  --server-side-encryption-configuration '{
    "Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]
  }'

# Versioning (recovery from accidental deletes)
aws s3api put-bucket-versioning --bucket $S3_BUCKET \
  --versioning-configuration Status=Enabled

# Lifecycle: move old versions to Glacier after 90 days
aws s3api put-bucket-lifecycle-configuration --bucket $S3_BUCKET \
  --lifecycle-configuration file://s3-lifecycle.json
```

`s3-lifecycle.json`:

```json
{
  "Rules": [{
    "ID": "archive-old-versions",
    "Status": "Enabled",
    "Filter": { "Prefix": "" },
    "NoncurrentVersionTransitions": [
      { "NoncurrentDays": 90, "StorageClass": "GLACIER" }
    ]
  }]
}
```

---

## 5. SES (transactional email)

Used for booking confirmations, invoice notifications, and password resets.

```bash
# 1) Verify the sender domain (this creates the DKIM records to add to DNS)
aws ses verify-domain-identity --domain coworkhub.example.com --region $REGION
aws ses verify-domain-dkim   --domain coworkhub.example.com --region $REGION
# Add the returned CNAME records to Route 53.

# 2) Verify at least one "From" email (or use no-reply@coworkhub.example.com after domain verification)
aws ses verify-email-identity --email-address no-reply@coworkhub.example.com --region $REGION

# 3) Request production access (out of sandbox) — required to email non-verified addresses:
#    https://console.aws.amazon.com/ses/home#/account
```

Create **SMTP credentials** for the app to use (SES SMTP is separate from your
IAM console user):

```
SES Console → SMTP settings → Create SMTP credentials
```

This produces `MAIL_USERNAME` and `MAIL_PASSWORD`. Point the app at the SMTP
endpoint for your region, e.g.:

```
MAIL_SERVER=email-smtp.us-east-1.amazonaws.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_DEFAULT_SENDER=no-reply@coworkhub.example.com
```

Alternative: skip SMTP and use SES SendEmail via boto3 (add code in
`app/services/notification.py`). SMTP works out of the box with Flask-Mail.

---

## 6. Secrets Manager

Store the DB password and the Flask `SECRET_KEY` centrally. The EC2 instance
role will be granted `secretsmanager:GetSecretValue` on these ARNs only.

```bash
FLASK_SECRET=$(openssl rand -hex 32)

aws secretsmanager create-secret --name coworkhub/prod/db_password \
  --secret-string "$DB_PASSWORD"

aws secretsmanager create-secret --name coworkhub/prod/flask_secret \
  --secret-string "$FLASK_SECRET"

aws secretsmanager create-secret --name coworkhub/prod/smtp_password \
  --secret-string "<SES_SMTP_PASSWORD>"
```

Capture the ARNs — you'll paste them into the IAM policy in the next step.

---

## 7. IAM: instance role + policies

Create one **IAM role** that the EC2 instance assumes. It gets three scoped
policies: S3 for documents, SES for sending mail, Secrets Manager for secrets.
(Optional: CloudWatch Logs for shipping stdout.)

### 7.1 Trust policy — allow EC2 to assume the role

`ec2-trust.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
```

```bash
aws iam create-role --role-name CoWorkHubAppRole \
  --assume-role-policy-document file://ec2-trust.json
```

### 7.2 Attach AWS-managed policies

```bash
# So the instance can send logs & metrics
aws iam attach-role-policy --role-name CoWorkHubAppRole \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

# For SSM Session Manager (no SSH needed)
aws iam attach-role-policy --role-name CoWorkHubAppRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
```

### 7.3 Custom S3 policy (scoped to the documents bucket)

`s3-policy.json` — replace `<S3_BUCKET>`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::<S3_BUCKET>"
    },
    {
      "Sid": "RWObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:AbortMultipartUpload"
      ],
      "Resource": "arn:aws:s3:::<S3_BUCKET>/*"
    }
  ]
}
```

```bash
aws iam create-policy --policy-name CoWorkHubS3Access \
  --policy-document file://s3-policy.json

aws iam attach-role-policy --role-name CoWorkHubAppRole \
  --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/CoWorkHubS3Access
```

### 7.4 Custom SES policy

`ses-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ses:SendEmail", "ses:SendRawEmail"],
    "Resource": "*",
    "Condition": {
      "StringEquals": {
        "ses:FromAddress": "no-reply@coworkhub.example.com"
      }
    }
  }]
}
```

`ses:FromAddress` scoping prevents leaked creds from being used to spoof other
senders in your account.

```bash
aws iam create-policy --policy-name CoWorkHubSESAccess \
  --policy-document file://ses-policy.json
aws iam attach-role-policy --role-name CoWorkHubAppRole \
  --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/CoWorkHubSESAccess
```

### 7.5 Secrets Manager policy

`secrets-policy.json` — paste in the three ARNs from step 6:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "secretsmanager:GetSecretValue",
    "Resource": [
      "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:coworkhub/prod/db_password-*",
      "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:coworkhub/prod/flask_secret-*",
      "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:coworkhub/prod/smtp_password-*"
    ]
  }]
}
```

```bash
aws iam create-policy --policy-name CoWorkHubSecretsAccess \
  --policy-document file://secrets-policy.json
aws iam attach-role-policy --role-name CoWorkHubAppRole \
  --policy-arn arn:aws:iam::$ACCOUNT_ID:policy/CoWorkHubSecretsAccess
```

### 7.6 Instance profile

EC2 launches assume a *profile* that wraps the role:

```bash
aws iam create-instance-profile --instance-profile-name CoWorkHubAppProfile
aws iam add-role-to-instance-profile \
  --instance-profile-name CoWorkHubAppProfile --role-name CoWorkHubAppRole
```

---

## 8. Build & push the container image (ECR)

```bash
aws ecr create-repository --repository-name coworkhub \
  --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

docker build -t coworkhub .
docker tag coworkhub $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/coworkhub:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/coworkhub:latest
```

---

## 9. Launch the EC2 instance

Use Amazon Linux 2023 (or Ubuntu 24.04). Recommended size: **t3.small** to
start; scale up or add ASG later.

### 9.1 User data script (bootstrap on first boot)

Save as `user-data.sh`. It installs Docker, logs into ECR, pulls secrets, and
starts the container. `<ACCOUNT_ID>`, `<REGION>`, `<S3_BUCKET>`, `<DOMAIN>`,
and `<DB_HOST>` are substituted before you paste it.

```bash
#!/bin/bash
set -euo pipefail

REGION=us-east-1
ACCOUNT_ID=<ACCOUNT_ID>
IMAGE=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/coworkhub:latest
S3_BUCKET=<S3_BUCKET>
DB_HOST=<DB_HOST>
DOMAIN=<DOMAIN>

# 1. Install docker + awscli
dnf update -y
dnf install -y docker jq
systemctl enable --now docker

# 2. Pull secrets from Secrets Manager
DB_PASSWORD=$(aws secretsmanager get-secret-value --region $REGION \
  --secret-id coworkhub/prod/db_password  --query SecretString --output text)
FLASK_SECRET=$(aws secretsmanager get-secret-value --region $REGION \
  --secret-id coworkhub/prod/flask_secret --query SecretString --output text)
SMTP_PASSWORD=$(aws secretsmanager get-secret-value --region $REGION \
  --secret-id coworkhub/prod/smtp_password --query SecretString --output text)

# 3. Write app env file consumed by systemd
mkdir -p /etc/coworkhub
cat > /etc/coworkhub/app.env <<EOF
FLASK_ENV=production
APP_NAME=CoWorkHub
APP_BASE_URL=https://$DOMAIN
SECRET_KEY=$FLASK_SECRET
DATABASE_URL=postgresql+psycopg2://coworkhub:$DB_PASSWORD@$DB_HOST:5432/coworkhub?sslmode=require

STORAGE_BACKEND=s3
AWS_REGION=$REGION
AWS_S3_BUCKET=$S3_BUCKET
AWS_S3_PREFIX=documents/
AWS_S3_URL_TTL=3600

MAIL_SERVER=email-smtp.$REGION.amazonaws.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=<SES_SMTP_USERNAME>
MAIL_PASSWORD=$SMTP_PASSWORD
MAIL_DEFAULT_SENDER=no-reply@$DOMAIN

BOOTSTRAP_ADMIN_EMAIL=admin@$DOMAIN
BOOTSTRAP_ADMIN_PASSWORD=$(openssl rand -base64 18)
EOF
chmod 600 /etc/coworkhub/app.env

# 4. Pull image
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
docker pull $IMAGE

# 5. systemd unit — restarts on crash, restarts on reboot
cat > /etc/systemd/system/coworkhub.service <<EOF
[Unit]
Description=CoWorkHub web
After=docker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=5s
ExecStartPre=-/usr/bin/docker rm -f coworkhub
ExecStart=/usr/bin/docker run --rm --name coworkhub \\
  --env-file /etc/coworkhub/app.env \\
  -p 8000:8000 $IMAGE
ExecStop=/usr/bin/docker stop coworkhub

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now coworkhub

# 6. First-boot schema init + seed
sleep 20   # give the container time to open the DB
docker exec coworkhub flask --app wsgi.py db upgrade
docker exec coworkhub flask --app wsgi.py seed-demo || true
```

> Store the auto-generated bootstrap admin password by tailing the boot log
> (`sudo journalctl -u coworkhub | grep BOOTSTRAP_ADMIN_PASSWORD`) — or replace
> the `openssl rand` line with a value you generate yourself and log into a
> secrets store.

### 9.2 Launch

```bash
# Latest Amazon Linux 2023 AMI
AMI=$(aws ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64 \
  --query 'Parameter.Value' --output text)

aws ec2 run-instances \
  --image-id $AMI \
  --instance-type t3.small \
  --key-name coworkhub-ec2 \
  --iam-instance-profile Name=CoWorkHubAppProfile \
  --security-group-ids $APP_SG \
  --subnet-id $PRIV_A \
  --user-data file://user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=coworkhub-app}]'
```

If you don't have a NAT GW, launch into `$PUB_A` with `--associate-public-ip-address`.

---

## 10. Application Load Balancer + TLS

### 10.1 Request an ACM certificate

```bash
CERT_ARN=$(aws acm request-certificate \
  --domain-name $DOMAIN \
  --validation-method DNS \
  --query CertificateArn --output text)
```

Add the returned CNAME record to Route 53 to validate.

### 10.2 Create ALB + target group

```bash
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name coworkhub-alb --type application \
  --subnets $PUB_A $PUB_B --security-groups $ALB_SG \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

TG_ARN=$(aws elbv2 create-target-group \
  --name coworkhub-tg --protocol HTTP --port 8000 \
  --vpc-id $VPC_ID --target-type instance \
  --health-check-path /healthz \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

aws elbv2 register-targets --target-group-arn $TG_ARN --targets Id=$INSTANCE_ID

aws elbv2 create-listener --load-balancer-arn $ALB_ARN \
  --protocol HTTPS --port 443 \
  --certificates CertificateArn=$CERT_ARN \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

# Optional 80→443 redirect
aws elbv2 create-listener --load-balancer-arn $ALB_ARN \
  --protocol HTTP --port 80 \
  --default-actions '[{"Type":"redirect","RedirectConfig":{"Protocol":"HTTPS","Port":"443","StatusCode":"HTTP_301"}}]'
```

### 10.3 Point Route 53 at the ALB

```bash
ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name example.com \
  --query 'HostedZones[0].Id' --output text | sed 's|/hostedzone/||')

ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].DNSName' --output text)
ALB_ZONE=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].CanonicalHostedZoneId' --output text)

aws route53 change-resource-record-sets --hosted-zone-id $ZONE_ID --change-batch "{
  \"Changes\": [{
    \"Action\": \"UPSERT\",
    \"ResourceRecordSet\": {
      \"Name\": \"$DOMAIN\", \"Type\": \"A\",
      \"AliasTarget\": {
        \"HostedZoneId\": \"$ALB_ZONE\",
        \"DNSName\": \"$ALB_DNS\",
        \"EvaluateTargetHealth\": true
      }
    }
  }]
}"
```

---

## 11. Logging & monitoring

- **Container logs → CloudWatch Logs.** Change the `docker run` line in the
  user-data to `--log-driver=awslogs --log-opt awslogs-region=$REGION
  --log-opt awslogs-group=/coworkhub/app --log-opt awslogs-create-group=true`.
- **CloudWatch metrics.** Enable detailed monitoring on the instance and add
  CloudWatch Agent (already permitted by `CloudWatchAgentServerPolicy`).
- **RDS Performance Insights.** Enable in the RDS console for query-level
  diagnostics.
- **Alarms.** At minimum:
  - ALB `HTTPCode_Target_5XX_Count` > 5 for 5 min
  - EC2 CPU > 80% for 10 min
  - RDS FreeStorageSpace < 5 GB
  - RDS CPUUtilization > 80%
  - SES Bounce/Complaint rate > 1%

---

## 12. First-time app setup

Once the EC2 is running and the ALB shows the target as `healthy`:

```bash
# Confirm health
curl -f https://$DOMAIN/healthz

# Log in as the auto-generated admin
sudo journalctl -u coworkhub | grep BOOTSTRAP_ADMIN_PASSWORD   # on the EC2
open https://$DOMAIN/auth/login
```

Then immediately:

1. Rotate the admin password.
2. Delete the seeded `jane@acme.example` / `alex@example.com` / `bob@acme.example`
   users if you don't want the demo data in production. Or run without seeding
   by removing the `docker exec ... seed-demo` line from `user-data.sh`.
3. Create your real Location, Floors, Seats, Rooms, and PricingPlans through
   the admin UI.
4. Add SES domain **DKIM** records to Route 53 if not done in step 5.
5. Move SES out of the sandbox in the AWS console.

---

## 12a. What `flask seed-demo` inserts (India defaults)

The CLI command runs idempotently on every boot. It only inserts rows that
don't already exist, so re-running is safe. Everything below can be edited
from the admin UI after boot.

### System settings (single row)

Written to `system_settings`, editable at **Admin → System settings** (super
admin only):

| Field | Default |
|---|---|
| Currency code / symbol | `INR` · `₹` |
| Locale · number grouping | `en_IN` · Indian (`12,34,56,789`) |
| Timezone | `Asia/Kolkata` |
| Date format | `%d-%b-%Y` (e.g. `17-Sep-2026`) |
| Datetime format | `%d-%b-%Y %H:%M` |
| Default tax rate · label | `18.00%` · `GST` |
| Invoice prefix | `INV` |

### Users (all with password `ChangeMe123!` — rotate on first login)

| Role | Email |
|---|---|
| Super Admin | `admin@coworkhub.io` |
| CoWorkHub Manager | `manager@coworkhub.io` |
| Company Admin (Acme Robotics) | `jane@acme.example` |
| Employee (Acme Robotics) | `bob@acme.example` |
| Individual member | `alex@example.com` |

### Location: `BLR-01` — CoWorkHub Bengaluru (Indiranagar)

- Address: 100 Feet Road, Bengaluru, KA 560038, India
- Timezone: `Asia/Kolkata`
- Hours: 07:00 – 22:00
- **4 floors**: Ground (Lounge), L5 (Hot Desks), L6 (Dedicated Desks), L7 (Private Offices)
- **35 seats**:
  - 20 hot desks — ₹150/hr · ₹900/day · ₹12,000/month
  - 10 dedicated desks — ₹22,000/month
  - 5 private offices (capacity 4) — ₹85,000/month
- **4 conference rooms**:
  - The Boardroom (12p) — ₹2,400/hr · 2 credits/hr
  - Cauvery (6p) — ₹1,200/hr · 1 credit/hr
  - Krishna (4p) — ₹800/hr · 1 credit/hr
  - Executive Suite (8p) — ₹1,800/hr · 2 credits/hr

### Pricing plans (INR)

| Name | Type | Cycle | Price | Included credits |
|---|---|---|---|---|
| Day Pass | day pass | daily | ₹900 | 0 |
| Hot Desk Monthly | hot desk | monthly | ₹12,000 | 8 |
| All Access | all access | monthly | ₹18,000 | 12 |
| Dedicated Desk | dedicated desk | monthly | ₹22,000 | 20 |
| Private Office (4-person) | private office | monthly | ₹85,000 | 40 |

### Company + subscription

- **Acme Robotics** — Active status, max 25 employees
- 1 active `Dedicated Desk` subscription × 5 quantity → 100 meeting credits pool

### Amenities

- Location amenities: Wi-Fi, Coffee, Printing, Phone booths, Kitchen, Shower, Bike storage
- Room amenities: TV Screen, Whiteboard, Video Conference, Speakerphone

### Skipping the seed in production

If you do not want the demo data in production, remove this line from the
`user-data.sh` bootstrap script (step 9):

```bash
docker exec coworkhub flask --app wsgi.py seed-demo || true
```

Then create your real data through **Admin → New location**, **Admin →
Companies**, **Admin → Pricing plans** in the UI.

### Removing existing demo data

If you already seeded and want to remove the demo tenant:

```bash
# On the EC2 host, exec into the container:
docker exec -it coworkhub flask shell
>>> from app.extensions import db
>>> from app.models import User, Company
>>> User.query.filter(User.email.in_([
...   'jane@acme.example','bob@acme.example','alex@example.com'
... ])).delete(synchronize_session=False)
>>> Company.query.filter_by(name='Acme Robotics').delete()
>>> db.session.commit()
```


---

## 13. Ops runbook

| Task | Command |
|------|---------|
| SSH via SSM (no keys) | `aws ssm start-session --target <INSTANCE_ID>` |
| Tail app logs | `sudo journalctl -u coworkhub -f` |
| Roll a new image | Push tag → on host: `docker pull ...:latest && systemctl restart coworkhub` |
| Run migrations | `docker exec coworkhub flask --app wsgi.py db upgrade` |
| Manual billing run | `docker exec coworkhub flask --app wsgi.py billing-run` (add EventBridge schedule later) |
| DB snapshot | `aws rds create-db-snapshot --db-instance-identifier coworkhub-prod --db-snapshot-identifier coworkhub-$(date +%F)` |
| Rotate `SECRET_KEY` | `aws secretsmanager update-secret --secret-id coworkhub/prod/flask_secret --secret-string $(openssl rand -hex 32)` then restart the service |

---

## 14. Alternative: ECS Fargate

If you don't want to manage EC2, replace section 9 with:

1. `aws ecs create-cluster --cluster-name coworkhub`.
2. Create a **task definition** referencing the ECR image, with the
   `CoWorkHubAppRole` as the **task role** (S3/SES/Secrets access) and the AWS
   managed `AmazonECSTaskExecutionRolePolicy` on the **execution role** (pulls
   ECR + writes logs).
3. Reference secrets from Secrets Manager via the `secrets` field of the task
   definition — no need to fetch them at boot.
4. `aws ecs create-service ... --launch-type FARGATE --desired-count 2
   --load-balancers targetGroupArn=$TG_ARN,containerName=web,containerPort=8000`.

Everything else (VPC, ALB, RDS, S3, SES, IAM) is identical.

---

## 15. Cost estimate (small production, US East 1)

| Item | Approx / month |
|------|----------------|
| RDS db.t4g.small (Multi-AZ) + 20 GB gp3 | $65 |
| EC2 t3.small (single AZ) | $15 |
| ALB | $18 + traffic |
| S3 (10 GB + requests) | $1 |
| SES (10k emails) | $1 |
| CloudWatch Logs + metrics | $5 |
| Route 53 hosted zone | $0.50 |
| **Total** | **≈ $105 / month** |

Enable **Savings Plans** on EC2/RDS once traffic stabilises to trim 20–30%.

---

## 16. Security checklist

- [ ] RDS is `publicly-accessible false` and only reachable from `$APP_SG`.
- [ ] S3 bucket has **Block Public Access = ON**, versioning enabled, SSE
      enabled.
- [ ] EC2 role has **only** the four policies above; no `s3:*` or `ses:*`.
- [ ] SES `ses:FromAddress` condition restricts the sender.
- [ ] `SECRET_KEY` and DB password live in Secrets Manager, not in AMIs or
      environment variables checked into git.
- [ ] `.env` files are in `.gitignore` (they are).
- [ ] EC2 access is via SSM Session Manager, not open port 22.
- [ ] ACM cert auto-renews; TLS 1.2+ only on the ALB listener.
- [ ] Rotate `admin@coworkhub.io` password on first login.
- [ ] Delete demo users (`jane@acme.example`, `alex@example.com`,
      `bob@acme.example`) before onboarding real customers, or skip
      `seed-demo` entirely.
- [ ] Turn on **CloudTrail** in the account.
- [ ] Add a WAF WebACL on the ALB (optional; adds ~$5/month + $1/rule).
