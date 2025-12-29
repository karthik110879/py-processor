# Intelligent Code Analysis & Document Processing Platform

A comprehensive Flask-based platform that combines document processing, code repository analysis, knowledge graph generation, and AI-powered autonomous code change agents. This system enables intelligent code understanding, automated refactoring, and real-time collaboration through WebSocket-based chat interfaces.

## Overview

This platform provides a unified solution for:
- **Document Processing**: Multi-format document parsing with OCR, table extraction, and intelligent chunking
- **Code Analysis**: Multi-language code parsing and Project Knowledge Graph (PKG) generation
- **Graph Database Integration**: Neo4j-based storage and querying of code relationships
- **AI Agent System**: Autonomous code change agents that can analyze, plan, execute, test, and create PRs
- **Diagram Generation**: Visual dependency and architecture diagrams from code structure
- **Real-time Chat Interface**: WebSocket-based interactive agent communication

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ REST Client  │  │ WebSocket    │  │  Frontend UI        │  │
│  │ (PDF/API)    │  │ Chat Client  │  │  (Real-time)        │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────┘  │
└─────────┼─────────────────┼──────────────────────┼────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Flask Application Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ PDF Routes  │  │ Chat Routes  │  │  Agent Orchestrator │  │
│  │ (REST API)  │  │ (WebSocket)  │  │  (Workflow Manager)  │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬─────────┘  │
└─────────┼─────────────────┼──────────────────────┼────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Service Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ PDF Service  │  │ Parser        │  │  PKG Generator       │  │
│  │              │  │ Service       │  │                      │  │
│  └──────────────┘  └──────┬───────┘  └──────────┬─────────┘  │
└────────────────────────────┼──────────────────────┼────────────┘
                             │                      │
                             ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent System                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Intent       │  │ Query        │  │  Impact Analyzer     │  │
│  │ Router       │  │ Handler      │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────┘  │
│         │                 │                      │             │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────────▼─────────┐  │
│  │ Planner      │  │ Code Editor   │  │  Test Runner       │  │
│  │              │  │               │  │                     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────┘  │
│         │                 │                      │             │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────────▼─────────┐  │
│  │ Verifier     │  │ PR Creator    │  │  Diagram Generator  │  │
│  └──────────────┘  └───────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Data Layer                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Neo4j        │  │ File Cache   │  │  Qdrant (Optional)  │  │
│  │ Graph DB     │  │ (PKG JSON)    │  │  Vector Store       │  │
│  └──────────────┘  └──────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Core Features

### 1. Document Processing

Advanced document parsing capabilities for multiple file formats with intelligent content extraction.

**Supported Formats:**
- PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, HTML, TXT, MD

**Key Capabilities:**
- **OCR Support**: Process scanned documents and image-based PDFs
- **Table Extraction**: Extract tables with structured data (rows, columns, markdown)
- **Image Extraction**: Extract images with metadata and base64 encoding
- **Document Chunking**: Split large documents into manageable chunks with configurable overlap
- **Metadata Extraction**: Title, author, date, page count, language, subject, keywords
- **Multiple Output Formats**: Markdown, JSON, and HTML

**Workflow:**
```
Document Upload
  → Format Detection
  → Content Extraction (OCR if needed)
  → Structure Analysis (sections, tables, images)
  → Chunking (if requested)
  → Format Conversion
  → Response with structured data
```

### 2. Code Analysis & Knowledge Graph Generation

Comprehensive codebase analysis that builds a Project Knowledge Graph (PKG) representing the entire codebase structure and relationships.

**Supported Languages:**
- Python, TypeScript, JavaScript, Java, C, C++, C#

**Analysis Capabilities:**
- **Multi-language Parsing**: Tree-sitter based AST parsing for accurate code understanding
- **Module Extraction**: File-level modules with metadata (LOC, hash, kind tags)
- **Symbol Extraction**: Functions, classes, interfaces, methods, variables, enums
- **Relationship Mapping**: Imports, calls, implements, extends, routes-to, uses-db, tests
- **Endpoint Discovery**: HTTP/RPC endpoints with method, path, and handler mapping
- **Framework Detection**: Automatic detection of NestJS, Spring Boot, ASP.NET, etc.
- **Feature Grouping**: Higher-level feature/bounded context identification

**PKG Schema Structure:**
- **Project**: Root metadata (id, name, rootPath, languages, summary)
- **Modules**: File-level nodes with imports, exports, kind tags, summaries
- **Symbols**: Functions, classes, interfaces with signatures, visibility, summaries
- **Endpoints**: HTTP/RPC endpoints with method, path, handler mapping
- **Edges**: Relationships (imports, calls, implements, extends, routes-to, etc.)
- **Features**: Optional feature groupings with module associations

**Repository Analysis Workflow:**
```
Repository URL
  → Clone Repository (if not cached)
  → Detect Languages & Frameworks
  → Parse Files (multi-language tree-sitter)
  → Extract Modules, Symbols, Endpoints
  → Build Relationship Graph
  → Calculate Metrics (fan-in, fan-out, centrality, complexity)
  → Generate PKG JSON
  → Store in Neo4j (optional)
  → Cache PKG for future use
```

### 3. Neo4j Graph Database Integration

Persistent storage and advanced querying of code knowledge graphs using Neo4j.

**Features:**
- **Version Tracking**: Store multiple PKG versions with VERSION_OF relationships
- **Batch Operations**: Efficient batch insertion for large codebases
- **Indexing**: Automatic indexes on frequently queried properties
- **Fulltext Search**: Fulltext indexes on summaries for semantic search
- **Vector Indexes**: Optional vector embeddings for similarity search (Neo4j 5.x+)
- **Metrics Storage**: Precomputed fan-in, fan-out, centrality, complexity metrics
- **Caching**: Diagram and query result caching with TTL

