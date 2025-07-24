import os
import json
import uuid
import boto3
import logging
import ast
from strands import Agent, tool
from strands_tools import http_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Config ───
SESSION_BUCKET = os.environ["SESSION_BUCKET"]
SESSION_PREFIX = os.environ.get("SESSION_PREFIX", "sessions/")
WEB_SEARCH_LAMBDA = os.environ.get("WEB_SEARCH_LAMBDA")
# WEB_SEARCH_LAMBDA = "AccordAutomateEmailStack-WebSearchFunction572C3AA7-5MbKg636mbvn"
FAQ_KNOWLEDGE_BASE_ID = "37U9ZJEDUH"
ACCORD_KNOWLEDGE_BASE_ID = "6NBB1GW4DI"
ENABLE_SESSION_MANAGEMENT = os.environ.get("ENABLE_SESSION_MANAGEMENT", "false").lower() == "true"
MODEL_ARN = os.environ.get(
    "MODEL_ARN", "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
)

# Flag to control citation deduplication
ENABLE_CITATION_DEDUPLICATION = False

s3 = boto3.client("s3")
lambda_client = boto3.client("lambda")
bedrock_runtime = boto3.client("bedrock-agent-runtime")

# ─── Utility ───
def normalize_state_variants(state):
    if not state:
        return ["ALL"]
    full = state.strip().title()
    return [full, full.upper(), full.lower()]

# ─── Tools ───
@tool(
    name="UnderwritingDocsSearch",
    description=(
        "Use this tool to extract information from underwriting documents like ACORD forms, loss runs, submission emails, and attachments "
        "that were submitted as part of a policy's submission package.\n\n"
        "** When to use: **\n"
        "- When the user asks details of a specific business or entity"
        "- When the user asks for details about policy coverage requests, business type, risk location, producer, or prior carrier\n"
        "- When asked about claims history, open claims, or loss runs\n"
        "- When asked what documents were submitted or what's missing from a submission\n"
        "- When asked about inspection reports, roof condition, valuations, or email context\n\n"
        "- You can provide any combination of: policy_number, policy_type, insured_name, or agency_number as input to this tool to lookup information."
        "- `policy_number` (optional): Unique identifier for the insurance policy, Do not remove or alter formatting.\n"
        "- `policy_type` (optional): Type of policy such as Commercial or Personal\n"
        "- `insured_name` (optional): Name of the business or individual insured\n"
        "- `agency_number` (optional): Unique ID for the agency or producer"
    )
)
def underwriting_docs_search(policy_number=None, policy_type=None, insured_name=None, agency_number=None):
    logger.info(
        f"[UnderwritingDocsSearch] Invoked with: policy_number={policy_number}, "
        f"policy_type={policy_type}, insured_name={insured_name}, agency_number={agency_number}"
    )

    # Build metadata filter using only provided inputs
    # 1) collect your individual conditions
    filter_fields = {
        "policy_number": policy_number,
        "policy_type": policy_type,
        "insured_name": insured_name,
        "agency_number": agency_number
    }

    filter_conditions = []
    for k, v in filter_fields.items():
        if not v:
            continue
        filter_conditions.append({
            # you can choose equals vs stringContains as needed:
            "stringContains": {"key": k, "value": v}
        })

    # 2) wrap only if you have 2+ filters
    if len(filter_conditions) >= 2:
        filters = {"orAll": filter_conditions}
    elif len(filter_conditions) == 1:
        # single condition goes in directly
        filters = filter_conditions[0]
    else:
        # no filters at all
        filters = {}


    logger.info(f"[UnderwritingDocsSearch] Using filters: {json.dumps(filters)}")

    try:
        resp = bedrock_runtime.retrieve_and_generate(
            input={"text": "Extract submission details relevant to underwriting."},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": ACCORD_KNOWLEDGE_BASE_ID,
                    "modelArn": MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": 100,
                            "filter": filters
                        }
                    },
                    "generationConfiguration": {
                        "inferenceConfig": {
                            "textInferenceConfig": {
                                "maxTokens": 8192,
                                "temperature": 0.0,
                                "topP": 0.5
                            }
                        }
                    }
                }
            }
        )
        
        # Log the full response structure to debug
        logger.info(f"[UnderwritingDocsSearch] Full response keys: {list(resp.keys())}")
        logger.info(f"[UnderwritingDocsSearch] Response sessionId: {resp.get('sessionId', 'None')}")
        
        # Extract citations from the response
        citations = []
        if "citations" in resp:
            logger.info(f"[UnderwritingDocsSearch] Found {len(resp['citations'])} citation groups")
            
            for citation_group in resp.get("citations", []):
                if "retrievedReferences" in citation_group:
                    for ref in citation_group.get("retrievedReferences", []):
                        if "location" in ref:
                            citation = {
                                "id": f"doc-{len(citations)+1}",  # Add unique ID for reference
                                "name": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                                "type": "document",
                                "snippet": ref.get("content", {}).get("text", "")[:800] + "...",  # Truncate long text
                                "metadata": ref.get("metadata", {})
                            }
                            citations.append(citation)
        
        logger.info(f"[UnderwritingDocsSearch] Extracted {len(citations)} citations")
        
        # CHANGE 1: Store the raw response in a global dictionary for later access
        # This allows us to access the citations even if Strands transforms the response
        if not hasattr(underwriting_docs_search, "raw_responses"):
            underwriting_docs_search.raw_responses = {}
        
        # Use a unique key based on the input parameters
        response_key = f"{policy_number}_{policy_type}_{insured_name}_{agency_number}"
        underwriting_docs_search.raw_responses[response_key] = resp
        
        # Store citations separately for easier access
        if not hasattr(underwriting_docs_search, "citations"):
            underwriting_docs_search.citations = []
        underwriting_docs_search.citations.extend(citations)
        
        # CHANGE 2: Return both the answer and citations in a format that works with Strands
        # Some frameworks expect just the answer text, others can handle a dictionary
        answer_text = resp.get("output", {}).get("text", "No relevant submission documents found.")
        
        # Return the answer text directly, as Strands might not handle dictionaries correctly
        return answer_text
    except Exception as e:
        logger.error(f"[UnderwritingDocsSearch] Error querying knowledge base: {e}")
        return "Error retrieving document information from underwriting package."


