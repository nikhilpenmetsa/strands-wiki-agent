from strands import Agent
from strands_tools import http_request
from typing import Dict, Any
import json

# Define a weather-focused system prompt
WEATHER_SYSTEM_PROMPT = """You are a weather assistant with HTTP capabilities. You can:

1. Make HTTP requests to the National Weather Service API
2. Process and display weather forecast data
3. Provide weather information for locations in the United States

When retrieving weather information:
1. First get the coordinates or grid information using https://api.weather.gov/points/{latitude},{longitude} or https://api.weather.gov/points/{zipcode}
2. Then use the returned forecast URL to get the actual forecast

When displaying responses:
- Format weather data in a human-readable way
- Highlight important information like temperature, precipitation, and alerts
- Handle errors appropriately
- Convert technical terms to user-friendly language

Always explain the weather conditions clearly and provide context for the forecast.
"""

def handler(event: Dict[str, Any], _context) -> Dict[str, Any]:
    try:
        # Parse the request body from API Gateway
        if 'body' in event:
            body = json.loads(event['body'])
            prompt = body.get('prompt')
        else:
            # Direct Lambda invocation
            prompt = event.get('prompt')
        
        if not prompt:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing prompt parameter'})
            }
        
        weather_agent = Agent(
            system_prompt=WEATHER_SYSTEM_PROMPT,
            tools=[http_request],
        )

        response = weather_agent(prompt)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'response': str(response)})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }