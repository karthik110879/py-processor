# Human-in-the-Loop (HIL) Agent Implementation Plan

## Overview

This plan outlines the implementation of a WebSocket-based chat interface that enables real-time communication with an autonomous code change agent. The agent will analyze repositories, plan code changes, execute edits, run tests, and create PRs while streaming all processing steps, logs, and code changes live to the user through a WebSocket connection.

## Goals

1. **WebSocket Integration**: Add WebSocket support to the Flask application for real-time bidirectional communication
2. **Chat Interface**: Implement a chat endpoint where users can interact with the agent
3. **Live Streaming**: Stream all agent processing steps, logs, code analysis, and changes in real-time
4. **Backward Compatibility**: Ensure all existing REST endpoints continue to function without modification
5. **Agent Workflow**: Implement the complete human-in-the-loop agent workflow as specified in `human-in-loop-agent-flow.txt`

## Architecture Overview

```
Frontend (WebSocket Client)
    ↓
WebSocket Connection (/ws/chat)
    ↓
Chat Handler (routes/chat_routes.py)
    ↓
Agent Orchestrator (agents/orchestrator.py)
    ↓
┌─────────────────────────────────────────┐
│  Agent Workflow Components:            │
│  - Intent Router                       │
│  - PKG Query Engine                    │
│  - Impact Analyzer                     │
│  - Planner (LLM)                       │
│  - Code Edit Executor                  │
│  - Test Runner                         │
│  - Verifier                            │
│  - PR Creator                          │
└─────────────────────────────────────────┘
    ↓
WebSocket Stream (Real-time updates)
```

## Implementation Plan

### Phase 1: WebSocket Infrastructure

#### 1.1 Dependencies
- Add `flask-socketio>=5.3.0` to `requirements.txt`
- Add `python-socketio>=5.10.0` for async support
- Add `eventlet>=0.33.0` or `gevent>=23.0.0` for WebSocket server

#### 1.2 WebSocket Setup
**File: `app.py`**
- Import and initialize Flask-SocketIO
- Configure CORS for WebSocket connections
- Add WebSocket event handlers registration
- Maintain existing Flask app structure

**Changes:**
```python
from flask_socketio import SocketIO, emit
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
```

#### 1.3 WebSocket Route Handler
**New File: `routes/chat_routes.py`**
- Create Flask blueprint for chat endpoints
- Implement WebSocket connection handler
- Handle client connection/disconnection
- Register with SocketIO

**Key Functions:**
- `handle_connect()`: Client connection handler
- `handle_disconnect()`: Client disconnection handler
- `handle_message()`: Process incoming chat messages

### Phase 2: Agent Orchestrator

#### 2.1 Agent Orchestrator Service
**New File: `services/agent_orchestrator.py`**

**Class: `AgentOrchestrator`**
- Manages the complete agent workflow
- Coordinates between different agent components
- Handles WebSocket message streaming
- Manages session state per WebSocket connection

**Key Methods:**
- `process_user_request(session_id, user_message, socketio)`: Main entry point
- `stream_message(socketio, session_id, event_type, data)`: Stream updates to client
- `execute_workflow(intent, socketio, session_id)`: Execute full agent workflow

#### 2.2 Message Streaming Format
**Standardized message format for WebSocket events:**

```json
{
  "type": "log|status|code_change|test_result|error|approval_request|summary",
  "timestamp": "2024-01-01T12:00:00Z",
  "stage": "intent_extraction|pkg_query|impact_analysis|planning|editing|testing|verification|pr_creation",
  "data": {
    // Stage-specific data
  },
  "session_id": "uuid"
}
```

**Event Types:**
- `log`: General processing logs
- `status`: Workflow stage updates
- `code_change`: Code modifications (diffs, file changes)
- `test_result`: Test execution results
- `error`: Error messages
- `approval_request`: Human approval required
- `summary`: Final summary and results

### Phase 3: Agent Workflow Components

#### 3.1 Intent Router
**New File: `agents/intent_router.py`**