**Node Types:**
- `Project`: Root project nodes
- `Package`: Versioned PKG snapshots
- `Module`: File-level modules
- `Symbol`: Functions, classes, interfaces
- `Endpoint`: HTTP/RPC endpoints
- `Feature`: Feature groupings
- `Document`: Cached diagrams and documents
- `Metadata`: Project metadata

**Relationship Types:**
- `HAS_MODULE`, `HAS_SYMBOL`, `HAS_ENDPOINT`, `HAS_FEATURE`
- `IMPORTS`, `CALLS`, `IMPLEMENTS`, `EXTENDS`, `ROUTES_TO`, `USES_DB`, `TESTS`
- `CONTAINS`, `VERSION_OF`, `HAS_METADATA`

### 4. AI Agent System

Autonomous code change agents that can understand natural language requests, analyze codebases, plan changes, execute edits, run tests, and create pull requests.

**Agent Components:**

1. **Intent Router** (`agents/intent_router.py`)
   - Converts natural language to structured intent
   - Categories: `informational_query`, `diagram_request`, `code_change`
   - Extracts: intent type, description, risk level, test requirements, constraints, target modules

2. **Query Handler** (`agents/query_handler.py`)
   - Answers questions about codebase using PKG data
   - Supports: entry files, app components, features, dependencies, modules, endpoints
   - Uses LLM with PKG context for natural language responses

3. **Impact Analyzer** (`agents/impact_analyzer.py`)
   - Assesses change impact on codebase
   - Calculates risk scores
   - Identifies affected modules and dependencies
   - Determines if human approval is required

4. **Planner** (`agents/planner.py`)
   - Generates step-by-step code change plans
   - Uses LLM with intent, impact analysis, and module context
   - Creates task list with files, changes, and test expectations

5. **Code Editor** (`agents/code_editor.py`)
   - Applies code changes from plan
   - Creates git branches
   - Executes file edits (AST-aware or text-based)
   - Iterative code fixing with error feedback
   - Code validation and linting
   - Generates diffs
   - Supports fuzzy file matching

6. **Test Runner** (`agents/test_runner.py`)
   - Runs unit, integration, and e2e tests
   - Supports multiple test frameworks (pytest, jest, unittest, etc.)
   - Optional Docker-based test execution
   - Test failure feedback loop with automatic code fixing
   - Test result parsing and reporting

7. **Verifier** (`agents/verifier.py`)
   - Verifies changes meet acceptance criteria
   - Compares test results to expectations
   - Determines if changes are ready for PR

8. **PR Creator** (`agents/pr_creator.py`)
   - Automatically forks repositories if needed
   - Creates git commits with descriptive messages
   - Pushes branches to forked repository
   - Opens pull requests on GitHub (to original repo)
   - Generates PR descriptions with change summary
   - Configures git remotes (origin=fork, upstream=original)

**Agent Workflow:**
```
User Message (WebSocket)
  ↓
Intent Router → Extract Structured Intent
  ↓
PKG Query Engine → Find Impacted Modules/Endpoints
  ↓
Impact Analyzer → Assess Risk & Impact
  ↓
Planner → Generate Step-by-Step Plan
  ↓
[Human Approval if Required]
  ↓
Code Editor → Create Branch & Apply Changes
  ↓
Test Runner → Execute Tests
  ↓
Verifier → Verify Acceptance Criteria
  ↓
PR Creator → Create Pull Request
  ↓
Stream Results to User (Real-time Updates)
```

**Intent Categories:**

- **Informational Query**: Questions about codebase ("What is this project?", "Explain module X")
- **Diagram Request**: Visualization requests ("Show dependencies", "Create architecture diagram")
- **Code Change**: Modification requests ("Add feature X", "Fix bug Y", "Refactor Z")

### 5. Diagram Generation

Visual representation of code structure, dependencies, and architecture.

**Diagram Types:**
- **Dependency Diagrams**: Module dependency graphs
- **Architecture Diagrams**: High-level system architecture
- **Feature Diagrams**: Feature-based groupings
- **Custom Diagrams**: User-specified module subsets

**Features:**
- **Mermaid Code Generation**: Generates Mermaid diagram code
- **Image Rendering**: Optional image rendering via Playwright or mermaid.ink API
- **Interactive Diagrams**: Interactive HTML diagrams with zoom/pan
- **Customization**: Theme, layout, node limits, label visibility, grouping options
- **Caching**: Neo4j-based caching with TTL for performance

**Diagram Generation Workflow:**
```
User Request
  → Diagram Generator
  → Query PKG for Modules/Relationships
  → Apply Filters (depth, node limits, customizations)
  → Generate Mermaid Code
  → Render (Playwright or mermaid.ink API)
  → Cache Result (optional)
  → Return Diagram (code, image, or interactive HTML)
```

**Customization Options:**
- **Theme**: dark, forest, neutral
- **Layout**: force (left-right), circular, hierarchical
- **Node Limit**: Maximum nodes to include
- **Show Labels**: Toggle label visibility
- **Group By**: feature, layer, kind

### 6. Real-time Chat Interface

WebSocket-based bidirectional communication for interactive agent collaboration.

