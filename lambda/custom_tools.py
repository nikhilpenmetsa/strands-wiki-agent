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
        
        # Get sessionId if provided
        session_id = os.getenv("SESSION_ID")
        
        logger.info(f"[custom_retrieve] Using knowledge base ID: {kb_id}")
        logger.info(f"[custom_retrieve] Using model ARN: {model_arn}")
        
        # Initialize Bedrock client
        bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=region)

        # Prepare retrieve_and_generate parameters
        retrieve_params = {
            "input": {"text": text},
            "retrieveAndGenerateConfiguration": {
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
        }
        
        # Add sessionId if provided
        if session_id:
            retrieve_params["sessionId"] = session_id
            logger.info(f"[custom_retrieve] Using sessionId: {session_id}")

        # Use retrieve_and_generate to get citations
        response = bedrock_runtime.retrieve_and_generate(**retrieve_params)
        
        # Log the full response structure
        logger.info(f"[custom_retrieve] Full response keys: {list(response.keys())}")
        
        # Log the raw response
        print(f"Raw retrieve_and_generate response: {json.dumps(response, default=str)}")
        
        # Extract citations from the response
        citations = []
        citation_groups_by_span = {}
        
        if "citations" in response:
            logger.info(f"[custom_retrieve] Found {len(response['citations'])} citation groups")
            
            # First pass: organize citation groups by span to detect duplicates
            for i, citation_group in enumerate(response.get("citations", [])):
                # Extract span information if available
                span = None
                if "generatedResponsePart" in citation_group and "textResponsePart" in citation_group["generatedResponsePart"]:
                    span_data = citation_group["generatedResponsePart"]["textResponsePart"].get("span")
                    if span_data:
                        # Create a span key for deduplication
                        span_key = f"{span_data.get('start')}:{span_data.get('end')}"
                        if span_key not in citation_groups_by_span:
                            citation_groups_by_span[span_key] = []
                        citation_groups_by_span[span_key].append((i, citation_group))
                        span = span_data
                
                if "retrievedReferences" in citation_group:
                    for ref in citation_group.get("retrievedReferences", []):
                        citation = {
                            "id": f"doc-{len(citations)+1}",
                            "source": ref.get("location", {}).get("s3Location", {}).get("uri", "Unknown"),
                            "content": ref.get("content", {}).get("text", "")[:500] + "...",
                            "metadata": ref.get("metadata", {}),
                            "span": span,  # Include span information
                            "group_index": i  # Track which group this came from
                        }
                        citations.append(citation)
        
        logger.info(f"[custom_retrieve] Extracted {len(citations)} citations")
        
        # Advanced deduplication based on multiple factors
        deduplicated_citations = []
        seen_keys = set()
        
        # Sort citations by group_index to maintain order
        citations.sort(key=lambda c: c.get("group_index", 0))
        
        for citation in citations:
            chunk_id = citation.get("metadata", {}).get("x-amz-bedrock-kb-chunk-id")
            source = citation.get("source", "")
            span_data = citation.get("span", {})
            span_key = "none"
            if span_data:
                span_key = f"{span_data.get('start')}:{span_data.get('end')}"
            
            # Create a composite key for deduplication
            dedup_key = f"{chunk_id}:{source}:{span_key}"
            
            # Skip if we've seen this exact combination before
            if dedup_key in seen_keys:
                continue
            
            seen_keys.add(dedup_key)
            
            # Remove the temporary group_index field before adding to final results
            if "group_index" in citation:
                del citation["group_index"]
                
            deduplicated_citations.append(citation)
        
        logger.info(f"[custom_retrieve] Deduplicated from {len(citations)} to {len(deduplicated_citations)} citations")
        
        logger.info(f"[custom_retrieve] Deduplicated from {len(citations)} to {len(deduplicated_citations)} citations")
        
        # Store deduplicated citations and sessionId for later retrieval
        custom_retrieve.last_citations = deduplicated_citations
        custom_retrieve.last_session_id = response.get("sessionId")
        
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


# Initialize storage for citations and sessionId after function definition
custom_retrieve.last_citations = []
custom_retrieve.last_session_id = None