@tool(
    name="InternalGuidelinesLookup",
    description=(
        "Use this to look up wind underwriting guidelines, underwriting restrictions, deductibles, premium considerations, or risk exclusions "
        "based on which county and state the property is located.\n\n"
        "**Parameters:**\n"
        "- `question` (required)\n"
        "- `county` (optional)\n"
        "- `state` (optional, list[str])\n\n"
        "**MANDATORY RULES before using this tool:**\n"
        "1. Convert any state abbreviation (e.g., 'FL') to full name (e.g., 'Florida') before using this tool.\n"
        "2. Pass `state` as list of values: ['Florida', 'FLORIDA', 'florida'].\n"
        "3. If no state is provided, pass ['ALL'].\n"
        "4. If you know the county, the best results are obtained when both county and state are included in the question."
    )
)
def underwriter_faq(question, county=None, state=None):
    logger.info(f"[InternalGuidelinesLookup] Invoked with: question={question}, county={county}, state={state}")
    try:
        if isinstance(state, str):
            try:
                parsed = ast.literal_eval(state)
                if isinstance(parsed, list):
                    state_values = parsed
                else:
                    state_values = [state]
            except Exception:
                state_values = [state]
        elif isinstance(state, list):
            state_values = state
        else:
            state_values = ["ALL"]

        filter_expr = {
            "orAll": [
                {"equals": {"key": "state", "value": val}}
                for val in state_values
            ]
        }

        logger.info(f"Querying KB: question={question}, state={state_values}, filter={filter_expr}")

        if FAQ_KNOWLEDGE_BASE_ID:
            resp = bedrock_runtime.retrieve_and_generate(
                input={"text": question},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": FAQ_KNOWLEDGE_BASE_ID,
                        "modelArn": MODEL_ARN,
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": 100,
                                "filter": filter_expr
                            }
                        },
                        "generationConfiguration": {
                            "inferenceConfig": {
                                "textInferenceConfig": {
                                    "maxTokens": 8192,
                                    "temperature": 0,
                                    "topP": 0.54
                                }
                            }
                        }
                    }
                }
            )
            
            # Log the full response structure to debug
            logger.info(f"[InternalGuidelinesLookup] Full response keys: {list(resp.keys())}")
            
            # Extract citations from the response
            citations = []
            if "citations" in resp:
                logger.info(f"[InternalGuidelinesLookup] Found {len(resp['citations'])} citation groups")
                
                for citation_group in resp.get("citations", []):
                    if "retrievedReferences" in citation_group:
                        for ref in citation_group.get("retrievedReferences", []):
                            if "location" in ref:
                                citation = {
                                    "id": f"doc-{len(citations)+1}",  # Add unique ID for reference
                                    "name": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                                    "type": "document",
                                    "snippet": ref.get("content", {}).get("text", "")[:800] + "...",  # Truncate long text
                                    "metadata": ref.get("metadata", {})
                                }
                                citations.append(citation)
            
            logger.info(f"[InternalGuidelinesLookup] Extracted {len(citations)} citations")
            
            # CHANGE 1: Store the raw response in a global dictionary for later access
            if not hasattr(underwriter_faq, "raw_responses"):
                underwriter_faq.raw_responses = {}
            
            # Use a unique key based on the input parameters
            response_key = f"{question}_{county}_{state}"
            underwriter_faq.raw_responses[response_key] = resp
            
            # Store citations separately for easier access
            if not hasattr(underwriter_faq, "citations"):
                underwriter_faq.citations = []
            underwriter_faq.citations.extend(citations)
            
            # CHANGE 2: Return just the answer text, not a dictionary
            answer_text = resp.get("output", {}).get("text", "No result from KB")
            return answer_text
        else:
            return f"For {question} in county={county or 'ANY'}, state={state or 'ANY'}: minimum deductible is 1% of TIV."
    except Exception as e:
        logger.error("[InternalGuidelinesLookup] FAQ KB error: %s", e)
        return "Error retrieving guideline from FAQ knowledge base."