**Additional Capabilities:**
- **Auto-Forking**: Automatically forks repositories not owned by authenticated user
- **Spec File Generation**: When `CODE_EDITS_ENABLED=false`, generates markdown specification files instead of editing code
- **Iterative Code Fixing**: Automatically fixes code based on linting errors and test failures
- **Fuzzy File Matching**: Resolves file paths with confidence scoring when exact matches not found
- **AST-Aware Editing**: Uses Abstract Syntax Trees for safer code transformations
- **Test Failure Feedback Loop**: Automatically fixes code when tests fail and re-runs tests
- **MCP Integration**: Model Context Protocol support for spec file notifications

**WebSocket Events:**

**Client → Server:**
- `connect`: Establish connection (auto-assigns session_id)
- `chat_message`: Send user message with optional repo_url
- `approve_plan`: Approve pending plan for execution
- `reject_plan`: Reject plan with optional reason

**Server → Client:**
- `connected`: Connection confirmation with session_id
- `agent_update`: Real-time workflow updates
  - Types: `status`, `log`, `code_change`, `test_result`, `query_response`, `diagram_response`, `approval_request`, `summary`, `error`
  - Stages: `intent_extraction`, `pkg_query`, `impact_analysis`, `planning`, `editing`, `testing`, `verification`, `pr_creation`
- `error`: Error notifications

**Session Management:**
- Automatic session creation on connection
- Session persistence for:
  - `repo_url` (original and forked)
  - `repo_path` (local repository path)
  - `pkg_data` (cached PKG JSON)
  - `current_intent` (extracted intent)
  - `current_plan` (generated plan)
  - `pending_approval` (plan_id awaiting approval)
  - `fork_info` (fork operation details)
- Session cleanup on disconnect
- Session lookup by socket ID (SID)

**Real-time Streaming:**
- Live status updates during agent operations
- Code change diffs streamed in real-time
- Test results streamed as they complete
- Query responses with references
- Diagram generation progress
- Validation results (errors, warnings)
- File resolution notifications (fuzzy matching)
- Approval requests with plan details
- Spec file generation notifications (MCP namespace)

## Installation & Setup

### Prerequisites

- Python 3.10+
- Git (for repository cloning)
- Neo4j 4.x+ (optional, for graph database features)
- Node.js & npm (optional, for mermaid-cli diagram rendering and ts-morph)
- Playwright (optional, for diagram image rendering)

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd py-processor
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Node.js dependencies (optional, for TypeScript parsing):**
   ```bash
   npm install
   ```

5. **Install optional dependencies:**

   **For diagram rendering (Playwright):**
   ```bash
   pip install playwright
   playwright install chromium
   ```

   **For Mermaid CLI (alternative rendering):**
   ```bash
   npm install -g @mermaid-js/mermaid-cli
   ```

6. **Configure environment variables:**
   ```bash
   cp env.example .env
   # Edit .env with your configuration
   ```

## Python Packages & Dependencies

### Core Dependencies

**Web Framework:**
- `flask>=3.0.0` - Web framework
- `flask-cors>=4.0.0` - CORS support
- `flask-socketio>=5.3.0` - WebSocket support
- `python-socketio>=5.10.0` - Socket.IO implementation
- `eventlet>=0.33.0` - Async networking library

**Document Processing:**
- `docling>=2.61.1` - Document conversion and OCR
- `opencv-python-headless<4.11.0` - Image processing
- `numpy<2` - Numerical operations

**Code Parsing:**
- `tree-sitter>=0.20.0` - Incremental parsing system
- `tree-sitter-python>=0.20.0` - Python parser
- `tree-sitter-typescript>=0.20.0` - TypeScript parser
- `tree-sitter-javascript>=0.20.0` - JavaScript parser
- `tree-sitter-java>=0.20.0` - Java parser
- `tree-sitter-c>=0.20.0` - C parser
- `tree-sitter-cpp>=0.20.0` - C++ parser
- `tree-sitter-c-sharp>=0.20.0` - C# parser
- `libcst>=1.1.0` - Concrete Syntax Tree for Python

**AI & LLM:**
- `langchain>=1.0.8` - LLM framework
- `langchain-core>=1.1.0` - Core LangChain components
- `langchain-text-splitters>=1.0.0` - Text splitting utilities
- `langchain-openai>=1.0.3` - OpenAI integration

**Database & Storage:**
- `neo4j>=6.0.3` - Neo4j graph database driver
- `qdrant-client>=1.16.0` - Vector database client (optional)

**Git & GitHub:**
- `gitpython>=3.1.40` - Git operations
- `pygithub>=2.1.1` - GitHub API integration

**Utilities:**
- `python-dotenv>=1.0.0` - Environment variable management
- `pydantic>=2.0.0` - Data validation
- `jsonschema>=4.0.0` - JSON schema validation
- `playwright>=1.40.0` - Browser automation for diagram rendering

**Testing:**
- `pytest>=7.4.0` - Testing framework

### Node.js Dependencies

- `ts-morph>=27.0.2` - TypeScript AST manipulation (for advanced TypeScript parsing)

### Environment Configuration

**Required for Basic Features:**
```env
HOST=0.0.0.0
PORT=5001
DEBUG=False
UPLOAD_FOLDER=/tmp
```

**Required for Agent Features:**
```env
OPENAI_API_KEY=your_openai_api_key
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=2000
```

**Required for Neo4j Integration:**
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=repos
```

**Optional Configuration:**
```env
# WebSocket
WEBSOCKET_CORS_ORIGINS=*
WEBSOCKET_ASYNC_MODE=eventlet
WEBSOCKET_PING_TIMEOUT=60
WEBSOCKET_PING_INTERVAL=25

# Agent Behavior
AGENT_APPROVAL_REQUIRED=true
AGENT_AUTO_APPLY_LOW_RISK=false
AGENT_MAX_RETRIES=2
AGENT_TIMEOUT=3600
CODE_EDITS_ENABLED=false  # If false, generates spec files instead

