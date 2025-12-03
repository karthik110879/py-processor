"""Intent Router - Extracts structured intent from user messages."""

import logging
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class IntentSchema(BaseModel):
    """Structured intent schema."""
    intent_category: str = Field(description="Category: informational_query, diagram_request, or code_change")
    intent: str = Field(description="Intent type: change_login_flow, add_feature, fix_bug, refactor, or other")
    description: str = Field(description="Human-readable description of the intent")
    risk: str = Field(description="Risk level: low, medium, or high")
    tests_required: list[str] = Field(default_factory=list, description="Required test types: unit, integration, e2e")
    human_approval: bool = Field(default=True, description="Whether human approval is required")
    constraints: list[str] = Field(default_factory=list, description="Constraints mentioned (e.g., no breaking changes)")
    target_modules: list[str] = Field(default_factory=list, description="Optional hints for target modules (e.g., auth, user)")


class IntentRouter:
    """Extracts structured intent from natural language user requests."""
    
    def __init__(self):
        """Initialize the intent router."""
        self.llm = None
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize LLM for intent extraction."""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, intent extraction will be limited")
                return
            
            model = os.getenv("LLM_MODEL", "gpt-4")
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
            max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2000"))
            
            self.llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                openai_api_key=api_key
            )
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}", exc_info=True)
            self.llm = None
    
    def extract_intent(self, user_message: str) -> Dict[str, Any]:
        """
        Extract structured intent from user message.
        
        Args:
            user_message: Natural language user request
            
        Returns:
            Structured intent dictionary
        """
        if not self.llm:
            # Fallback to simple rule-based extraction
            return self._fallback_extract_intent(user_message)
        
        try:
            return self._call_llm(user_message)
        except Exception as e:
            logger.error(f"LLM intent extraction failed: {e}", exc_info=True)
            return self._fallback_extract_intent(user_message)
    
    def _call_llm(self, user_message: str) -> Dict[str, Any]:
        """
        Call LLM to extract intent.
        
        Args:
            user_message: User's message
            
        Returns:
            Structured intent dictionary
        """
        self._user_message = user_message  # Store for fallback
        prompt = f"""You are an intent extraction agent. Analyze the user's request and extract structured intent.

User request: {user_message}

First, classify the request into one of these categories:
- informational_query: Questions asking "what", "how", "explain", "describe", "show", "tell", "list" (e.g., "what is this project about", "explain module X", "list dependencies")
- diagram_request: Requests for visualizations like "diagram", "visualize", "graph", "show dependencies", "create diagram"
- code_change: Requests to modify code like "implement", "add", "fix", "create", "modify", "refactor", "change"

Then extract:
1. Intent category (informational_query, diagram_request, or code_change)
2. Intent type (for code_change: change_login_flow, add_feature, fix_bug, refactor, or other; for others: descriptive string)
3. Description (human-readable summary)
4. Risk level (low/medium/high - only relevant for code_change, use "low" for queries/diagrams)
5. Required tests (unit, integration, e2e - only for code_change)
6. Whether human approval is needed (true if high risk or major changes - only for code_change)
7. Any constraints mentioned (e.g., "no breaking changes", "maintain backward compatibility")
8. Target modules (optional hints like "auth", "user", "payment" if mentioned)

Return a JSON object with these fields:
- intent_category: "informational_query" | "diagram_request" | "code_change"
- intent: string
- description: string
- risk: "low" | "medium" | "high"
- tests_required: array of strings (empty for informational/diagram requests)
- human_approval: boolean (false for informational/diagram requests)
- constraints: array of strings
- target_modules: array of strings