@tool(
    name="web_search",
    description="Search the web if there are questions that other tools don't answer."
)
def web_search(query: str):
    logger.info(f"[web_search] Invoked with query: {query}")
    if not WEB_SEARCH_LAMBDA:
        raise RuntimeError("Missing web search lambda env var")
    payload = json.dumps({"query": query}).encode("utf-8")
    resp = lambda_client.invoke(
        FunctionName=WEB_SEARCH_LAMBDA,
        InvocationType="RequestResponse",
        Payload=payload
    )
    result = json.loads(resp["Payload"].read())
    if result.get("statusCode") == 200:
        response_body = json.loads(result.get("body", "{}"))
        
        # Log the full response structure to debug
        logger.info(f"[web_search] Full response keys: {list(response_body.keys())}")
        
        # Extract citations from web search results
        citations = []
        # Check if results exist in the response
        if "results" in response_body:
            logger.info(f"[web_search] Found {len(response_body['results'])} search results")
            for idx, result in enumerate(response_body.get("results", [])):
                citation = {
                    "id": f"web-{idx+1}",  # Add unique ID for reference
                    "name": result.get("title", f"Web Result {idx+1}"),
                    "url": result.get("url", ""),
                    "type": "web",
                    "snippet": result.get("snippet", "")[:200] + ("..." if len(result.get("snippet", "")) > 200 else "")
                }
                citations.append(citation)
        # If no results but we have an answer, create a generic citation
        elif "answer" in response_body:
            logger.info("[web_search] No results field found, creating generic citation")
            citation = {
                "id": "web-1",
                "name": "Web Search Result",
                "url": "",
                "type": "web",
                "snippet": "Information retrieved from web search"
            }
            citations.append(citation)
        
        logger.info(f"[web_search] Extracted {len(citations)} citations")
        
        # Store the raw response in a global dictionary for later access
        if not hasattr(web_search, "raw_responses"):
            web_search.raw_responses = {}
        
        # Use a unique key based on the input parameters
        response_key = query
        web_search.raw_responses[response_key] = {
            "answer": response_body.get("answer", "No web search results found."),
            "results": response_body.get("results", []),
            "citations": citations  # Store the citations we created
        }
        
        # Store citations separately for easier access
        if not hasattr(web_search, "citations"):
            web_search.citations = []
        web_search.citations.extend(citations)
        
        # Return just the answer text, not a dictionary
        answer_text = response_body.get("answer", "No web search results found.")
        return answer_text
    raise RuntimeError(f"WebSearch lambda error: {result.get('body')}")