# Git/GitHub
GIT_USER_NAME=Agent
GIT_USER_EMAIL=agent@example.com
GITHUB_TOKEN=your_github_token
GITHUB_API_URL=https://api.github.com

# Test Runner
TEST_RUNNER_TIMEOUT=300
USE_DOCKER_FOR_TESTS=false
DOCKER_IMAGE_PREFIX=test-runner

# PKG Generation
PKG_FAN_THRESHOLD=3
PKG_INCLUDE_FEATURES=true
PKG_CACHE_ENABLED=true

# Security
MAX_IMPACTED_FILES_FOR_AUTO_APPROVAL=5
REQUIRE_HUMAN_APPROVAL_FOR_MIGRATIONS=true

# Code Editing
USE_AST_EDITING=true
FUZZY_FILE_MATCHING_ENABLED=true
FUZZY_MATCH_CONFIDENCE_THRESHOLD=0.8
ENABLE_FILE_VALIDATION=true
MAX_FIX_RETRIES=3
AUTO_FIX_LINT=true
INCLUDE_CODE_EXAMPLES=true
FIX_ON_TEST_FAILURE=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=standard
LOG_STRUCTURED=false
LOG_LLM_PROMPTS=false

# Neo4j
NEO4J_BATCH_SIZE=1000
NEO4J_MAX_RETRIES=3
NEO4J_RETRY_DELAY=1.0
EMBEDDING_DIMENSION=1536

# File Processing
MAX_FILE_SIZE=16777216  # 16MB
SUPPORTED_LANGUAGES=python,typescript,javascript,java,c,cpp,csharp
```

### Neo4j Setup

1. **Install Neo4j:**
   - Download from https://neo4j.com/download/
   - Or use Docker: `docker run -p 7474:7474 -p 7687:7687 neo4j:latest`

2. **Configure connection:**
   - Set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in `.env`
   - Default: `bolt://localhost:7687`, user: `neo4j`

3. **Verify connection:**
   - The application will automatically create indexes on first connection
   - Check logs for connection status

### Running the Application

```bash
python app.py
```

The server will start on `http://localhost:5001` (or configured PORT).

**Health Check:**
```bash
curl http://localhost:5001/health
```

**WebSocket Status:**
```bash
curl http://localhost:5001/ws/status
```

## API Documentation

### REST Endpoints

#### POST /process-pdf

Process a document file and get parsed content.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: Form data with field `file` containing document
- Query Parameters:
  - `enable_ocr`: `true`/`false` (default: `false`)
  - `output_format`: `markdown`/`json`/`html` (default: `markdown`)
  - `extract_tables`: `true`/`false` (default: `true`)
  - `extract_images`: `true`/`false` (default: `true`)
  - `chunk_size`: Integer (optional)
  - `chunk_overlap`: Integer (default: `200`)

**Response:**
```json
{
  "status": "success",
  "data": {
    "metadata": {...},
    "content": "...",
    "sections": [...],
    "tables": [...],
    "images": [...],
    "chunks": [...]
  },
  "message": "Successfully processed document"
}
```

#### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "websocket_enabled": true,
  "timestamp": "2024-01-01T00:00:00"
}
```

#### GET /ws/status

WebSocket server status.

**Response:**
```json
{
  "websocket_enabled": true,
  "active_sessions": 2,
  "timestamp": "2024-01-01T00:00:00"
}
```

#### POST /clone-and-generate

Clone a repository and generate PKG JSON.

**Request:**
- Method: `POST`
- Content-Type: `application/json`
- Body:
```json
{
  "repo_url": "https://github.com/user/repo.git"
}
```
- Query Parameters:
  - `generate_summaries`: `true`/`false` (default: `false`) - Generate LLM summaries
  - `fan_threshold`: Integer (default: `3`) - Fan-in threshold for filtering
  - `include_features`: `true`/`false` (default: `true`) - Include feature groupings
  - `format`: `pkg`/`legacy` (default: `pkg`) - Output format

**Response:**
```json
{
  "status": "success",
  "data": {
    "project": {...},
    "modules": [...],
    "symbols": [...],
    "endpoints": [...],
    "edges": [...],
    "features": [...]
  },
  "message": "PKG generated successfully for repo-name"
}
```

**Features:**
- Automatically forks repository if not owned by authenticated user
- Checks for existing cloned repository before cloning
- Validates git SHA for cache invalidation
- Supports both PKG and legacy JSON formats

#### GET /chunks

Search stored document chunks (requires LangChain agents).

**Request:**
- Method: `GET`
- Query Parameters:
  - `q`: Search query string

**Response:**
```json
{
  "result": "Search results..."
}
```

#### POST /api/cleanup/*

Cleanup routes for temporary files and resources (see `routes/cleanup_routes.py`).

### WebSocket Events

#### Client Events

**connect**
- Establishes connection
- Server responds with `connected` event and `session_id`

**chat_message**
```json
{
  "message": "User's message text",
  "repo_url": "https://github.com/user/repo.git",
  "session_id": "optional-session-uuid"
}
```

**approve_plan**
```json
{
  "session_id": "session-uuid",
  "plan_id": "plan-uuid",
  "codeEdits": true/false
}
```

**approval_response**
```json
{
  "session_id": "session-uuid",
  "plan_id": "plan-uuid",
  "approved": true/false,
  "codeEdits": true/false,
  "reason": "Optional rejection reason"
}
```

**reject_plan**
```json
{
  "session_id": "session-uuid",
  "plan_id": "plan-uuid",
  "reason": "Optional rejection reason"
}
```

#### Server Events

**connected**
```json
{
  "session_id": "uuid",
  "status": "connected",
  "message": "WebSocket connection established",
  "timestamp": "2024-01-01T00:00:00"
}
```

**agent_update**
```json
{
  "type": "status|log|code_change|test_result|query_response|diagram_response|approval_request|summary|error",
  "timestamp": "2024-01-01T00:00:00",
  "stage": "intent_extraction|pkg_query|impact_analysis|planning|editing|testing|verification|pr_creation",
  "data": {...},
  "session_id": "uuid"
}
```

**error**
```json
{
  "type": "connection_error|validation_error|processing_error|unhandled_error",
  "message": "Error description",
  "timestamp": "2024-01-01T00:00:00"
}
```

## How It Works

### System Initialization

1. **Flask Application Startup:**
   - Loads configuration from `.env` or `config.yaml/json`
   - Initializes logging (standard or structured JSON)
   - Sets up CORS for cross-origin requests
   - Initializes SocketIO for WebSocket support
   - Registers route blueprints (PDF, cleanup, chat, MCP)
   - Creates error handlers for common HTTP errors

2. **Neo4j Connection:**
   - Attempts connection with retry logic (exponential backoff)
   - Creates indexes on first connection:
     - Node indexes (Project, Module, Symbol, Endpoint, Feature, Package)
     - Fulltext indexes for summaries
     - Vector indexes for embeddings (Neo4j 5.x+)
   - Falls back gracefully if Neo4j unavailable

3. **Session Management:**
   - In-memory session store (production: use Redis)
   - Auto-generates session IDs on WebSocket connection
   - Tracks: repo_url, repo_path, pkg_data, current_intent, current_plan

### Request Processing Flow

**REST API Requests:**
```
Client Request
  → Flask Route Handler
  → Service Layer (PDF/Parser/PKG)
  → Agent/Processor Components
  → Data Layer (Neo4j/File System)
  → Response Formatter
  → JSON Response
