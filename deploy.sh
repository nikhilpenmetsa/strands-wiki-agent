#!/bin/bash
echo "Deploying updated frontend and Lambda function..."

# Navigate to the CDK directory
cd "$(dirname "$0")"

# Install dependencies if needed
echo "Installing dependencies..."
npm install

# Build and deploy the CDK stack
echo "Deploying CDK stack..."
npx cdk deploy FrontendStack --require-approval never

# Get the CloudFront distribution ID
echo "Getting CloudFront distribution ID..."
DISTRIBUTION_ID=$(npx cdk list-exports --query "Exports[?Name=='FrontendDistributionId'].Value" --no-version-reporting | tr -d '"')

# Create CloudFront invalidation
echo "Creating CloudFront invalidation for distribution $DISTRIBUTION_ID..."
aws cloudfront create-invalidation --distribution-id $DISTRIBUTION_ID --paths "/*"

echo "Deployment complete!"