# ─── Persistence ───
def save_agent_state(agent: Agent, session_id: str):
    key = f"{SESSION_PREFIX}{session_id}.json"
    s3.put_object(
        Bucket=SESSION_BUCKET,
        Key=key,
        Body=json.dumps({
            "messages": agent.messages,
            "system_prompt": agent.system_prompt
        }).encode(),
        ContentType="application/json"
    )

def restore_agent_state(session_id: str):
    key = f"{SESSION_PREFIX}{session_id}.json"
    try:
        resp = s3.get_object(Bucket=SESSION_BUCKET, Key=key)
        state = json.loads(resp["Body"].read().decode())
        return Agent(system_prompt=state["system_prompt"], messages=state["messages"], tools=[underwriter_faq, underwriting_docs_search, web_search])
    except Exception:
        return None

# ─── System Prompt ───

SYSTEM_PROMPT = """
You are a helpful assistant for insurance underwriters evaluating risk and pricing for commercial and residential properties.

You have access to the following tools:

• UnderwritingDocsSearch(policy_number?, policy_type?, insured_name?, agency_number?)
  - Use this first whenever the question mentions: policy number, insured business or individual, coverage request, claim number, loss run, roof condition, inspection report, etc.
    - This tool will returns submission-package details from ACCORD forms, emails, attachments.
  - This tool is applicable when asked about:
    - Policy coverage requests, insured business type, risk location, producer/agency
    - Claims history, open losses, prior carrier or renewals
    - What documents are included or missing in the submission
    - For prior carrier, renewals, claims history, or open losses
    - Inspection reports, valuations, property condition, or broker comments
    - Roof condition, valuation reports, inspection findings, or broker comments
    - Details about an insured business or insured individual
  - This tool can be invoked with atleast one of the values like - type of policy, or name of the business or individual insured or unique ID for the agency or producer`.

• InternalGuidelinesLookup(question, county?, state?) 
  - ALWAYS use this **after** UnderwritingDocsSearch when the user needs underwriting rules: wind/hail deductibles, excluded counties, risk‐based limits for a specific insured entity or property.  
  - ALWAYS use this to look up property underwriting restrictions, wind and hail deductibles, excluded counties, or risk-based limits.
  - This tool is applicable whether the question mentions a specific business name, address, county, or just a state.
  - Use it for general questions like "What is the deductible for wind in Florida?" or "Are there any underwriting restrictions in Miami-Dade County?"
  - If you know the county, the **best way to get accurate answers is to include both the full state name and the county name in the question**.
  - Convert all state abbreviations (e.g., "NY") to full names, and ALWAYS pass a list of state variants like: ['New York', 'NEW YORK', 'new york'].
  - If no state is provided, pass ['ALL'].
  - Provide as much detail as possible.

• web_search(query)
  - Use this when the user asks about recent news, third-party sources, regulations, or market trends that internal tools may not address.
  - Use this tool if the user asks to find recent insurance related events or weather events in the county and state where the business is located.
  - Use this tool if the user asks for information related to the business' board of directors or leadership
  - Trigger this tool when the question includes words like "latest", "recent", "news", "external", "update", or "changes".
  - You may use this tool **in parallel** with internal tools when the question has both internal and external components.

Citation Instructions:
- When presenting information from documents or web searches, clearly indicate the source using citation markers [1], [2], etc.
- Number citations in the order you mention them in your response.
- For each source you reference, include a citation marker at the end of the relevant information.
- When combining information from multiple sources, clearly attribute which information came from which source.
- Format citations consistently throughout your response.

General Instructions:
- If the question refers to a specific insured entity or property, **first** invoke UnderwritingDocsSearch.
- Then feed the relevant location details (e.g. county, state) into InternalGuidelinesLookup.
- Use web_search **only** for external news/regulations.
- Always choose the most appropriate tool(s) based on the nature of the question.
- Normalize state inputs using full names and case variants.
- NEVER fabricate answers if you don't have sufficient internal knowledge.
- If the question is **complex or multi-part**, break it down into **simpler sub-questions**, answer each using the most relevant tool, and then **combine the answers** into a cohesive response.
- You may invoke tools in **sequence** (when later answers depend on earlier results) or in **parallel** (when questions are unrelated or independently resolvable).
- Always include citations from the sources used to answer questions.
- When presenting information from documents or web searches, clearly indicate the source.
"""