```

**WebSocket Requests:**
```
Client Connect
  → SocketIO Handler
  → Session Creation
  → Connected Event (with session_id)
  
Client Message
  → Chat Route Handler
  → Agent Orchestrator
  → Intent Router
  → Route by Category
  → Execute Workflow
  → Stream Updates via SocketIO
  → Final Response
```

### PKG Generation Process

1. **File Collection:**
   - Recursively scans repository directory
   - Filters by supported file extensions
   - Excludes common ignore patterns

2. **Language Detection:**
   - Maps file extensions to languages
   - Initializes appropriate tree-sitter parser
   - Handles multi-language projects

3. **AST Parsing:**
   - Parses each file to Abstract Syntax Tree
   - Extracts definitions (functions, classes, etc.)
   - Captures import statements
   - Identifies endpoint decorators/routes

4. **Normalization:**
   - Converts AST nodes to standardized format
   - Extracts signatures, visibility, types
   - Builds module metadata

5. **Relationship Extraction:**
   - Resolves import statements
   - Maps function/method calls
   - Links endpoints to handlers
   - Identifies inheritance/implementation

6. **Metrics Calculation:**
   - Fan-in: Count incoming dependencies
   - Fan-out: Count outgoing dependencies
   - Centrality: Graph-based importance score
   - Complexity: Cyclomatic complexity

7. **Feature Detection (optional):**
   - Analyzes module structure
   - Groups by directory patterns
   - Identifies bounded contexts

8. **PKG Assembly:**
   - Combines all extracted data
   - Applies fan_threshold filtering
   - Generates summaries (if LLM available)
   - Validates against schema

## Workflows & Flows

### PDF Processing Flow

```
1. Document Upload
   ↓
2. Format Detection (PDF, DOCX, etc.)
   ↓
3. Content Extraction
   ├─→ OCR (if enabled)
   ├─→ Text Extraction
   ├─→ Table Extraction
   └─→ Image Extraction
   ↓
4. Structure Analysis
   ├─→ Section Detection
   ├─→ Metadata Extraction
   └─→ Language Detection
   ↓
5. Chunking (if requested)
   ├─→ Split by size
   ├─→ Maintain overlap
   └─→ Preserve sentence boundaries
   ↓
6. Format Conversion
   ├─→ Markdown (default)
   ├─→ JSON
   └─→ HTML
   ↓
7. Response with Structured Data
```

### Repository Analysis Flow

```
1. Repository URL Provided
   ↓
2. Auto-Fork Check (if GitHub token available)
   ├─→ Parse owner/repo from URL
   ├─→ Check if user owns repository
   ├─→ Fork if needed (store fork_info)
   └─→ Update repo_url to fork if forked
   ↓
3. Check Session Cache
   ├─→ If PKG data exists in session → Return cached
   └─→ If not → Continue
   ↓
4. Check Neo4j (if configured)
   ├─→ Extract project_id from repo URL
   ├─→ Query Neo4j for Package node
   ├─→ If exists → Load PKG from Neo4j
   └─→ If not → Continue
   ↓
5. Check File Cache (pkg.json)
   ├─→ Check if pkg.json exists in repo_path
   ├─→ Compare git SHA (current vs cached)
   ├─→ If SHA matches → Return cached PKG
   └─→ If SHA differs or missing → Continue
   ↓
6. Clone Repository (if not exists locally)
   ├─→ Extract repo name from URL
   ├─→ Check cloned_repos/{repo_name}
   ├─→ Clone if not exists
   └─→ Configure git remotes (origin=fork, upstream=original)
   ↓
7. Detect Languages & Frameworks
   ├─→ Scan file extensions
   ├─→ Detect framework (NestJS, Spring Boot, ASP.NET, etc.)
   └─→ Identify project structure
   ↓