Be specific and accurate. If the intent is unclear, use "code_change" category with "other" intent and provide a detailed description."""

        try:
            response = self.llm.invoke(prompt)
            
            # Parse response
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Try to extract JSON from response
            import json
            import re
            
            # Look for JSON in the response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                intent_dict = json.loads(json_str)
            else:
                # Fallback: try to use Pydantic parser if available
                try:
                    from langchain_core.output_parsers import PydanticOutputParser
                    parser = PydanticOutputParser(pydantic_object=IntentSchema)
                    intent_dict = parser.parse(content).dict()
                except ImportError:
                    # If parser not available, use fallback extraction
                    intent_dict = self._fallback_extract_intent(self._user_message)
            
            # Validate and normalize
            intent_dict = self._normalize_intent(intent_dict)
            
            return intent_dict
        
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}", exc_info=True)
            return self._fallback_extract_intent(user_message)
    
    def _fallback_extract_intent(self, user_message: str) -> Dict[str, Any]:
        """
        Fallback rule-based intent extraction.
        
        Args:
            user_message: User's message
            
        Returns:
            Basic intent dictionary
        """
        message_lower = user_message.lower()
        
        # First, determine intent category
        informational_keywords = ['what', 'how', 'explain', 'describe', 'show', 'tell', 'list', 'what are', 'what is']
        diagram_keywords = ['diagram', 'visualize', 'graph', 'dependencies', 'show dependencies', 'create diagram', 'draw']
        code_change_keywords = ['implement', 'add', 'fix', 'create', 'modify', 'refactor', 'change', 'update', 'remove']
        
        if any(keyword in message_lower for keyword in informational_keywords):
            intent_category = "informational_query"
            intent_type = "information_request"
            risk = "low"
            tests_required = []
            human_approval = False
        elif any(keyword in message_lower for keyword in diagram_keywords):
            intent_category = "diagram_request"
            intent_type = "diagram_generation"
            risk = "low"
            tests_required = []
            human_approval = False
        else:
            # Default to code_change
            intent_category = "code_change"
            
            # Determine intent type for code changes
            if any(word in message_lower for word in ['login', 'auth', 'authentication', 'sign in']):
                intent_type = "change_login_flow"
            elif any(word in message_lower for word in ['add', 'create', 'new', 'implement']):
                intent_type = "add_feature"
            elif any(word in message_lower for word in ['fix', 'bug', 'error', 'issue']):
                intent_type = "fix_bug"
            elif any(word in message_lower for word in ['refactor', 'restructure', 'reorganize']):
                intent_type = "refactor"
            else:
                intent_type = "other"
            
            # Determine risk (simple heuristic) - only for code changes
            if len(user_message.split()) > 50 or any(word in message_lower for word in ['major', 'significant', 'large']):
                risk = "high"
            elif len(user_message.split()) > 20:
                risk = "medium"
            else:
                risk = "low"
            
            tests_required = ["unit", "integration"] if risk != "low" else ["unit"]
            human_approval = risk in ["medium", "high"]
        
        # Extract target modules
        target_modules = []
        if 'auth' in message_lower or 'login' in message_lower:
            target_modules.append('auth')
        if 'user' in message_lower:
            target_modules.append('user')
        if 'payment' in message_lower:
            target_modules.append('payment')
        
        return {
            "intent_category": intent_category,
            "intent": intent_type,
            "description": user_message[:200],  # Truncate if too long
            "risk": risk,
            "tests_required": tests_required,
            "human_approval": human_approval,
            "constraints": [],
            "target_modules": target_modules
        }
    
    def _normalize_intent(self, intent_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize intent dictionary to ensure all required fields are present.
        
        Args:
            intent_dict: Intent dictionary from LLM
            
        Returns:
            Normalized intent dictionary
        """
        # Determine intent category (default to code_change for backward compatibility)
        intent_category = intent_dict.get("intent_category", "code_change")
        valid_categories = ["informational_query", "diagram_request", "code_change"]
        if intent_category not in valid_categories:
            intent_category = "code_change"
        
        # Ensure all required fields exist
        normalized = {
            "intent_category": intent_category,
            "intent": intent_dict.get("intent", "other"),
            "description": intent_dict.get("description", ""),
            "risk": intent_dict.get("risk", "medium"),
            "tests_required": intent_dict.get("tests_required", []),
            "human_approval": intent_dict.get("human_approval", True),
            "constraints": intent_dict.get("constraints", []),
            "target_modules": intent_dict.get("target_modules", [])
        }
        
        # For informational/diagram requests, set appropriate defaults
        if intent_category in ["informational_query", "diagram_request"]:
            normalized["risk"] = "low"
            normalized["tests_required"] = []
            normalized["human_approval"] = False
        
        # Validate intent type (only for code_change category)
        if intent_category == "code_change":
            valid_intents = ["change_login_flow", "add_feature", "fix_bug", "refactor", "other"]
            if normalized["intent"] not in valid_intents:
                normalized["intent"] = "other"
        
        # Validate risk level
        valid_risks = ["low", "medium", "high"]
        if normalized["risk"] not in valid_risks:
            normalized["risk"] = "medium"
        
        # Ensure tests_required is a list
        if not isinstance(normalized["tests_required"], list):
            normalized["tests_required"] = []
        
        # Ensure constraints is a list
        if not isinstance(normalized["constraints"], list):
            normalized["constraints"] = []
        
        # Ensure target_modules is a list
        if not isinstance(normalized["target_modules"], list):
            normalized["target_modules"] = []
        
        return normalized
