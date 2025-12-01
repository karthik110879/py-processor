# Agent Workflow Implementation Plan

## Overview

This plan implements a complete agent workflow system that enables users to chat with an AI agent, request code changes, and have the agent analyze, plan, execute, test, and create PRs for those changes. The implementation follows a phased approach prioritizing core workflow components first.

## Architecture Flow

```
User Chat Message (WebSocket)
    ↓
AgentOrchestrator.process_user_request()
    ↓
IntentRouter.extract_intent() → Structured Intent JSON
    ↓
PKGQueryEngine.query() → Impacted Modules/Endpoints
    ↓
ImpactAnalyzer.analyze() → Risk Assessment
    ↓
Planner.generate_plan() → Step-by-step Task List
    ↓
[Human Approval if Required]
    ↓
CodeEditExecutor.apply_edits() → Git Branch + Code Changes
    ↓
TestRunner.run_tests() → Test Results
    ↓
Verifier.verify() → Acceptance Check
    ↓
PRCreator.create_pr() → Pull Request
    ↓
Stream Results to User via WebSocket
```

## Phase 1: Core Workflow (Highest Priority)

### 1.1 AgentOrchestrator Implementation

**File:** `services/agent_orchestrator.py`

**Class Structure:**

```python
class AgentOrchestrator:
    def __init__(self)
    def process_user_request(session_id, user_message, repo_url, socketio, sid)
    def _ensure_repo_loaded(session_id, repo_url)
    def _load_pkg(repo_path)
    def _stream_update(socketio, sid, event_type, stage, data, session_id)
    def _execute_workflow(intent, pkg_data, repo_path, session_id, socketio, sid)
    def approve_plan(session_id, plan_id, socketio, sid)
```

**Key Responsibilities:**

- Manage session state (store repo_path, PKG data per session)
- Coordinate workflow execution
- Stream real-time updates via WebSocket
- Handle repo cloning/PKG loading when repo_url provided
- Route to appropriate agents based on workflow stage

**Session State Management:**

- Store in `active_sessions` dict in `chat_routes.py` or separate session store
- Each session contains: `repo_path`, `pkg_data`, `current_workflow_stage`, `pending_plan`

**Integration Points:**

- Called from `routes/chat_routes.py` `handle_chat_message()`
- Uses `services/parser_service.py` `generate_pkg()` for PKG loading
- Uses `routes/pdf_routes.py` clone logic for repo cloning

### 1.2 IntentRouter Implementation

**File:** `agents/intent_router.py`

**Class Structure:**

```python
class IntentRouter:
    def __init__(self)
    def extract_intent(user_message: str) -> Dict[str, Any]
    def _call_llm(user_message: str) -> Dict[str, Any]
```

**Intent JSON Schema:**

```json
{
  "intent": "change_login_flow|add_feature|fix_bug|refactor|other",
  "description": "Human-readable description",
  "risk": "low|medium|high",
  "tests_required": ["unit", "integration", "e2e"],
  "human_approval": true|false,
  "constraints": ["no breaking changes", "maintain backward compatibility"],
  "target_modules": ["auth", "user"]  // Optional hints
}
```

**LLM Integration:**

- Use `ChatOpenAI` from `langchain_openai` (same pattern as `extraction_agent.py`)
- Model: `os.getenv('LLM_MODEL', 'gpt-4')`
- Temperature: `os.getenv('LLM_TEMPERATURE', '0.3')`
- Structured output using Pydantic BaseModel

**Prompt Template:**

```
You are an intent extraction agent. Analyze the user's request and extract structured intent.

User request: {user_message}

Extract:
1. Intent type (change_login_flow, add_feature, fix_bug, refactor, other)
2. Description
3. Risk level (low/medium/high)
4. Required tests
5. Whether human approval is needed
6. Any constraints mentioned

Return structured JSON matching the intent schema.
```

### 1.3 PKGQueryEngine Implementation

**File:** `services/pkg_query_engine.py`