8. Parse Files (multi-language tree-sitter)
   ├─→ Python → tree-sitter-python
   ├─→ TypeScript → tree-sitter-typescript
   ├─→ JavaScript → tree-sitter-javascript
   ├─→ Java → tree-sitter-java
   ├─→ C/C++ → tree-sitter-c/cpp
   └─→ C# → tree-sitter-c-sharp
   ↓
9. Extract Definitions
   ├─→ Modules (files with metadata: LOC, hash, kind tags)
   ├─→ Symbols (functions, classes, interfaces, methods, variables, enums)
   ├─→ Endpoints (HTTP/RPC with method, path, handler)
   └─→ Relationships (imports, calls, implements, extends, routes-to, uses-db, tests)
   ↓
10. Build Relationship Graph
    ├─→ Resolve imports (cross-file dependencies)
    ├─→ Map function/method calls
    ├─→ Link endpoints to handler functions
    ├─→ Calculate metrics:
    │   ├─→ Fan-in (incoming dependencies)
    │   ├─→ Fan-out (outgoing dependencies)
    │   ├─→ Centrality (importance in graph)
    │   └─→ Complexity (cyclomatic complexity)
    └─→ Build edge list
   ↓
11. Generate Features (optional, if include_features=true)
    ├─→ Detect feature boundaries
    ├─→ Group modules by feature/bounded context
    └─→ Create feature nodes
   ↓
12. Generate PKG JSON
    ├─→ Project metadata (id, name, rootPath, languages, gitSha, summary)
    ├─→ Modules array (with summaries if LLM available)
    ├─→ Symbols array (filtered by fan_threshold)
    ├─→ Endpoints array
    ├─→ Edges array (relationships)
    └─→ Features array (optional)
   ↓
13. Store in Neo4j (if configured)
    ├─→ Create/update Project node
    ├─→ Create Package node (versioned snapshot)
    ├─→ Batch insert Module nodes
    ├─→ Batch insert Symbol nodes
    ├─→ Batch insert Endpoint nodes
    ├─→ Batch insert Feature nodes
    ├─→ Batch insert relationships
    ├─→ Create indexes (if not exist)
    └─→ Create fulltext/vector indexes (if supported)
   ↓
14. Cache PKG JSON (file system)
    ├─→ Save to {repo_path}/pkg.json
    └─→ Include git SHA for validation
   ↓
15. Store in Session
    ├─→ Store repo_url (original and fork)
    ├─→ Store repo_path
    ├─→ Store pkg_data
    └─→ Store fork_info (if applicable)
   ↓
16. Return PKG Data
```

### Agent Workflow Flow

```
1. User Message (WebSocket)
   ↓
2. Intent Router
   ├─→ Extract intent category (query/diagram/code_change)
   ├─→ Extract intent type
   ├─→ Extract description, risk, constraints
   ├─→ Extract target modules
   └─→ Extract target files
   ↓
3. Route by Intent Category
   ├─→ Informational Query → Query Handler → Return Answer
   ├─→ Diagram Request → Diagram Generator → Return Diagram
   └─→ Code Change → Continue workflow
   ↓
4. Ensure Repository Loaded
   ├─→ Check session cache (PKG data)
   ├─→ Check Neo4j (by project_id)
   ├─→ Check file cache (pkg.json with git SHA validation)
   ├─→ Auto-fork repository if needed (GitHub token available)
   ├─→ Clone repository (if not exists)
   └─→ Generate PKG (if not cached)
   ↓
5. PKG Query Engine
   ├─→ Query impacted modules (by tags, filenames)
   ├─→ Query dependencies (imports, calls)
   ├─→ Query related symbols/endpoints
   └─→ Fuzzy file matching (if enabled)
   ↓
6. Impact Analyzer
   ├─→ Assess change impact
   ├─→ Calculate risk score
   ├─→ Identify affected modules
   ├─→ Determine approval requirement
   └─→ Check auto-approval thresholds
   ↓
7. Planner
   ├─→ Generate step-by-step plan
   ├─→ Create task list with files, changes, tests
   ├─→ Validate file existence (with fuzzy matching)
   ├─→ Define test expectations
   └─→ Generate plan_id
   ↓
8. Human Approval (if required)
   ├─→ Stream approval_request event
   ├─→ Wait for approve_plan/approval_response
   ├─→ Check codeEdits flag (spec generation vs execution)
   └─→ Continue on approval
   ↓
9a. If codeEdits=false: Generate Spec File
    ├─→ Create specs/ directory
    ├─→ Generate markdown specification
    ├─→ Emit spec_file_generated event (MCP namespace)
    └─→ Return spec file path
   ↓
9b. If codeEdits=true: Code Editor
    ├─→ Create git branch (feat/agent-{plan_id})
    ├─→ Apply code changes (AST-aware editing)
    ├─→ Validate code (linting, syntax)
    ├─→ Iterative fix on errors (if enabled)
    └─→ Generate diff
   ↓
10. Test Runner
    ├─→ Run unit tests
    ├─→ Run integration tests
    ├─→ Run e2e tests (if applicable)
    └─→ Test failure feedback loop (if enabled)
       ├─→ Extract failure messages
       ├─→ Fix code iteratively
       └─→ Re-run tests (max retries)
   ↓
11. Verifier
    ├─→ Compare test results to expectations
    ├─→ Verify acceptance criteria
    └─→ Determine PR readiness
   ↓
12. PR Creator (if verification passes)
    ├─→ Create git commit
    ├─→ Push branch to fork
    ├─→ Open pull request (to original repo)
    └─→ Generate PR description with summary
   ↓
