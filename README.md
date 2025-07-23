# Encyclopedia Knowledge Base Agent

This project deploys an AI agent that uses Amazon Bedrock to answer questions using a knowledge base.

## Features

- **Knowledge Base Integration**: Uses Amazon Bedrock Knowledge Base to retrieve information
- **Guardrail Protection**: Implements Amazon Bedrock Guardrails for safe responses
- **Web Interface**: Simple chat interface for interacting with the agent
- **CDK Deployment**: Infrastructure as code using AWS CDK

## Architecture

- **Lambda Function**: Processes requests and interacts with Bedrock
- **API Gateway**: HTTP endpoint for the Lambda function
- **CloudFront**: Hosts the web interface
- **Bedrock**: Provides the AI model and knowledge base capabilities

## Deployment

### Prerequisites

- AWS CLI configured
- Node.js and npm installed
- Python 3.10+ installed
- AWS CDK installed (`npm install -g aws-cdk`)

### Steps

1. Install dependencies:
   ```bash
   npm install
   ```

2. Package the Lambda code:
   ```bash
   python bin/package_for_lambda.py
   ```

3. Deploy the stacks:
   ```bash
   npx cdk deploy --all
   ```

4. Access the web interface at the CloudFront URL provided in the output.

## Configuration

- **Knowledge Base ID**: Set in `bin/cdk-app.ts`
- **Guardrail ID**: Set in `bin/cdk-app.ts`
- **Model**: Claude 3 Sonnet (configurable in `lambda/encyclopedia_handler.py`)

## Usage

Simply ask questions in the chat interface, and the agent will search the knowledge base for answers.