**Class Structure:**

```python
class PKGQueryEngine:
    def __init__(self, pkg_data: Dict[str, Any])
    def get_modules_by_tag(tag: str) -> List[Dict]
    def get_modules_by_path_pattern(pattern: str) -> List[Dict]
    def get_endpoints_by_path(path_pattern: str) -> List[Dict]
    def get_impacted_modules(module_ids: List[str], depth: int = 2) -> Dict
    def get_dependencies(module_id: str) -> Dict
    def get_symbols_by_name(name_pattern: str) -> List[Dict]
```

**Query Methods:**

- `get_modules_by_tag()`: Search modules by tags (e.g., "auth", "controller", "service")
- `get_endpoints_by_path()`: Find endpoints matching path patterns (e.g., "/login", "/auth/*")
- `get_impacted_modules()`: Build transitive closure of dependencies using `edges` from PKG
- `get_dependencies()`: Get callers (fan-in) and callees (fan-out) for a module

**PKG Data Structure Usage:**

- Access `pkg_data['modules']` for module list
- Access `pkg_data['symbols']` for symbol definitions
- Access `pkg_data['endpoints']` for API endpoints
- Access `pkg_data['edges']` for dependency relationships
- Use `moduleId`, `symbolId` format for lookups

**Example Implementation:**

```python
def get_modules_by_tag(self, tag: str) -> List[Dict]:
    """Find modules with matching tag in tags array."""
    return [m for m in self.pkg_data.get('modules', []) 
            if tag.lower() in [t.lower() for t in m.get('tags', [])]]
```

## Phase 2: Planning and Analysis

### 2.1 ImpactAnalyzer Implementation

**File:** `agents/impact_analyzer.py`

**Class Structure:**

```python
class ImpactAnalyzer:
    def __init__(self, pkg_data: Dict[str, Any])
    def analyze_impact(intent: Dict, target_modules: List[str]) -> Dict
    def calculate_risk_score(impacted_files: List[str]) -> str
    def find_affected_tests(modules: List[Dict]) -> List[str]
    def _build_dependency_graph(module_ids: List[str]) -> Set[str]
```

**Impact Analysis Output:**

```json
{
  "impacted_modules": [...],
  "impacted_files": ["path/to/file1.py", ...],
  "affected_tests": ["tests/test_auth.py", ...],
  "risk_score": "low|medium|high",
  "fan_in_count": 15,
  "fan_out_count": 8,
  "requires_approval": true,
  "estimated_complexity": "medium"
}
```

**Risk Calculation Logic:**

- Low: < 3 files, low fan-in/out, good test coverage
- Medium: 3-10 files, moderate dependencies
- High: > 10 files, high fan-in/out, core modules affected

**Integration:**

- Uses `PKGQueryEngine` to find dependencies
- Analyzes `edges` array in PKG for transitive closure
- Checks test files using naming patterns (test_*, *_test.py, *.spec.ts)

### 2.2 Planner Implementation

**File:** `agents/planner.py`

**Class Structure:**

```python
class Planner:
    def __init__(self)
    def generate_plan(intent: Dict, impacted_modules: Dict, constraints: List[str]) -> Dict
    def _call_llm(intent, modules, constraints) -> Dict
```

**Plan Output Schema:**

```json
{
  "plan_id": "uuid",
  "tasks": [
    {
      "task_id": 1,
      "task": "Add 2FA field to User entity",
      "files": ["src/user/user.entity.ts"],
      "changes": ["Add is2FAEnabled: boolean field"],
      "tests": ["tests/user.entity.spec.ts"],
      "notes": "Migration required",
      "estimated_time": "15min"
    }
  ],
  "total_estimated_time": "2h",
  "migration_required": true
}
```

**LLM Prompt Template:**