13. Stream Summary to User
    ├─→ Final summary event
    ├─→ PR URL and details
    └─→ Complete workflow status
```

### Query Handling Flow

```
1. User Question
   ↓
2. Query Handler
   ├─→ Classify query type
   │   ├─→ Entry file query
   │   ├─→ App component query
   │   ├─→ Features query
   │   ├─→ Project summary query
   │   ├─→ Dependencies query
   │   ├─→ Module query
   │   ├─→ Endpoints query
   │   └─→ General question
   ↓
3. PKG Query Engine
   ├─→ Search PKG data
   ├─→ Query Neo4j (if available)
   └─→ Extract relevant modules/symbols
   ↓
4. Build Context
   ├─→ Module summaries
   ├─→ Symbol information
   └─→ Relationship context
   ↓
5. LLM Generation
   ├─→ Generate answer with context
   └─→ Include references
   ↓
6. Return Response
   ├─→ Natural language answer
   ├─→ References (modules, symbols, endpoints)
   └─→ Metadata (query type, mentioned entities)
```

### Diagram Generation Flow

```
1. User Request
   ↓
2. Diagram Generator
   ├─→ Parse customizations (theme, layout, etc.)
   └─→ Determine diagram type
   ↓
3. Check Cache (Neo4j)
   ├─→ If cached & not expired → Return cached
   └─→ If not → Continue
   ↓
4. PKG Query Engine
   ├─→ Query modules (by tag, path, or all)
   ├─→ Query relationships
   └─→ Apply filters (depth, node limits)
   ↓
5. Generate Mermaid Code
   ├─→ Build graph structure
   ├─→ Apply customizations
   └─→ Optimize layout
   ↓
6. Render (if image requested)
   ├─→ Option 1: Playwright (local)
   ├─→ Option 2: mermaid.ink API (remote)
   └─→ Option 3: Return Mermaid code only
   ↓
7. Cache Result (Neo4j)
   ↓
8. Return Diagram
   ├─→ Mermaid code
   ├─→ Image (base64 or URL)
   └─→ Interactive HTML (optional)
```

## Additional Capabilities

### Code Editing Features

**AST-Aware Editing:**
- Uses `libcst` for Python AST transformations
- Preserves code formatting and structure
- Safer than text-based replacements

**Iterative Fixing:**
- Automatically fixes linting errors (if `AUTO_FIX_LINT=true`)
- Fixes code based on test failure messages (if `FIX_ON_TEST_FAILURE=true`)
- Maximum retry attempts configurable (`MAX_FIX_RETRIES`)
- Includes code examples from PKG in LLM prompts

**File Validation:**
- Validates file existence before planning
- Fuzzy file matching with confidence threshold
- Suggests similar files when exact match not found
- Streams validation results to client

**Code Validation:**
- Syntax validation after edits
- Linting with auto-fix support
- Type checking (where applicable)
- Error reporting with line numbers

### Repository Management

**Auto-Forking:**
- Automatically detects if repository is owned by authenticated user
- Forks repository if needed (requires GitHub token)
- Configures git remotes (origin=fork, upstream=original)
- Stores fork information in session

**Caching Strategy:**
1. **Session Cache**: PKG data stored in memory per session
2. **Neo4j Cache**: Persistent storage with versioning
3. **File Cache**: `pkg.json` with git SHA validation
4. **Priority**: Session → Neo4j → File Cache → Regenerate

### Spec File Generation

When `CODE_EDITS_ENABLED=false`, the system generates markdown specification files instead of editing code:

- Creates `specs/` directory in repository
- Generates detailed change specifications
- Includes task breakdown, file changes, test requirements
- Emits MCP events for external tooling integration
- Returns spec file path for review

### MCP (Model Context Protocol) Integration

- Separate WebSocket namespace (`/mcp`)
- Spec file generation notifications
- Integration with external MCP-compatible tools
- Event-driven architecture for tooling workflows

## Project Structure

```
py-processor/
├── app.py                      # Main Flask application
├── requirements.txt             # Python dependencies
├── project-schema.json          # PKG schema definition
├── env.example                  # Environment variable template
│
├── agents/                      # AI Agent Components
│   ├── intent_router.py         # Intent extraction and routing
│   ├── query_handler.py         # Query answering with LLM
│   ├── impact_analyzer.py       # Impact assessment and risk analysis
│   ├── planner.py               # Plan generation with file validation
│   ├── code_editor.py           # Code editing with AST-aware transformations
│   ├── code_validator.py        # Code validation and linting
│   ├── code_context_analyzer.py # Context analysis for code changes
│   ├── test_runner.py           # Test execution with feedback loops
│   ├── verifier.py              # Change verification and acceptance
│   ├── pr_creator.py            # PR creation with auto-forking
│   ├── diagram_generator.py     # Diagram generation (Mermaid)
│   ├── extraction_agent.py     # Data extraction (LangChain)
│   ├── storing_agent.py         # Data storage (LangChain + Qdrant)
│   ├── chunking_agent.py        # Document chunking (LangChain)
│   └── ast_transformers.py     # AST transformation utilities
│
├── code_parser/                 # Code Parsing
│   ├── multi_parser.py          # Multi-language parser
│   ├── multi_normalizer.py      # Normalization
│   ├── parser.py                # Language-specific parsers
│   ├── normalizer.py            # Definition extraction
│   ├── framework_detector.py    # Framework detection
│   ├── endpoint_extractors.py   # Endpoint extraction
│   ├── relationship_extractor.py # Relationship mapping
│   └── project_metadata.py      # Project metadata
│
├── db/                          # Database Layer
│   ├── neo4j_db.py              # Neo4j operations
│   └── neo4j_query_engine.py    # Neo4j query engine
│
├── services/                    # Business Logic
│   ├── agent_orchestrator.py    # Agent workflow orchestration
│   ├── pdf_service.py           # PDF processing
│   ├── parser_service.py        # Parser service
│   ├── pkg_generator.py         # PKG generation
│   ├── pkg_query_engine.py      # PKG querying
│   └── summary_generator.py     # Summary generation
│
├── routes/                      # API Routes
│   ├── pdf_routes.py            # PDF processing endpoints
│   ├── chat_routes.py           # WebSocket chat routes
│   ├── cleanup_routes.py        # Cleanup and resource management
│   └── mcp_routes.py            # MCP (Model Context Protocol) routes
│
├── utils/                       # Utilities
│   ├── config.py                # Centralized configuration management
│   ├── file_utils.py            # File operations and collection
│   ├── response_formatter.py    # Response formatting
│   ├── schema_validator.py      # Schema validation
│   └── logging_config.py        # Logging configuration
│
├── processors/                  # Data Processors
│   └── qdrant.py                # Qdrant vector store (optional)
│
├── cloned_repos/                # Cloned repositories cache
└── output/                      # Output files
```

## Configuration

### Environment Variables

See `env.example` for complete configuration options.

**Key Variables:**
- `OPENAI_API_KEY`: Required for agent features
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`: Required for Neo4j features
- `GITHUB_TOKEN`: Required for PR creation
- `LLM_MODEL`: LLM model to use (default: `gpt-4`)
- `AGENT_APPROVAL_REQUIRED`: Require human approval for changes (default: `true`)

