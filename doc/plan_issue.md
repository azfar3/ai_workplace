# Issue Analysis

The root cause of the issue is a complete **lack of conversation memory (context retention)** between turns, specifically within the `hybrid_handler.py` and tool execution flows.

Here is the step-by-step breakdown of the failure:
1. **Isolated Processing**: When the user asked *"how many policies are uploaded?"*, the system triggered the deterministic `policy_count` intent and successfully returned the count using `get_published_policies`.
2. **Missing Context in Tool Invocation**: When the user followed up with *"tell me the included topics in the published policy"*, the `hybrid_handler.py` intercepted it under the `search_knowledge` intent. It immediately ran the `search_knowledge` tool with **only** the exact user query (`query=user_query`), without any reference to the previous turn. Because the query was generic ("published policy") and lacked specific keywords, the RAG indexer failed to retrieve the correct policy chunks.
3. **Missing Context in LLM Synthesis**: In `hybrid_handler.py`, the LLM is prompted with a hardcoded template (`"Employee asked: '{user_query}'\nHere is the authoritative data: {raw_data}"`). It does not receive any conversation history. Because `raw_data` was irrelevant or empty, the LLM politely declined, hallucinating the phrase *"the information you provided does not include..."* as it treated the system prompt as the "information provided".
4. **Truncated Data**: In `ai/tools.py`, the `get_published_policies` tool artificially limits the policy body to 300 characters (`raw_body[:300]`). Even if the LLM tried to use this list to extract topics, 300 characters is too short to contain the actual policy topics.

# Improvement Plan

To resolve this issue and make the bot conversational, we need to implement the following changes:

### 1. Implement Conversation Memory
We need to fetch the last 3-5 turns of conversation from the `WhatsApp Message Log` or `AI Action Log` for the active conversation. This history must be appended to the `messages` array in both `ai_workplace/services/hr_agent.py` (the ReAct agent) and `ai_workplace/ai/hybrid_handler.py` (the hybrid synthesizer) before calling the LLM.

### 2. Context-Aware Query Reformulation
Before executing the `search_knowledge` tool, the user's raw query needs to be contextualized. We can introduce a lightweight LLM step (or use the ReAct planner) to reformulate the query based on the conversation history. For example, it would rewrite *"tell me the included topics in the published policy"* to a query containing the actual policy name mentioned previously.

### 3. Update the Hybrid Handler Prompt
Modify `hybrid_handler.py` so that it doesn't isolate the LLM from the user. Instead of a single hardcoded string prompt, it should pass the actual `messages` list (including system instructions, conversation history, and the newly injected `raw_data` as a tool or system observation). This will stop the LLM from talking about "the information you provided".

### 4. Fix Policy Truncation
In `ai_workplace/ai/tools.py` (`get_published_policies`), increase the truncation limit from `raw_body[:300]` to a more reasonable size for LLM reasoning (e.g., `raw_body[:3000]`), or ensure that policies are exclusively read via the `search_knowledge` tool rather than the summary list.
