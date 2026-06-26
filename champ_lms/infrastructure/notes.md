# Infrastructure Notes

Follow Part 14 of MVP_PLAN.md for full step-by-step AWS deployment.

## Quick Reference — AWS Resources to Create

### IAM Roles
- `champ-lms-ecs-task` — ECS task role
- `champ-lms-mediaconvert` — MediaConvert service role  
- `champ-lms-lambda-trigger` — Lambda #1 + #2
- `champ-lms-zoom-lambda` — Lambda #3 (Zoom processor)

### S3 Buckets (all private)
- `champ-lms-raw-videos`
- `champ-lms-hls`
- `champ-lms-frontend`
- `champ-lms-thumbnails`

### ECS
- Build Docker image: `docker build -t champ-lms-api ./backend`
- Push to ECR: see `ecr_push.sh` (create this after ECR repo is made)

### Lambda Deployment
Each Lambda in `lambdas/` is a standalone zip:
```bash
cd lambdas/trigger_mediaconvert && zip -r function.zip . && aws lambda update-function-code ...
```

### Environment Variables in Production
Store all secrets in AWS Secrets Manager under prefix `champ-lms/`.
ECS task definition references them via `secrets` block (not env vars).

### CloudFront Key Pair
Generate at: AWS Console → CloudFront → Key management → Public keys
Store the private key PEM in Secrets Manager as `champ-lms/cloudfront-private-key`.