**Class: `IntentRouter`**
- Parses natural language user requests
- Extracts structured intent JSON
- Determines risk level and approval requirements
- Uses LLM (LangChain) for intent extraction

**Output Format:**
```json
{
  "intent": "change_login_flow",
  "description": "require 2FA + email verification on login",
  "risk": "medium",
  "tests_required": ["unit", "integration"],
  "human_approval": true,
  "constraints": []
}
```

**Integration:**
- Stream intent extraction progress via WebSocket
- Request clarification if intent is ambiguous

#### 3.2 PKG Query Engine
**New File: `services/pkg_query_engine.py`**

**Class: `PKGQueryEngine`**
- Queries Project Knowledge Graph (PKG) for impacted modules
- Finds related symbols, endpoints, and dependencies
- Uses existing `services/pkg_generator.py` and PKG schema

**Key Methods:**
- `get_modules_by_tag(tag: str) -> List[Dict]`: Find modules by tags
- `get_impacted_modules(module_ids: List[str], depth: int) -> Dict`: Transitive closure
- `get_endpoints_by_path(path_pattern: str) -> List[Dict]`: Find endpoints
- `get_dependencies(module_id: str) -> Dict`: Get callers and callees

**Streaming:**
- Stream discovered modules, symbols, and endpoints
- Show impact analysis progress

#### 3.3 Impact Analyzer
**New File: `agents/impact_analyzer.py`**

**Class: `ImpactAnalyzer`**
- Analyzes impact of proposed changes
- Calculates risk scores based on fan-in/fan-out
- Identifies affected tests and dependencies
- Determines if human approval is required

**Key Methods:**
- `analyze_impact(intent: Dict, pkg_data: Dict) -> Dict`: Main analysis
- `calculate_risk_score(impacted_files: List) -> str`: Risk assessment
- `find_affected_tests(modules: List) -> List`: Test discovery

**Streaming:**
- Stream impact analysis results
- Show risk assessment and affected files

#### 3.4 Planner (LLM)
**New File: `agents/planner.py`**

**Class: `Planner`**
- Generates step-by-step code change plan
- Uses LangChain with OpenAI/LLM
- Produces structured task list with files, changes, and tests

**Key Methods:**
- `generate_plan(intent: Dict, impacted_modules: Dict, constraints: List) -> Dict`: Generate plan
- Uses prompt template from `human-in-loop-agent-flow.txt`

**Output Format:**
```json
{
  "plan": [
    {
      "task": "Add 2FA fields to User entity",
      "files": ["src/user/user.entity.ts"],
      "changes": ["Add is2FAEnabled: boolean field"],
      "tests": ["tests/user.entity.spec.ts"],
      "notes": "Migration required"
    }
  ]
}
```

**Streaming:**
- Stream plan generation progress
- Send completed plan for review

#### 3.5 Code Edit Executor
**New File: `agents/code_editor.py`**

**Class: `CodeEditExecutor`**
- Applies code edits using AST-aware tools
- Creates git branch for changes
- Generates diffs and patches
- Commits changes with conventional commit messages

**Key Methods:**
- `create_branch(repo_path: str, branch_name: str) -> str`: Create git branch
- `apply_edits(plan: Dict, repo_path: str) -> Dict`: Apply code changes
- `generate_diff(repo_path: str) -> str`: Generate unified diff
- `commit_changes(repo_path: str, message: str) -> str`: Commit with message

**AST Tools:**
- Python: `libCST` or `tree-sitter-python`
- TypeScript: `ts-morph` (via Node.js subprocess) or `tree-sitter-typescript`
- Java: `JavaParser` (via subprocess)
- C#: Roslyn (via subprocess)

**Streaming:**
- Stream each file edit as it happens
- Send diffs in real-time
- Show commit messages

#### 3.6 Test Runner
**New File: `agents/test_runner.py`**

