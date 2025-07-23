from strands import Agent
from strands_tools import retrieve
from strands.models import BedrockModel
from typing import Dict, Any
import json
import os

# Define encyclopedia system prompt
ENCYCLOPEDIA_SYSTEM_PROMPT = """You are an encyclopedia assistant with access to a knowledge base.
Use the knowledge base to answer questions accurately about history, science, and biology.
Provide detailed, educational responses based on the information in the knowledge base.
If the knowledge base doesn't have the information, clearly state that you don't know.
"""

def handler(event: Dict[str, Any], _context) -> Dict[str, Any]:
    try:
        # Parse the request body from API Gateway
        try:
            if 'body' in event:
                body = json.loads(event['body'])
                prompt = body.get('prompt')
            else:
                # Direct Lambda invocation
                prompt = event.get('prompt')
        except Exception as e:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps({'error': f'Error parsing request: {str(e)}'})
            }
        
        if not prompt:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing prompt parameter'})
            }
        
        # Get knowledge base ID from environment
        knowledge_base_id = os.environ.get('KNOWLEDGE_BASE_ID')
        if not knowledge_base_id:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Knowledge base ID not configured'})
            }
        
        # Set knowledge base ID as environment variable for retrieve tool
        os.environ["KNOWLEDGE_BASE_ID"] = knowledge_base_id
        
        # Get guardrail ID from environment (optional)
        guardrail_id = os.environ.get('GUARDRAIL_ID')
        
        # Create model with guardrail if available
        if guardrail_id:
            model = BedrockModel(
                model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                guardrail_id=guardrail_id,
                guardrail_version="DRAFT",  # or "LATEST" for deployed version
                guardrail_trace="enabled"  # Enable trace info for debugging
            )
        else:
            model = BedrockModel(
                model_id="anthropic.claude-3-sonnet-20240229-v1:0"
            )
        
        # Create encyclopedia agent with retrieve tool and guardrailed model
        encyclopedia_agent = Agent(
            model=model,
            system_prompt=ENCYCLOPEDIA_SYSTEM_PROMPT,
            tools=[retrieve],
        )

        response = encyclopedia_agent(prompt)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps({'response': str(response)})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps({'error': str(e)})
        }