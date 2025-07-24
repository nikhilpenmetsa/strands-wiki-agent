@echo off
echo Deploying updated frontend and Lambda function...

REM Navigate to the CDK directory
cd /d %~dp0

REM Install dependencies if needed
echo Installing dependencies...
npm install

REM Build and deploy the CDK stack
echo Deploying CDK stack...
npx cdk deploy FrontendStack --require-approval never

REM Get the CloudFront distribution ID
echo Getting CloudFront distribution ID...
for /f "tokens=*" %%a in ('npx cdk list-exports --query "Exports[?Name=='FrontendDistributionId'].Value" --no-version-reporting') do set DISTRIBUTION_ID=%%a

REM Remove quotes from the distribution ID
set DISTRIBUTION_ID=%DISTRIBUTION_ID:"=%

REM Create CloudFront invalidation
echo Creating CloudFront invalidation for distribution %DISTRIBUTION_ID%...
aws cloudfront create-invalidation --distribution-id %DISTRIBUTION_ID% --paths "/*"

echo Deployment complete!