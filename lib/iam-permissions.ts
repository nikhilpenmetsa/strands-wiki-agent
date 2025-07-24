import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export function addBedrockPermissions(scope: Construct, role: iam.Role): void {
  // Add permissions for both Retrieve and RetrieveAndGenerate operations
  role.addToPolicy(new iam.PolicyStatement({
    actions: [
      'bedrock:Retrieve',
      'bedrock:RetrieveAndGenerate',
      'bedrock:InvokeModel'
    ],
    resources: ['*'],
  }));
}