**Class: `TestRunner`**
- Runs unit tests, linters, and type checks
- Supports multiple languages (Python, TypeScript, Java, C#)
- Executes in containerized/sandboxed environment
- Collects and parses test results

**Key Methods:**
- `run_tests(repo_path: str, language: str) -> Dict`: Run test suite
- `run_linter(repo_path: str, language: str) -> Dict`: Run linter
- `run_typecheck(repo_path: str, language: str) -> Dict`: Type checking
- `parse_test_results(output: str, framework: str) -> Dict`: Parse results

**Supported Frameworks:**
- Python: `pytest`
- TypeScript/JavaScript: `jest`, `npm test`
- Java: `maven test`, `gradle test`
- C#: `dotnet test`

**Streaming:**
- Stream test execution in real-time
- Send test results as they complete
- Show linter and type check outputs

#### 3.7 Verifier
**New File: `agents/verifier.py`**

**Class: `Verifier`**
- Verifies acceptance criteria
- Compares test results to expectations
- Runs security scans (SAST)
- Determines if changes are ready for PR

**Key Methods:**
- `verify_acceptance(test_results: Dict, criteria: Dict) -> Dict`: Verify criteria
- `run_security_scan(repo_path: str) -> Dict`: Security analysis
- `check_test_coverage(results: Dict) -> Dict`: Coverage analysis

**Streaming:**
- Stream verification progress
- Send verification results

#### 3.8 PR Creator
**New File: `agents/pr_creator.py`**

**Class: `PRCreator`**
- Creates git commits and branches
- Pushes branch to remote
- Creates Pull Request via GitHub/GitLab API
- Generates PR description with template

**Key Methods:**
- `push_branch(repo_path: str, branch_name: str, remote: str) -> str`: Push branch
- `create_pr(repo_url: str, branch: str, title: str, description: str) -> Dict`: Create PR
- `generate_pr_description(plan: Dict, test_results: Dict, changes: Dict) -> str`: Generate description

**Streaming:**
- Stream PR creation progress
- Send PR link when created

### Phase 4: WebSocket Chat Handler

#### 4.1 Chat Route Implementation
**File: `routes/chat_routes.py`**

**WebSocket Events:**
- `connect`: Handle client connection
- `disconnect`: Handle client disconnection
- `chat_message`: Process user chat messages
- `approve_plan`: Handle human approval
- `reject_plan`: Handle plan rejection
- `cancel_request`: Cancel ongoing agent operation

**Session Management:**
- Track active sessions per WebSocket connection
- Store session state (current workflow stage, repo path, etc.)
- Handle concurrent requests from same client

**Message Flow:**
```
Client → "chat_message" event → Agent Orchestrator
Agent Orchestrator → Streams updates via "agent_update" event → Client
Client → "approve_plan" event → Agent Orchestrator (continues workflow)
```

#### 4.2 Error Handling
- Handle WebSocket connection errors gracefully
- Reconnect logic for dropped connections
- Timeout handling for long-running operations
- Error streaming to client

### Phase 5: Integration with Existing Services

#### 5.1 PKG Integration
- Leverage existing `services/pkg_generator.py` for PKG generation
- Use existing `services/parser_service.py` for repository parsing
- Integrate with existing `code_parser/` modules

#### 5.2 Document Processing
- Maintain existing `/process-pdf` endpoint
- Keep all existing PDF processing functionality
- No changes to `services/pdf_service.py`

#### 5.3 Repository Management
- Use existing `/clone-and-generate` endpoint logic
- Integrate with `cloned_repos/` directory structure
- Maintain backward compatibility

### Phase 6: Frontend Integration Points

#### 6.1 WebSocket Client Requirements
**Frontend should implement:**
- WebSocket connection to `ws://localhost:5001/ws/chat`
- Event listeners for:
  - `agent_update`: Real-time agent progress
  - `connection_status`: Connection state
  - `error`: Error messages

**Message Handling:**
- Display streaming logs in chat interface
- Show code changes with syntax highlighting
- Display test results in formatted tables
- Show approval requests with action buttons
- Render final summaries and PR links

#### 6.2 UI Components Needed
- Chat message input
- Streaming log viewer
- Code diff viewer
- Test results display
- Approval request modal
- Status indicator (current workflow stage)

### Phase 7: Configuration and Environment

#### 7.1 Environment Variables
**Add to `.env`:**
```env
# WebSocket Configuration
WEBSOCKET_CORS_ORIGINS=*
WEBSOCKET_ASYNC_MODE=eventlet

# Agent Configuration
AGENT_MAX_RETRIES=2
AGENT_TIMEOUT=3600
AGENT_APPROVAL_REQUIRED=true

# LLM Configuration (if not already present)
OPENAI_API_KEY=your_key_here
LLM_MODEL=gpt-4

# Git Configuration
GIT_USER_NAME=Agent
GIT_USER_EMAIL=agent@example.com
GITHUB_TOKEN=your_token_here  # For PR creation

# Test Runner Configuration
TEST_RUNNER_TIMEOUT=300
USE_DOCKER_FOR_TESTS=false
```

#### 7.2 Configuration Service
**New File: `utils/config.py`**
- Centralized configuration management
- Load agent-specific settings
- Validate required environment variables

### Phase 8: Logging and Monitoring

#### 8.1 Enhanced Logging
- Structured logging for all agent operations
- Log levels: DEBUG, INFO, WARNING, ERROR
- Log to both file and WebSocket stream
- Include session IDs in all log entries

#### 8.2 Monitoring
- Track agent operation metrics
- Monitor WebSocket connection health
- Log performance metrics (operation duration, etc.)

### Phase 9: Testing Strategy

#### 9.1 Unit Tests
- Test each agent component independently
- Mock WebSocket connections for testing
- Test intent extraction with various inputs
- Test PKG query engine with sample data

#### 9.2 Integration Tests
- Test complete workflow end-to-end
- Test WebSocket message flow
- Test error handling and recovery
- Test human approval workflow

#### 9.3 Test Files to Create
- `tests/test_intent_router.py`
- `tests/test_pkg_query_engine.py`
- `tests/test_agent_orchestrator.py`
- `tests/test_chat_routes.py`
- `tests/test_code_editor.py`
- `tests/test_test_runner.py`

### Phase 10: Security Considerations

#### 10.1 Input Validation
- Validate all user inputs
- Sanitize repository paths
- Validate git commands
- Prevent command injection

#### 10.2 Sandboxing
- Run code edits in isolated environment
- Execute tests in containers
- Limit resource usage (CPU, memory)
- Timeout long-running operations

#### 10.3 Secret Management
- Detect secrets in code changes
- Redact sensitive information from logs
- Secure API key storage
- Validate GitHub tokens

## File Structure

```
py-processor/
├── app.py                          # Modified: Add SocketIO
├── routes/
│   ├── pdf_routes.py               # Unchanged
│   └── chat_routes.py              # NEW: WebSocket chat handler
├── services/
│   ├── pdf_service.py              # Unchanged
│   ├── parser_service.py           # Unchanged
│   ├── pkg_generator.py            # Unchanged
│   ├── summary_generator.py        # Unchanged
│   ├── agent_orchestrator.py       # NEW: Main orchestrator
│   └── pkg_query_engine.py         # NEW: PKG query service
├── agents/
│   ├── __init__.py                 # Modified: Export new agents
│   ├── chunking_agent.py           # Unchanged
│   ├── extraction_agent.py        # Unchanged
│   ├── storing_agent.py            # Unchanged
│   ├── intent_router.py          # NEW: Intent extraction
│   ├── impact_analyzer.py         # NEW: Impact analysis
│   ├── planner.py                  # NEW: LLM-based planning
│   ├── code_editor.py              # NEW: Code editing
│   ├── test_runner.py              # NEW: Test execution
│   ├── verifier.py                 # NEW: Verification
│   └── pr_creator.py               # NEW: PR creation
├── utils/
│   ├── response_formatter.py       # Unchanged
│   ├── file_utils.py               # Unchanged
│   ├── schema_validator.py        # Unchanged
│   └── config.py                   # NEW: Configuration management
├── tests/
│   ├── test_app.py                 # Unchanged
│   ├── test_intent_router.py      # NEW
│   ├── test_pkg_query_engine.py   # NEW
│   ├── test_agent_orchestrator.py # NEW
│   ├── test_chat_routes.py        # NEW
│   └── test_code_editor.py        # NEW
├── requirements.txt                # Modified: Add WebSocket deps
├── .env                            # Modified: Add agent config
└── HIL_plan.MD                     # This file
```

## API Endpoints Summary

### Existing Endpoints (Unchanged)
- `POST /process-pdf`: Document processing
- `GET /health`: Health check
- `GET /chunks`: Vector search
- `POST /clone-and-generate`: Repository cloning and PKG generation

### New Endpoints
- `WebSocket /ws/chat`: Real-time chat interface with agent

## WebSocket Event Specification

### Client → Server Events

#### `chat_message`
```json
{
  "message": "Change login to require 2FA",
  "repo_url": "https://github.com/user/repo.git",
  "session_id": "optional-uuid"
}
```

#### `approve_plan`
```json
{
  "session_id": "uuid",
  "plan_id": "plan-uuid",
  "approved": true,
  "notes": "Optional approval notes"
}
```

#### `reject_plan`
```json
{
  "session_id": "uuid",
  "plan_id": "plan-uuid",
  "reason": "Reason for rejection"
}
```

#### `cancel_request`
```json
{
  "session_id": "uuid"
}
```

### Server → Client Events

#### `agent_update`
```json
{
  "type": "log|status|code_change|test_result|error|approval_request|summary",
  "timestamp": "2024-01-01T12:00:00Z",
  "stage": "intent_extraction|pkg_query|impact_analysis|planning|editing|testing|verification|pr_creation",
  "data": {
    // Stage-specific data structure
  },
  "session_id": "uuid"
}
```

#### `connection_status`
```json
{
  "status": "connected|disconnected|error",
  "message": "Status message",
  "session_id": "uuid"
}
```

## Implementation Phases Timeline

### Phase 1-2: Foundation (Week 1)
- WebSocket infrastructure
- Basic chat handler
- Agent orchestrator skeleton

### Phase 3: Core Agents (Week 2-3)
- Intent router
- PKG query engine
- Impact analyzer
- Planner

### Phase 4: Execution Agents (Week 4-5)
- Code editor
- Test runner
- Verifier
- PR creator

### Phase 5-6: Integration (Week 6)
- Integration with existing services
- Frontend integration points
- End-to-end testing

### Phase 7-8: Polish (Week 7)
- Configuration management
- Enhanced logging
- Security hardening

### Phase 9-10: Testing & Security (Week 8)
- Comprehensive testing
- Security review
- Documentation

## Success Criteria

1. ✅ WebSocket connection established and stable
2. ✅ User can chat with agent via WebSocket
3. ✅ All agent workflow steps stream live updates
4. ✅ Code changes visible in real-time with diffs
5. ✅ Test results stream as they execute
6. ✅ Human approval requests work correctly
7. ✅ PR creation and linking functional
8. ✅ All existing REST endpoints continue to work
9. ✅ Error handling graceful and informative
10. ✅ Security measures in place

## Dependencies to Add

```txt
flask-socketio>=5.3.0
python-socketio>=5.10.0
eventlet>=0.33.0
libcst>=1.1.0  # For Python AST editing
gitpython>=3.1.40  # For git operations
pygithub>=2.1.1  # For GitHub API (PR creation)
docker>=7.0.0  # For containerized test execution (optional)
```

## Notes

- All existing functionality must remain unchanged
- WebSocket implementation should be non-blocking
- Consider rate limiting for WebSocket connections
- Implement connection pooling for multiple concurrent users
- Cache PKG data to avoid regeneration on every request
- Use async/await patterns where possible for better performance
- Consider implementing a job queue (Redis/Celery) for long-running operations if needed

## Future Enhancements (Out of Scope)

- Multi-user session management
- Agent operation history and replay
- Advanced approval workflows
- Integration with CI/CD pipelines
- Agent learning from past changes
- Support for more languages and frameworks
