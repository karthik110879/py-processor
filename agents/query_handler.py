"""Query Handler - Answers informational questions using PKG data."""

import logging
import os
import re
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI

from services.pkg_query_engine import PKGQueryEngine

logger = logging.getLogger(__name__)


class QueryHandler:
    """Handles informational queries about the project using PKG data."""
    
    def __init__(self, pkg_data: Dict[str, Any], pkg_query_engine: Optional[PKGQueryEngine] = None, neo4j_query_engine=None):
        """
        Initialize query handler.
        
        Args:
            pkg_data: Complete PKG dictionary
            pkg_query_engine: Optional PKGQueryEngine instance (will create if not provided)
            neo4j_query_engine: Optional Neo4jQueryEngine instance for cross-repository queries
        """
        self.pkg_data = pkg_data
        self.neo4j_query_engine = neo4j_query_engine
        
        # Initialize PKGQueryEngine with Neo4j backend if available
        if pkg_query_engine:
            self.query_engine = pkg_query_engine
            # Update the existing engine's neo4j_engine if not already set
            if neo4j_query_engine and not self.query_engine.neo4j_engine:
                self.query_engine.neo4j_engine = neo4j_query_engine
        else:
            self.query_engine = PKGQueryEngine(pkg_data, neo4j_engine=neo4j_query_engine)
        
        self.llm = None
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize LLM for generating natural language responses."""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set, query responses will be limited")
                return
            
            model = os.getenv("LLM_MODEL", "gpt-4")
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
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
    
    def answer_query(self, user_message: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Answer an informational query about the project.
        
        Args:
            user_message: User's question
            intent: Extracted intent dictionary
            
        Returns:
            Dictionary with answer, references, and metadata
        """
        message_lower = user_message.lower()
        
        # Route to appropriate handler based on query type
        if any(keyword in message_lower for keyword in ['what is this project', 'project about', 'project summary', 'describe project']):
            answer = self._generate_project_summary()
            references = self._get_project_references()
        elif any(keyword in message_lower for keyword in ['dependencies', 'depends on', 'what does it import']):
            module_id = self._extract_module_from_query(user_message)
            answer = self._list_dependencies(module_id)
            references = self._get_dependency_references(module_id)
        elif any(keyword in message_lower for keyword in ['explain module', 'what is module', 'describe module', 'module']):
            module_id = self._extract_module_from_query(user_message)
            if module_id:
                answer = self._explain_module(module_id)
                references = self._get_module_references(module_id)
            else:
                answer = self._list_modules()
                references = []
        elif any(keyword in message_lower for keyword in ['list modules', 'what modules', 'all modules', 'modules']):
            answer = self._list_modules()
            references = []
        elif any(keyword in message_lower for keyword in ['endpoints', 'api', 'routes']):
            answer = self._list_endpoints()
            references = self._get_endpoint_references()
        else:
            answer = self._answer_general_question(user_message)
            references = self._extract_references_from_answer(answer, user_message)
        
        return {
            "answer": answer,
            "references": references,
            "metadata": {
                "modules_mentioned": self._extract_module_ids_from_references(references),
                "endpoints_mentioned": self._extract_endpoint_ids_from_references(references),
                "query_type": self._classify_query_type(user_message)
            }
        }
    
    def _generate_project_summary(self) -> str:
        """Generate a project summary."""
        project = self.pkg_data.get('project', {})
        modules = self.pkg_data.get('modules', [])
        summaries = self.pkg_data.get('summaries', {})
        
        if summaries.get('projectSummary'):
            base_summary = summaries['projectSummary']
        else:
            base_summary = f"Project {project.get('name', 'Unknown')} with {len(modules)} modules"
        
        languages = project.get('languages', [])
        endpoints = self.pkg_data.get('endpoints', [])
        features = self.pkg_data.get('features', [])
        
        details = []
        if languages:
            details.append(f"written in {', '.join(languages)}")
        if endpoints:
            details.append(f"with {len(endpoints)} API endpoints")
        if features:
            details.append(f"organized into {len(features)} feature areas")
        
        if details:
            return f"{base_summary}. {', '.join(details)}."
        return base_summary
    
    def _list_dependencies(self, module_id: Optional[str] = None) -> str:
        """List dependencies for a module or the entire project."""
        if module_id:
            module = self.query_engine.get_module_by_id(module_id)
            if not module:
                return f"Module {module_id} not found."
            
            deps = self.query_engine.get_dependencies(module_id)
            callers = deps.get('callers', [])
            callees = deps.get('callees', [])
            
            response = f"Module {module.get('path', module_id)}:\n"
            if callees:
                response += f"\nDependencies ({len(callees)}):\n"
                for callee in callees[:10]:
                    response += f"  - {callee.get('path', callee.get('id', 'unknown'))}\n"
            if callers:
                response += f"\nUsed by ({len(callers)}):\n"
                for caller in callers[:10]:
                    response += f"  - {caller.get('path', caller.get('id', 'unknown'))}\n"
            
            return response
        else:
            modules = self.pkg_data.get('modules', [])
            edges = self.pkg_data.get('edges', [])
            import_edges = [e for e in edges if e.get('type') == 'imports']
            
            response = f"Project has {len(modules)} modules with {len(import_edges)} dependency relationships.\n"
            response += "\nTop modules by dependencies:\n"
            
            dep_counts = {}
            for edge in import_edges:
                from_id = edge.get('from', '')
                mod_id = self.query_engine._extract_module_id(from_id)
                if mod_id:
                    dep_counts[mod_id] = dep_counts.get(mod_id, 0) + 1
            
            sorted_modules = sorted(dep_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            for mod_id, count in sorted_modules:
                module = self.query_engine.get_module_by_id(mod_id)
                if module:
                    response += f"  - {module.get('path', mod_id)}: {count} dependencies\n"
            
            return response
    
    def _explain_module(self, module_id: str) -> str:
        """Explain what a module does."""
        module = self.query_engine.get_module_by_id(module_id)
        if not module:
            return f"Module {module_id} not found."
        
        path = module.get('path', module_id)
        kinds = module.get('kind', [])
        exports = module.get('exports', [])
        summary = module.get('moduleSummary')
        
        response = f"Module: {path}\n"
        if kinds:
            response += f"Type: {', '.join(kinds)}\n"
        if summary:
            response += f"\nSummary: {summary}\n"
        if exports:
            response += f"\nExports {len(exports)} symbols:\n"
            for export in exports[:10]:
                symbol_id = export if isinstance(export, str) else export.get('id', '')
                symbol = self.query_engine.get_symbol_by_id(symbol_id)
                if symbol:
                    name = symbol.get('name', 'unknown')
                    kind = symbol.get('kind', '')
                    response += f"  - {kind} {name}\n"
        
        deps = self.query_engine.get_dependencies(module_id)
        if deps.get('callees'):
            response += f"\nDepends on {len(deps['callees'])} modules"
        if deps.get('callers'):
            response += f"\nUsed by {len(deps['callers'])} modules"
        
        return response
    
    def _list_modules(self) -> str:
        """List all modules in the project."""
        modules = self.pkg_data.get('modules', [])
        if not modules:
            return "No modules found in the project."
        
        response = f"Project contains {len(modules)} modules:\n\n"
        by_kind = {}
        for module in modules:
            kinds = module.get('kind', [])
            kind = kinds[0] if kinds else 'other'
            if kind not in by_kind:
                by_kind[kind] = []
            by_kind[kind].append(module)
        
        for kind, mods in sorted(by_kind.items()):
            response += f"{kind.upper()} ({len(mods)}):\n"
            for module in mods[:20]:
                path = module.get('path', module.get('id', 'unknown'))
                response += f"  - {path}\n"
            if len(mods) > 20:
                response += f"  ... and {len(mods) - 20} more\n"
            response += "\n"
        
        return response
    
    def _list_endpoints(self) -> str:
        """List all API endpoints."""
        endpoints = self.pkg_data.get('endpoints', [])
        if not endpoints:
            return "No API endpoints found in the project."
        
        response = f"Project has {len(endpoints)} API endpoints:\n\n"
        by_method = {}
        for endpoint in endpoints:
            method = endpoint.get('method', 'UNKNOWN')
            if method not in by_method:
                by_method[method] = []
            by_method[method].append(endpoint)
        
        for method, eps in sorted(by_method.items()):
            response += f"{method}:\n"
            for endpoint in eps[:20]:
                path = endpoint.get('path', 'unknown')
                summary = endpoint.get('summary', '')
                response += f"  - {path}"
                if summary:
                    response += f" ({summary})"
                response += "\n"
            if len(eps) > 20:
                response += f"  ... and {len(eps) - 20} more\n"
            response += "\n"
        
        return response
    
    def _answer_general_question(self, question: str) -> str:
        """Answer a general question using LLM with PKG context."""
        if not self.llm:
            return "I can answer questions about the project structure, but LLM is not available for detailed analysis."
        
        project = self.pkg_data.get('project', {})
        modules = self.pkg_data.get('modules', [])
        endpoints = self.pkg_data.get('endpoints', [])
        edges = self.pkg_data.get('edges', [])
        
        context = f"""Project: {project.get('name', 'Unknown')}
Languages: {', '.join(project.get('languages', []))}
Modules: {len(modules)}
Endpoints: {len(endpoints)}
Dependencies: {len([e for e in edges if e.get('type') == 'imports'])}

Top modules:
"""
        for module in modules[:10]:
            path = module.get('path', '')
            kinds = module.get('kind', [])
            context += f"- {path} ({', '.join(kinds) if kinds else 'generic'})\n"
        
        prompt = f"""You are a helpful assistant answering questions about a codebase. Use the following project information to answer the user's question.

{context}

User question: {question}

Provide a clear, concise answer based on the project structure. If the question cannot be answered from the available information, say so."""
        
        try:
            response = self.llm.invoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Error answering general question: {e}", exc_info=True)
            return f"I encountered an error while processing your question. Please try rephrasing it or ask about specific modules or dependencies."
    
    def _extract_module_from_query(self, query: str) -> Optional[str]:
        """Try to extract module ID or path from query."""
        mod_match = re.search(r'mod:([^\s]+)', query)
        if mod_match:
            return mod_match.group(0)
        
        path_match = re.search(r'([a-zA-Z0-9_/\\]+\.(py|ts|js|tsx|jsx))', query)
        if path_match:
            path = path_match.group(1)
            for module in self.pkg_data.get('modules', []):
                if path in module.get('path', '') or module.get('path', '').endswith(path):
                    return module.get('id')
        
        return None
    
    def _get_project_references(self) -> List[Dict[str, Any]]:
        """Get references for project-level query."""
        project = self.pkg_data.get('project', {})
        return [{"type": "project", "id": project.get('id', ''), "name": project.get('name', '')}]
    
    def _get_dependency_references(self, module_id: Optional[str]) -> List[Dict[str, Any]]:
        """Get references for dependency query."""
        references = []
        if module_id:
            module = self.query_engine.get_module_by_id(module_id)
            if module:
                references.append({"type": "module", "id": module_id, "name": module.get('path', module_id)})
                deps = self.query_engine.get_dependencies(module_id)
                for dep_module in (deps.get('callees', []) + deps.get('callers', []))[:10]:
                    references.append({"type": "module", "id": dep_module.get('id', ''), "name": dep_module.get('path', '')})
        else:
            modules = self.pkg_data.get('modules', [])[:10]
            for module in modules:
                references.append({"type": "module", "id": module.get('id', ''), "name": module.get('path', '')})
        return references
    
    def _get_module_references(self, module_id: str) -> List[Dict[str, Any]]:
        """Get references for module query."""
        module = self.query_engine.get_module_by_id(module_id)
        if not module:
            return []
        
        references = [{"type": "module", "id": module_id, "name": module.get('path', module_id)}]
        exports = module.get('exports', [])
        for export_id in exports[:5]:
            symbol = self.query_engine.get_symbol_by_id(export_id)
            if symbol:
                references.append({"type": "symbol", "id": export_id, "name": symbol.get('name', '')})
        return references
    
    def _get_endpoint_references(self) -> List[Dict[str, Any]]:
        """Get references for endpoint query."""
        endpoints = self.pkg_data.get('endpoints', [])
        return [{"type": "endpoint", "id": endpoint.get('id', ''), "name": f"{endpoint.get('method', '')} {endpoint.get('path', '')}"} for endpoint in endpoints[:20]]
    
    def _extract_references_from_answer(self, answer: str, query: str) -> List[Dict[str, Any]]:
        """Extract module/symbol references mentioned in the answer."""
        references = []
        path_pattern = r'([a-zA-Z0-9_/\\]+\.(py|ts|js|tsx|jsx))'
        matches = re.findall(path_pattern, answer)
        
        for match in matches[:10]:
            path = match[0]
            for module in self.pkg_data.get('modules', []):
                if path in module.get('path', ''):
                    references.append({"type": "module", "id": module.get('id', ''), "name": module.get('path', '')})
                    break
        return references
    
    def _extract_module_ids_from_references(self, references: List[Dict[str, Any]]) -> List[str]:
        """Extract module IDs from references."""
        return [ref['id'] for ref in references if ref.get('type') == 'module']
    
    def _extract_endpoint_ids_from_references(self, references: List[Dict[str, Any]]) -> List[str]:
        """Extract endpoint IDs from references."""
        return [ref['id'] for ref in references if ref.get('type') == 'endpoint']
    
    def _classify_query_type(self, query: str) -> str:
        """Classify the type of query."""
        query_lower = query.lower()
        if 'project' in query_lower or 'about' in query_lower:
            return 'project_summary'
        elif 'dependencies' in query_lower or 'depends' in query_lower:
            return 'dependencies'
        elif 'module' in query_lower:
            return 'module_info'
        elif 'endpoint' in query_lower or 'api' in query_lower:
            return 'endpoints'
        else:
            return 'general'