### Feature Flags

- `PKG_CACHE_ENABLED`: Enable PKG file caching (default: `true`)
- `USE_DOCKER_FOR_TESTS`: Use Docker for test execution (default: `false`)
- `AGENT_AUTO_APPLY_LOW_RISK`: Auto-apply low-risk changes (default: `false`)
- `CODE_EDITS_ENABLED`: Enable actual code edits vs spec generation (default: `false`)
- `USE_AST_EDITING`: Use AST-aware code editing (default: `true`)
- `FUZZY_FILE_MATCHING_ENABLED`: Enable fuzzy file matching (default: `true`)
- `AUTO_FIX_LINT`: Automatically fix linting errors (default: `true`)
- `FIX_ON_TEST_FAILURE`: Automatically fix code when tests fail (default: `true`)
- `PKG_INCLUDE_FEATURES`: Include feature groupings in PKG (default: `true`)

## Development

### Code Standards

- Type hints in all function definitions
- Docstrings for all functions and classes
- Logging instead of print statements
- Error handling with meaningful messages

### Running Tests

```bash
pytest test_app.py -v
```

### Formatting Code

```bash
black .
```

## Nice-to-Haves & Future Enhancements

### Planned Features

1. **Cross-Repository Queries**
   - Query across multiple repositories
   - Compare codebases
   - Find similar patterns

2. **Advanced Impact Analysis**
   - Semantic impact analysis using embeddings
   - Dependency chain visualization
   - Risk prediction models

3. **Enhanced Diagram Features**
   - 3D architecture visualizations
   - Interactive dependency exploration
   - Real-time diagram updates

4. **Performance Optimizations**
   - Incremental PKG updates
   - Parallel parsing
   - Smart caching strategies

5. **Additional Language Support**
   - Go, Rust, Ruby, PHP
   - Configuration languages (YAML, TOML)
   - Infrastructure as Code (Terraform, CloudFormation)

6. **CI/CD Integration**
   - GitHub Actions integration
   - Automated PR reviews
   - Pre-commit hooks

7. **Security Scanning**
   - Vulnerability detection
   - Security best practices checking
   - Dependency vulnerability scanning

8. **Code Quality Metrics**
   - Code complexity analysis
   - Technical debt estimation
   - Refactoring suggestions

9. **Collaboration Features**
   - Multi-user sessions
   - Shared workspaces
   - Team approvals

10. **Advanced Agent Capabilities**
    - Multi-step reasoning
    - Context-aware planning
    - Learning from feedback

## Performance Considerations

- **OCR**: Enabling OCR significantly increases processing time but enables scanned document support
- **PKG Generation**: Large repositories may take several minutes to parse; caching with git SHA validation helps avoid regeneration
- **Neo4j**: Batch operations (configurable batch size) are used for efficient storage of large codebases
- **Diagram Rendering**: Playwright rendering is faster but requires local installation; mermaid.ink API is alternative
- **Agent Operations**: Complex changes may take several minutes; real-time streaming keeps users informed
- **Session Caching**: PKG data cached in session memory for faster subsequent queries
- **File Cache**: PKG JSON files cached on disk with git SHA validation
- **Neo4j Caching**: Diagram and query results cached in Neo4j with TTL
- **Iterative Fixing**: Code fixes may require multiple iterations; max retries configurable

## Error Handling

The application uses consistent error responses:

```json
{
  "status": "error",
  "message": "Error description",
  "code": "ERROR_CODE"
}
```

**Common Error Codes:**
- `400`: Bad Request
- `404`: Not Found
- `413`: Request Entity Too Large
- `500`: Internal Server Error
- `503`: Service Unavailable (Neo4j connection issues)

## License

This project is part of a document processing and code analysis system.

## Contributing

Contributions are welcome! Please ensure:
- Code follows project standards
- Tests are included for new features
- Documentation is updated
- Type hints are used throughout

## Support

For issues, questions, or contributions, please refer to the project repository.
