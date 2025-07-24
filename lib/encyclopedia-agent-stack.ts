import { Duration, Stack, StackProps, CfnOutput } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as path from "path";

export interface EncyclopediaAgentStackProps extends StackProps {
  knowledgeBaseId: string;
  guardrailId?: string;  // Optional guardrail ID
}

export class EncyclopediaAgentStack extends Stack {
  public readonly apiUrl: string;

  constructor(scope: Construct, id: string, props: EncyclopediaAgentStackProps) {
    super(scope, id, props);

    const packagingDirectory = path.join(__dirname, "../packaging");
    const zipDependencies = path.join(packagingDirectory, "dependencies.zip");
    const zipApp = path.join(packagingDirectory, "app.zip");
    
    // Create a lambda layer with dependencies
    const dependenciesLayer = new lambda.LayerVersion(this, "DependenciesLayer", {
      code: lambda.Code.fromAsset(zipDependencies),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      description: "Dependencies needed for agent-based lambda",
    });

    // Define the Lambda function
    const encyclopediaFunction = new lambda.Function(this, "EncyclopediaLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      functionName: "EncyclopediaFunction",
      description: "A function that queries the encyclopedia knowledge base",
      handler: "encyclopedia_handler.handler",
      code: lambda.Code.fromAsset(zipApp),
      timeout: Duration.seconds(30),
      memorySize: 256,
      layers: [dependenciesLayer],
      architecture: lambda.Architecture.ARM_64,
      environment: {
        KNOWLEDGE_BASE_ID: props.knowledgeBaseId,
        ...(props.guardrailId && { GUARDRAIL_ID: props.guardrailId }),
      },
    });

    // Add permissions for Bedrock Knowledge Base, model invocation, and guardrails
    encyclopediaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate",
          "bedrock:ApplyGuardrail",
        ],
        resources: ["*"],
      }),
    );

    // Create API Gateway with CORS enabled
    const encyclopediaApi = new apigateway.RestApi(this, "EncyclopediaApi", {
      restApiName: "Encyclopedia Chat API",
      description: "API for querying the encyclopedia knowledge base",
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'X-Amz-Date', 'Authorization', 'X-Api-Key', 'X-Amz-Security-Token'],
        maxAge: Duration.seconds(300),
      },
    });

    // Create Lambda integration
    const lambdaIntegration = new apigateway.LambdaIntegration(encyclopediaFunction);

    // Add /kb resource with POST method
    const kbResource = encyclopediaApi.root.addResource("kb");
    kbResource.addMethod("POST", lambdaIntegration);

    // Export API URL
    this.apiUrl = encyclopediaApi.url;
    
    new CfnOutput(this, "EncyclopediaApiUrl", {
      value: this.apiUrl,
      description: "Encyclopedia API Gateway URL",
      exportName: "EncyclopediaApiUrl",
    });
  }
}