```
You are a code-change planner. Given:
- Intent: {intent_description}
- Impacted modules: {module_list_with_summaries}
- Constraints: {constraints}

Produce a numbered plan of code edits with:
- Files to modify (path)
- Specific changes (add field, update method signature, call new function)
- Tests to add/change (file + test name)
- Migration steps if DB changes
- CI changes required

Return JSON: {{ "tasks": [{{ "task": "...", "files": [...], "changes": [...], "tests": [...], "notes": "..." }}] }}
```

**Integration:**

- Uses `ChatOpenAI` with structured output
- Takes module summaries from PKG for context
- Generates conventional commit-style task descriptions

## Phase 3: Execution

### 3.1 CodeEditExecutor Implementation

**File:** `agents/code_editor.py`

**Class Structure:**

```python
class CodeEditExecutor:
    def __init__(self, repo_path: str)
    def create_branch(branch_name: str) -> str
    def apply_edits(plan: Dict) -> Dict
    def generate_diff() -> str
    def commit_changes(message: str) -> str
    def _edit_file(file_path: str, changes: List[str]) -> bool
    def _apply_ast_edit(file_path: str, edit_instructions: str) -> bool
```

**Git Operations:**

- Use `GitPython` library (already in requirements)
- Create branch: `feat/{scope}-{short-description}`
- Commit with conventional commit messages
- Generate unified diff using `git diff`

**Code Editing Strategy:**

- Phase 1: Simple file edits (read file, apply changes, write back)
- Phase 2: AST-aware edits using:
  - Python: `libCST` (already in requirements)
  - TypeScript: Tree-sitter or direct edits
  - Other: Tree-sitter parsers

**File Edit Flow:**

1. Read original file content
2. Apply changes (simple string replacement or AST transform)
3. Write modified content
4. Generate diff using git
5. Stream diff via WebSocket

**Diff Streaming:**

- Emit `code_change` events via WebSocket
- Format: `{"type": "code_change", "file": "path", "diff": "unified diff string"}`

### 3.2 TestRunner Implementation

**File:** `agents/test_runner.py`

**Class Structure:**

```python
class TestRunner:
    def __init__(self, repo_path: str)
    def run_tests(language: str = None) -> Dict
    def run_linter(language: str = None) -> Dict
    def run_typecheck(language: str = None) -> Dict
    def _detect_language() -> str
    def _parse_test_results(output: str, framework: str) -> Dict
```

**Test Execution:**

