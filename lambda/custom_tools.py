import os
import boto3
import json
import logging
from typing import Dict, Any, List

# Correct imports for tool definition
from strands import tool

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

@tool
def custom_retrieve(text: str, numberOfResults: int = 10, knowledgeBaseId: str = None, region: str = "us-west-2"):
    """
    Custom retrieve tool that logs raw results and includes citations.
    
    Args:
        text: The query to retrieve relevant knowledge.
        numberOfResults: The maximum number of results to return. Default is 10.
        knowledgeBaseId: The ID of the knowledge base to retrieve from.
        region: The AWS region name. Default is 'us-west-2'.
    
    Returns:
        str: Retrieved results with citations.
    """
    try:
        # Get default knowledge base ID if not provided
        default_knowledge_base_id = os.getenv("KNOWLEDGE_BASE_ID")
        kb_id = knowledgeBaseId if knowledgeBaseId else default_knowledge_base_id
        model_id = os.getenv("MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
        model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
        
        logger.info(f"[custom_retrieve] Using knowledge base ID: {kb_id}")
        logger.info(f"[custom_retrieve] Using model ARN: {model_arn}")
        
        # Initialize Bedrock client
        bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=region)

        # Use retrieve_and_generate to get citations
        response = bedrock_runtime.retrieve_and_generate(
            input={"text": text},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": model_arn,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": numberOfResults
                        }
                    },
                    "generationConfiguration": {
                        "inferenceConfig": {
                            "textInferenceConfig": {
                                "maxTokens": 4096,
                                "temperature": 0.0,
                                "topP": 0.5
                            }
                        }
                    }
                }
            }
        )
        
        # Log the full response structure
        logger.info(f"[custom_retrieve] Full response keys: {list(response.keys())}")
        
        # Log the raw response
        print(f"Raw retrieve_and_generate response: {json.dumps(response, default=str)}")
        
        # Extract citations from the response
        citations = []
        if "citations" in response:
            logger.info(f"[custom_retrieve] Found {len(response['citations'])} citation groups")
            
            for citation_group in response.get("citations", []):
                if "retrievedReferences" in citation_group:
                    for ref in citation_group.get("retrievedReferences", []):
                        citation = {
                            "id": f"doc-{len(citations)+1}",
                            "location": ref.get("location", {}),
                            "content": ref.get("content", {}).get("text", "")[:500] + "...",
                            "metadata": ref.get("metadata", {})
                        }
                        citations.append(citation)
        
        logger.info(f"[custom_retrieve] Extracted {len(citations)} citations")
        
        # Get the answer text
        answer_text = response.get("output", {}).get("text", "No relevant information found.")
        
        # Format the answer with citations
        formatted_result = format_answer_with_citations(answer_text, citations)
        
        return formatted_result

    except Exception as e:
        logger.error(f"[custom_retrieve] Error: {str(e)}")
        return f"Error during retrieval: {str(e)}"

def format_answer_with_citations(answer_text: str, citations: List[Dict[str, Any]]) -> str:
    """
    Format the answer with citations for display.
    """
    if not citations:
        return answer_text
    
    # Add citation section
    citation_text = "\n\nCitations:\n"
    for i, citation in enumerate(citations):
        doc_id = citation.get("id", f"doc-{i+1}")
        location_info = citation.get("location", {})
        
        # Try to get a meaningful document identifier
        doc_name = "Unknown"
        if "s3Location" in location_info:
            doc_name = location_info["s3Location"].get("uri", "Unknown")
        elif "customDocumentLocation" in location_info:
            doc_name = location_info["customDocumentLocation"].get("id", "Unknown")
            
        citation_text += f"[{i+1}] Document: {doc_name}\n"
        
        # Add snippet if available
        if "content" in citation:
            citation_text += f"    Snippet: {citation['content']}\n"
    
    return answer_text + citation_text