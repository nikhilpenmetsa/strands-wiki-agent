import { Duration, Stack, StackProps, SymlinkFollowMode, CfnOutput } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as path from "path";

export class AgentLambdaStack extends Stack {
  public readonly apiUrl: string;
  public readonly dependenciesLayer: lambda.LayerVersion;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const packagingDirectory = path.join(__dirname, "../packaging");

    const zipDependencies = path.join(packagingDirectory, "dependencies.zip");
    const zipApp = path.join(packagingDirectory, "app.zip");

    // Create a lambda layer with dependencies to keep the code readable in the Lambda console
    this.dependenciesLayer = new lambda.LayerVersion(this, "DependenciesLayer", {
      code: lambda.Code.fromAsset(zipDependencies),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      description: "Dependencies needed for agent-based lambda",
    });

    // Define the Lambda function
    const weatherFunction = new lambda.Function(this, "AgentLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      functionName: "WeatherAgentFunction",
      description: "A function that invokes a weather forecasting agent",
      handler: "agent_handler.handler",
      code: lambda.Code.fromAsset(zipApp),

      timeout: Duration.seconds(30),
      memorySize: 128,
      layers: [this.dependenciesLayer],
      architecture: lambda.Architecture.ARM_64,
    });

    // Add permissions for the Lambda function to invoke Bedrock APIs
    weatherFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        resources: ["*"],
      }),
    );

    // Create API Gateway
    const agentApi = new apigateway.RestApi(this, "AgentApi", {
      restApiName: "Agent Chat API",
      description: "API for invoking the agent Lambda function",
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ["Content-Type", "Authorization"],
        allowCredentials: true,
      },
    });

    // Create Lambda integration with CORS handling
    const lambdaIntegration = new apigateway.LambdaIntegration(weatherFunction, {
      proxy: true,
      integrationResponses: [
        {
          statusCode: '200',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': '\'*\'',
            'method.response.header.Access-Control-Allow-Headers': '\'Content-Type,Authorization\'',
            'method.response.header.Access-Control-Allow-Methods': '\'OPTIONS,POST\'',
          },
        },
      ],
    });

    // Add /chat resource with POST method
    const chatResource = agentApi.root.addResource("chat");
    chatResource.addMethod("POST", lambdaIntegration, {
      methodResponses: [
        {
          statusCode: '200',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
            'method.response.header.Access-Control-Allow-Headers': true,
            'method.response.header.Access-Control-Allow-Methods': true,
          },
        },
      ],
    });

    // Export API URL
    this.apiUrl = agentApi.url;
    
    new CfnOutput(this, "ApiUrl", {
      value: this.apiUrl,
      description: "API Gateway URL",
      exportName: "AgentApiUrl",
    });
  }
}