- Detect language from repo (Python, TypeScript, Java, C#)
- Run appropriate test command:
  - Python: `pytest -q --tb=short`
  - TypeScript: `npm test` or `jest`
  - Java: `mvn test` or `gradle test`
  - C#: `dotnet test`

**Output Format:**

```json
{
  "tests_passed": 45,
  "tests_failed": 2,
  "test_output": "...",
  "linter_errors": [],
  "typecheck_errors": [],
  "build_success": true
}
```

**Streaming:**

- Stream test output line-by-line via WebSocket
- Emit `test_result` events as tests complete

### 3.3 Verifier Implementation

**File:** `agents/verifier.py`

**Class Structure:**

```python
class Verifier:
    def __init__(self)
    def verify_acceptance(test_results: Dict, criteria: Dict) -> Dict
    def run_security_scan(repo_path: str) -> Dict
    def check_test_coverage(results: Dict) -> Dict
```

**Verification Criteria:**

- All unit tests pass
- New tests for changed functionality pass
- No new lint/type errors
- Security scan passes (basic SAST checks)
- Test coverage maintained or improved

**Output:**

```json
{
  "verified": true,
  "criteria_met": ["tests_pass", "no_lint_errors"],
  "security_issues": [],
  "coverage_change": "+2%",
  "ready_for_pr": true
}
```

### 3.4 PRCreator Implementation

**File:** `agents/pr_creator.py`

**Class Structure:**

```python
class PRCreator:
    def __init__(self, repo_path: str)
    def push_branch(branch_name: str, remote: str = "origin") -> str
    def create_pr(branch: str, title: str, description: str) -> Dict
    def generate_pr_description(plan: Dict, test_results: Dict, changes: Dict) -> str
```

**PR Creation Flow:**

1. Push branch to remote using GitPython
2. Use PyGithub (already in requirements) to create PR
3. Generate PR description from plan, test results, and changes
4. Add labels, assign reviewers (optional)

**PR Description Template:**

```
## Summary
{intent_description}

## Files Changed
- {file_list}

## Testing
- All unit tests passed ({test_count} total)
- Lint and type checks passed

## Migration
{migration_steps_if_any}

## Rollback
Revert branch: `git revert {commit_sha}`
```

## Integration Details

### WebSocket Event Streaming

**Event Types:**

- `status`: Workflow stage updates
- `log`: Processing logs
- `code_change`: Code modifications with diffs
- `test_result`: Test execution results
- `approval_request`: Human approval needed
- `error`: Error messages
- `summary`: Final summary

**Event Format:**

```json
{
  "type": "status|log|code_change|test_result|approval_request|error|summary",
  "timestamp": "ISO8601",
  "stage": "intent_extraction|pkg_query|impact_analysis|planning|editing|testing|verification|pr_creation",
  "data": {...},
  "session_id": "uuid"
}
```

### Session Management

**Session State Structure:**

```python
{
  "session_id": "uuid",
  "repo_url": "https://github.com/...",
  "repo_path": "/path/to/cloned_repos/repo",
  "pkg_data": {...},  # Loaded PKG JSON
  "current_intent": {...},
  "current_plan": {...},
  "workflow_stage": "intent_extraction|...",
  "pending_approval": {...}
}
```

### Repo Loading Flow

1. User sends message with `repo_url`
2. `AgentOrchestrator` checks if repo already cloned
3. If not cloned, use existing `/clone-and-generate` logic
4. Load PKG using `generate_pkg()` from `parser_service.py`
5. Store `repo_path` and `pkg_data` in session
6. Continue with workflow

## File Structure

```
services/
├── agent_orchestrator.py      # NEW: Main orchestrator
├── pkg_query_engine.py         # NEW: PKG query service
├── parser_service.py           # EXISTS: PKG generation
└── ...

agents/
├── intent_router.py            # NEW: Intent extraction
├── impact_analyzer.py          # NEW: Impact analysis
├── planner.py                  # NEW: LLM-based planning
├── code_editor.py              # NEW: Code editing
├── test_runner.py              # NEW: Test execution
├── verifier.py                 # NEW: Verification
└── pr_creator.py               # NEW: PR creation

routes/
├── chat_routes.py              # EXISTS: WebSocket handlers (needs integration)
└── ...
```

## Implementation Order

1. **AgentOrchestrator** - Core workflow coordination
2. **IntentRouter** - Extract user intent
3. **PKGQueryEngine** - Query knowledge graph
4. **ImpactAnalyzer** - Analyze change impact
5. **Planner** - Generate change plan
6. **CodeEditExecutor** - Apply code changes
7. **TestRunner** - Execute tests
8. **Verifier** - Verify acceptance
9. **PRCreator** - Create pull requests

## Dependencies

All required dependencies are already in `requirements.txt`:

- `flask-socketio>=5.3.0` ✓
- `langchain-openai>=1.0.3` ✓
- `libcst>=1.1.0` ✓
- `gitpython>=3.1.40` ✓
- `pygithub>=2.1.1` ✓

## Environment Variables

All required env vars are in `env.example`:

- `OPENAI_API_KEY` ✓
- `LLM_MODEL` ✓
- `GITHUB_TOKEN` ✓
- `GIT_USER_NAME` ✓
- `GIT_USER_EMAIL` ✓

## Testing Strategy

1. Unit tests for each agent component
2. Integration tests for workflow end-to-end
3. Mock WebSocket for testing
4. Test with sample repos

## Error Handling

- Graceful degradation if LLM unavailable
- Retry logic for transient failures
- Clear error messages streamed to user
- Rollback on test failures