# ─── Agent Setup ───
def get_agent(session_id: str):
    if ENABLE_SESSION_MANAGEMENT:
        agent = restore_agent_state(session_id)
        if agent is not None:
            return agent
    return Agent(system_prompt=SYSTEM_PROMPT, tools=[underwriter_faq, underwriting_docs_search, web_search])


# ─── Lambda Handler ───
def lambda_handler(event, context):
    payload = event.get("body") or event
    if isinstance(payload, str):
        payload = json.loads(payload)

    session_id = payload.get("session_id") or str(uuid.uuid4())
    question = payload["question"]

    logger.info(f"[Lambda] Received question: {question} for session: {session_id}")
    
    # Reset citation collections before invoking the agent
    if hasattr(underwriting_docs_search, "citations"):
        underwriting_docs_search.citations = []
    if hasattr(underwriter_faq, "citations"):
        underwriter_faq.citations = []
    if hasattr(web_search, "citations"):
        web_search.citations = []
    
    agent = get_agent(session_id)
    result = agent(question)

    # Process the result to include citations
    answer = str(result)
    all_citations = []
    
    # CHANGE 1: Extract citations from stored raw responses in tool functions
    logger.info("[Lambda] Extracting citations from stored raw responses")
    
    # First try to get citations from the direct citation attributes we added
    if hasattr(underwriting_docs_search, "citations"):
        all_citations.extend(underwriting_docs_search.citations)
        logger.info(f"[Lambda] Added {len(underwriting_docs_search.citations)} citations from UnderwritingDocsSearch")
    
    if hasattr(underwriter_faq, "citations"):
        all_citations.extend(underwriter_faq.citations)
        logger.info(f"[Lambda] Added {len(underwriter_faq.citations)} citations from InternalGuidelinesLookup")
    
    if hasattr(web_search, "citations"):
        all_citations.extend(web_search.citations)
        logger.info(f"[Lambda] Added {len(web_search.citations)} citations from web_search")
    
    # If no citations found in direct attributes, fall back to extracting from raw responses
    if not all_citations:
        logger.info("[Lambda] No citations found in direct attributes, falling back to raw responses")
        
        # Extract from UnderwritingDocsSearch raw responses
        if hasattr(underwriting_docs_search, "raw_responses"):
            for resp_key, resp in underwriting_docs_search.raw_responses.items():
                logger.info(f"[Lambda] Processing UnderwritingDocsSearch response for key: {resp_key}")
                if "citations" in resp:
                    for citation_group in resp.get("citations", []):
                        if "retrievedReferences" in citation_group:
                            for ref in citation_group.get("retrievedReferences", []):
                                if "location" in ref:
                                    citation = {
                                        "id": f"doc-{len(all_citations)+1}",
                                        "name": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                                        "type": "document",
                                        "snippet": ref.get("content", {}).get("text", "")[:800] + "...",
                                        "metadata": ref.get("metadata", {})
                                    }
                                    all_citations.append(citation)
                                    logger.info("[Lambda] Added citation from UnderwritingDocsSearch")
        
        # Extract from InternalGuidelinesLookup raw responses
        if hasattr(underwriter_faq, "raw_responses"):
            for resp_key, resp in underwriter_faq.raw_responses.items():
                logger.info(f"[Lambda] Processing InternalGuidelinesLookup response for key: {resp_key}")
                if "citations" in resp:
                    for citation_group in resp.get("citations", []):
                        if "retrievedReferences" in citation_group:
                            for ref in citation_group.get("retrievedReferences", []):
                                if "location" in ref:
                                    citation = {
                                        "id": f"doc-{len(all_citations)+1}",
                                        "name": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                                        "type": "document",
                                        "snippet": ref.get("content", {}).get("text", "")[:800] + "...",
                                        "metadata": ref.get("metadata", {})
                                    }
                                    all_citations.append(citation)
                                    logger.info("[Lambda] Added citation from InternalGuidelinesLookup")
        
        # Extract from web_search raw responses
        if hasattr(web_search, "raw_responses"):
            for resp_key, resp in web_search.raw_responses.items():
                logger.info(f"[Lambda] Processing web_search response for key: {resp_key}")
                if "citations" in resp:
                    # Use the citations we created in the web_search function
                    web_citations = resp.get("citations", [])
                    all_citations.extend(web_citations)
                    logger.info(f"[Lambda] Added {len(web_citations)} citations from web_search")
                elif "results" in resp:
                    # Fallback to extracting from results if citations aren't available
                    for idx, result in enumerate(resp.get("results", [])):
                        citation = {
                            "id": f"web-{len(all_citations)+1}",
                            "name": result.get("title", f"Web Result {idx+1}"),
                            "url": result.get("url", ""),
                            "type": "web",
                            "snippet": result.get("snippet", "")[:200] + ("..." if len(result.get("snippet", "")) > 200 else "")
                        }
                        all_citations.append(citation)
                        logger.info("[Lambda] Added citation from web_search results")
                else:
                    # Create a generic citation if no results or citations
                    logger.info("[Lambda] Creating generic web search citation")
                    citation = {
                        "id": "web-1",
                        "name": "Web Search Result",
                        "url": "",
                        "type": "web",
                        "snippet": f"Information retrieved from web search for: {resp_key}"
                    }
                    all_citations.append(citation)
                    logger.info("[Lambda] Added generic web search citation")
    
    # Apply deduplication only if enabled
    if ENABLE_CITATION_DEDUPLICATION:
        logger.info("[Lambda] Deduplication enabled, deduplicating citations by name")
        # Deduplicate citations by name
        unique_citations = {}
        for citation in all_citations:
            if "name" in citation:
                if citation["name"] not in unique_citations:
                    unique_citations[citation["name"]] = citation
        
        # Convert back to list and ensure all citations have IDs
        citations = []
        doc_count = 1
        web_count = 1
        
        for name, citation in unique_citations.items():
            if "id" not in citation:
                if citation.get("type") == "document":
                    citation["id"] = f"doc-{doc_count}"
                    doc_count += 1
                elif citation.get("type") == "web":
                    citation["id"] = f"web-{web_count}"
                    web_count += 1
                else:
                    citation["id"] = f"src-{len(citations)+1}"
            citations.append(citation)
        
        logger.info(f"[Lambda] After deduplication: {len(citations)} unique citations")
    else:
        logger.info("[Lambda] Deduplication disabled, using all citations")
        # Skip deduplication, just ensure all citations have IDs
        citations = all_citations
        doc_count = 1
        web_count = 1
        
        for citation in citations:
            if "id" not in citation:
                if citation.get("type") == "document":
                    citation["id"] = f"doc-{doc_count}"
                    doc_count += 1
                elif citation.get("type") == "web":
                    citation["id"] = f"web-{web_count}"
                    web_count += 1
                else:
                    citation["id"] = f"src-{len(citations)+1}"
    
    # CHANGE 2: Clear stored responses after processing to avoid memory leaks
    if hasattr(underwriting_docs_search, "raw_responses"):
        underwriting_docs_search.raw_responses = {}
    if hasattr(underwriter_faq, "raw_responses"):
        underwriter_faq.raw_responses = {}
    if hasattr(web_search, "raw_responses"):
        web_search.raw_responses = {}
    
    # Also clear citation collections
    if hasattr(underwriting_docs_search, "citations"):
        underwriting_docs_search.citations = []
    if hasattr(underwriter_faq, "citations"):
        underwriter_faq.citations = []
    if hasattr(web_search, "citations"):
        web_search.citations = []
    
    logger.info(f"[Lambda] Total citations collected: {len(citations)}")
    if citations:
        logger.info(f"[Lambda] First citation: {json.dumps(citations[0])}")

    logger.info(f"[Lambda] Final answer: {answer}")
    if ENABLE_SESSION_MANAGEMENT:
        save_agent_state(agent, session_id)

    return {
        "statusCode": 200,
        "body": {
            "session_id": session_id,
            "question": question,
            "answer": answer,
            "citations": citations
        }
    }