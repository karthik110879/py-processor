"""Query Handler - Answers informational questions using PKG data."""

import logging
import os
import re
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI

from services.pkg_query_engine import PKGQueryEngine
from utils.config import Config

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
            config = Config()
            api_key = config.openai_api_key
            
            if not api_key:
                logger.warning("OPENAI_API_KEY not set in config, query responses will be limited")
                return
            
            self.llm = ChatOpenAI(
                model=config.llm_model,
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
                openai_api_key=api_key
            )
            logger.info(f"LLM initialized successfully | Model: {config.llm_model}")
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
        # Check for entry file queries first
        if any(keyword in message_lower for keyword in ['entry file', 'entry point', 'main file', 'startup file', 'what is the entry', 'where is main']):
            answer = self._answer_entry_file_question(user_message)
            entry_modules = self.query_engine.get_entry_point_modules()
            references = [{"type": "module", "id": m.get('id', ''), "name": m.get('path', '')} for m in entry_modules]
        # Check for app component queries
        elif any(keyword in message_lower for keyword in ['app component', 'root component', 'main component', 'what is the app component', 'where is app component']):
            answer = self._answer_app_component_question(user_message)
            component_modules = self.query_engine.get_app_component_modules()
            references = [{"type": "module", "id": m.get('id', ''), "name": m.get('path', '')} for m in component_modules]
        # Check for features queries
        elif any(keyword in message_lower for keyword in ['what are the features', 'what features', 'list features', 'features']):
            answer = self._answer_features_question(user_message)
            features = self.pkg_data.get('features', [])
            references = []
            for feature in features:
                module_ids = feature.get('moduleIds', [])
                for module_id in module_ids[:5]:  # Limit references per feature
                    module = self.query_engine.get_module_by_id(module_id)
                    if module:
                        references.append({"type": "module", "id": module_id, "name": module.get('path', '')})
        # Check for project summary queries
        elif any(keyword in message_lower for keyword in ['what is this project', 'project about', 'project summary', 'describe project']):
            answer = self._generate_project_summary()
            references = self._get_project_references()
        # Check for dependencies queries
        elif any(keyword in message_lower for keyword in ['dependencies', 'depends on', 'what does it import']):
            module_id = self._extract_module_from_query(user_message)
            answer = self._list_dependencies(module_id)
            references = self._get_dependency_references(module_id)
        # Check for module queries
        elif any(keyword in message_lower for keyword in ['explain module', 'what is module', 'describe module', 'module']):
            module_id = self._extract_module_from_query(user_message)
            if module_id:
                answer = self._explain_module(module_id)
                references = self._get_module_references(module_id)
            else:
                answer = self._list_modules()
                references = []
        # Check for list modules queries
        elif any(keyword in message_lower for keyword in ['list modules', 'what modules', 'all modules', 'modules']):
            answer = self._list_modules()
            references = []
        # Check for endpoints queries
        elif any(keyword in message_lower for keyword in ['endpoints', 'api', 'routes']):
            answer = self._list_endpoints()
            references = self._get_endpoint_references()
        # Default to general question handler
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
    
    def _answer_entry_file_question(self, question: str) -> str:
        """Answer questions about entry files."""
        entry_modules = self.query_engine.get_entry_point_modules()
        
        if not entry_modules:
            return "No entry point files found in this project. Entry points are typically files like main.ts, index.ts, app.py, or main.py that serve as the application's starting point."
        
        if self.llm:
            context = self._build_entry_file_context()
            prompt = f"""You are a helpful assistant answering questions about a codebase. The user is asking about entry files.

{context}

User question: {question}

Provide a clear, detailed answer about the entry files in this project. Identify which file is the main entry point and explain its purpose."""
            
            try:
                response = self.llm.invoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                logger.error(f"Error answering entry file question: {e}", exc_info=True)
        
        # Fallback to structured response
        response = f"Found {len(entry_modules)} entry point file(s):\n\n"
        for module in entry_modules:
            path = module.get('path', '')
            summary = module.get('moduleSummary', '')
            response += f"- {path}\n"
            if summary:
                response += f"  {summary}\n"
        return response
    
    def _answer_app_component_question(self, question: str) -> str:
        """Answer questions about app components."""
        component_modules = self.query_engine.get_app_component_modules()
        
        if not component_modules:
            return "No app component files found in this project. App components are typically files like app.component.ts, App.tsx, or App.jsx that serve as the root component of the application."
        
        if self.llm:
            context = self._build_app_component_context()
            prompt = f"""You are a helpful assistant answering questions about a codebase. The user is asking about app components.

{context}

User question: {question}

Provide a clear, detailed answer about the app component(s) in this project. Identify the main/root component and explain its structure and purpose."""
            
            try:
                response = self.llm.invoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                logger.error(f"Error answering app component question: {e}", exc_info=True)
        
        # Fallback to structured response
        response = f"Found {len(component_modules)} app component file(s):\n\n"
        for module in component_modules:
            path = module.get('path', '')
            summary = module.get('moduleSummary', '')
            exports = module.get('exports', [])
            response += f"- {path}\n"
            if summary:
                response += f"  {summary}\n"
            if exports:
                response += f"  Exports {len(exports)} symbols\n"
        return response
    
    def _answer_features_question(self, question: str) -> str:
        """Answer questions about features."""
        features = self.pkg_data.get('features', [])
        
        if not features:
            return "No features found in this project. Features are typically organized areas of functionality in the codebase."
        
        if self.llm:
            context = self._build_features_context()
            prompt = f"""You are a helpful assistant answering questions about a codebase. The user is asking about features.

{context}

User question: {question}

Provide a clear, detailed answer about the features in this project. List and describe each feature area and what functionality it provides."""
            
            try:
                response = self.llm.invoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                logger.error(f"Error answering features question: {e}", exc_info=True)
        
        # Fallback to structured response
        response = f"Found {len(features)} feature(s):\n\n"
        for feature in features:
            name = feature.get('name', 'Unknown')
            path = feature.get('path', '')
            module_ids = feature.get('moduleIds', [])
            response += f"- {name}"
            if path:
                response += f" ({path})"
            response += f" - {len(module_ids)} modules\n"
        return response
    
    def _generate_project_summary(self) -> str:
        """Generate a comprehensive project summary using LLM with full project context."""
        project = self.pkg_data.get('project', {})
        modules = self.pkg_data.get('modules', [])
        endpoints = self.pkg_data.get('endpoints', [])
        features = self.pkg_data.get('features', [])
        edges = self.pkg_data.get('edges', [])
        
        # Try LLM-powered generation if available
        if self.llm:
            try:
                logger.info("Generating project summary using LLM")
                context = self._build_full_project_context()
                
                prompt = f"""You are a helpful assistant generating comprehensive project summaries. Based on the following project information, create a detailed 4-6 sentence summary covering:

1. Project purpose and primary function
2. Technology stack and programming languages used
3. Module structure and organization
4. Feature areas and their roles
5. Entry points and startup flow
6. API endpoints (if present)
7. Key architectural components

Project Information:
{context}

Generate a comprehensive, descriptive summary that provides a clear overview of this project. Write in a natural, flowing style that connects these aspects together."""
                
                response = self.llm.invoke(prompt)
                summary = response.content if hasattr(response, 'content') else str(response)
                logger.info("Successfully generated project summary using LLM")
                return summary
            except Exception as e:
                logger.error(f"Error generating project summary with LLM: {e}", exc_info=True)
                logger.info("Falling back to structured response")
        
        # Enhanced fallback response when LLM is unavailable
        project_name = project.get('name', 'Unknown')
        languages = project.get('languages', [])
        module_count = len(modules)
        feature_count = len(features)
        endpoint_count = len(endpoints)
        dependency_count = len([e for e in edges if e.get('type') == 'imports'])
        
        # Get entry point modules
        entry_modules = self.query_engine.get_entry_point_modules()
        
        # Build structured fallback response
        response_parts = []
        
        # Project overview
        response_parts.append(f"Project: {project_name}")
        
        # Technology stack
        if languages:
            response_parts.append(f"Technology Stack: {', '.join(languages)}")
        
        response_parts.append("")  # Empty line for spacing
        
        # Main description
        main_desc = f"This project contains {module_count} modules"
        if feature_count > 0:
            feature_names = [f.get('name', 'Unknown') for f in features]
            main_desc += f" organized into {feature_count} feature area(s): {', '.join(feature_names)}"
        main_desc += "."
        response_parts.append(main_desc)
        response_parts.append("")  # Empty line for spacing
        
        # Entry points section
        if entry_modules:
            response_parts.append("Entry Points:")
            for module in entry_modules:
                path = module.get('path', '')
                summary = module.get('moduleSummary', '')
                response_parts.append(f"  - {path}")
                if summary:
                    response_parts.append(f"    {summary}")
            response_parts.append("")  # Empty line for spacing
        
        # Dependency statistics
        if dependency_count > 0:
            response_parts.append(f"The project has {dependency_count} dependency relationships between modules.")
            response_parts.append("")  # Empty line for spacing
        
        # API endpoints section
        if endpoint_count > 0:
            response_parts.append(f"API Endpoints: {endpoint_count} endpoint(s) available")
            # List a few key endpoints
            by_method = {}
            for endpoint in endpoints[:10]:  # Limit to first 10
                method = endpoint.get('method', 'UNKNOWN')
                if method not in by_method:
                    by_method[method] = []
                by_method[method].append(endpoint)
            
            for method, eps in sorted(by_method.items()):
                response_parts.append(f"  {method}:")
                for endpoint in eps[:5]:  # Limit to 5 per method
                    path = endpoint.get('path', 'unknown')
                    summary = endpoint.get('summary', '')
                    endpoint_line = f"    - {path}"
                    if summary:
                        endpoint_line += f" ({summary})"
                    response_parts.append(endpoint_line)
        
        return "\n".join(response_parts)
    
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
    
    def _build_entry_file_context(self) -> str:
        """Build context for entry file queries."""
        entry_modules = self.query_engine.get_entry_point_modules()
        
        if not entry_modules:
            return "No entry point files found (main.ts, index.ts, app.py, etc.)."
        
        context = f"Entry Point Files ({len(entry_modules)}):\n"
        for module in entry_modules:
            path = module.get('path', '')
            kinds = module.get('kind', [])
            summary = module.get('moduleSummary', '')
            exports = module.get('exports', [])
            
            context += f"\n- {path}"
            if kinds:
                context += f" ({', '.join(kinds)})"
            if summary:
                context += f"\n  Summary: {summary}"
            if exports:
                context += f"\n  Exports: {len(exports)} symbols"
        
        return context
    
    def _build_app_component_context(self) -> str:
        """Build context for app component queries."""
        component_modules = self.query_engine.get_app_component_modules()
        
        if not component_modules:
            return "No app component files found (app.component.ts, App.tsx, etc.)."
        
        context = f"App Component Files ({len(component_modules)}):\n"
        for module in component_modules:
            path = module.get('path', '')
            kinds = module.get('kind', [])
            summary = module.get('moduleSummary', '')
            exports = module.get('exports', [])
            
            context += f"\n- {path}"
            if kinds:
                context += f" ({', '.join(kinds)})"
            if summary:
                context += f"\n  Summary: {summary}"
            if exports:
                context += f"\n  Exports: {len(exports)} symbols"
                # List key exports
                for export_id in exports[:5]:
                    symbol = self.query_engine.get_symbol_by_id(export_id)
                    if symbol:
                        context += f"\n    - {symbol.get('kind', '')} {symbol.get('name', '')}"
        
        return context
    
    def _build_features_context(self) -> str:
        """Build context for features queries."""
        features = self.pkg_data.get('features', [])
        
        if not features:
            return "No features found in the project."
        
        context = f"Features ({len(features)}):\n"
        for feature in features:
            name = feature.get('name', 'Unknown')
            path = feature.get('path', '')
            module_ids = feature.get('moduleIds', [])
            
            context += f"\n- {name}"
            if path:
                context += f" ({path})"
            context += f"\n  Modules: {len(module_ids)}"
            
            # List key modules in this feature
            for module_id in module_ids[:5]:
                module = self.query_engine.get_module_by_id(module_id)
                if module:
                    context += f"\n    - {module.get('path', module_id)}"
            if len(module_ids) > 5:
                context += f"\n    ... and {len(module_ids) - 5} more"
        
        return context
    
    def _build_version_context(self) -> str:
        """Build context for version-related queries."""
        project = self.pkg_data.get('project', {})
        metadata = project.get('metadata', {})
        
        context_parts = []
        
        # Framework versions
        framework_versions = metadata.get('frameworkVersions', {})
        if framework_versions:
            context_parts.append("Framework Versions:")
            for framework, info in framework_versions.items():
                # Prefer exactVersion if available, otherwise use version
                exact_version = info.get('exactVersion')
                version = exact_version if exact_version else info.get('version', info.get('versionSpec', 'unknown'))
                package = info.get('package', '')
                version_note = " (exact)" if exact_version else ""
                context_parts.append(f"  - {framework.capitalize()}: {version}{version_note} (package: {package})")
        
        # Language/runtime versions
        if metadata.get('nodeVersion'):
            context_parts.append(f"\nNode.js Version: {metadata['nodeVersion']}")
        
        if metadata.get('pythonVersion'):
            context_parts.append(f"Python Version: {metadata['pythonVersion']}")
        
        if metadata.get('javaVersion'):
            context_parts.append(f"Java Version: {metadata['javaVersion']}")
        
        if metadata.get('typescriptVersion'):
            context_parts.append(f"TypeScript Version: {metadata['typescriptVersion']}")
        
        # Build tool versions
        build_tool_versions = metadata.get('buildToolVersions', {})
        if build_tool_versions:
            context_parts.append("\nBuild Tool Versions:")
            for tool, version in build_tool_versions.items():
                context_parts.append(f"  - {tool}: {version}")
        
        # Frameworks list (for reference)
        frameworks = project.get('frameworks', [])
        if frameworks:
            context_parts.append(f"\nDetected Frameworks: {', '.join(frameworks)}")
        
        return "\n".join(context_parts) if context_parts else "No version information available."
    
    def _build_config_context(self) -> str:
        """Build context for configuration-related queries."""
        project = self.pkg_data.get('project', {})
        metadata = project.get('metadata', {})
        configs = metadata.get('configurations', {})
        
        if not configs:
            return "No configuration file details available."
        
        context_parts = []
        
        # Angular configuration
        angular_config = configs.get('angular')
        if angular_config:
            context_parts.append("Angular Configuration:")
            if angular_config.get('version'):
                context_parts.append(f"  Angular CLI Version: {angular_config['version']}")
            if angular_config.get('projects'):
                context_parts.append(f"  Projects: {', '.join(angular_config['projects'])}")
            if angular_config.get('architect'):
                context_parts.append(f"  Architect Targets: {', '.join(angular_config['architect'])}")
        
        # TypeScript configuration
        tsconfig = configs.get('typescript')
        if tsconfig:
            context_parts.append("\nTypeScript Configuration:")
            if tsconfig.get('target'):
                context_parts.append(f"  Target: {tsconfig['target']}")
            if tsconfig.get('module'):
                context_parts.append(f"  Module: {tsconfig['module']}")
            if tsconfig.get('strict'):
                context_parts.append(f"  Strict Mode: {tsconfig['strict']}")
        
        # Python packages
        python_packages = configs.get('pythonPackages')
        if python_packages:
            context_parts.append("\nPython Packages (from requirements.txt):")
            for pkg in python_packages[:10]:  # Limit to first 10
                pkg_name = pkg.get('package', '')
                version = pkg.get('version', '')
                constraint = pkg.get('constraint', '')
                if version:
                    context_parts.append(f"  - {pkg_name} {constraint}{version}")
                else:
                    context_parts.append(f"  - {pkg_name}")
        
        # Maven configuration
        maven_config = configs.get('maven')
        if maven_config:
            context_parts.append("\nMaven Configuration:")
            if maven_config.get('javaVersion'):
                context_parts.append(f"  Java Version: {maven_config['javaVersion']}")
            if maven_config.get('projectVersion'):
                context_parts.append(f"  Project Version: {maven_config['projectVersion']}")
        
        return "\n".join(context_parts)
    
    def _build_full_project_context(self) -> str:
        """Build comprehensive project context for general questions."""
        project = self.pkg_data.get('project', {})
        modules = self.pkg_data.get('modules', [])
        endpoints = self.pkg_data.get('endpoints', [])
        edges = self.pkg_data.get('edges', [])
        features = self.pkg_data.get('features', [])
        summaries = self.pkg_data.get('summaries', {})
        
        context = f"""Project: {project.get('name', 'Unknown')}
Languages: {', '.join(project.get('languages', []))}
Total Modules: {len(modules)}
Total Endpoints: {len(endpoints)}
Total Dependencies: {len([e for e in edges if e.get('type') == 'imports'])}
Total Features: {len(features)}
"""
        
        # Add version information
        version_context = self._build_version_context()
        if version_context and version_context != "No version information available.":
            context += f"\n{version_context}\n"
        
        # Add project summary if available
        if summaries.get('projectSummary'):
            context += f"\nProject Summary: {summaries['projectSummary']}\n"
        
        # Add entry points
        entry_modules = self.query_engine.get_entry_point_modules()
        if entry_modules:
            context += f"\nEntry Points ({len(entry_modules)}):\n"
            for module in entry_modules[:5]:
                context += f"  - {module.get('path', '')}\n"
        
        # Add app components
        component_modules = self.query_engine.get_app_component_modules()
        if component_modules:
            context += f"\nApp Components ({len(component_modules)}):\n"
            for module in component_modules[:5]:
                context += f"  - {module.get('path', '')}\n"
        
        # Add features summary
        if features:
            context += f"\nFeatures ({len(features)}):\n"
            for feature in features[:10]:
                name = feature.get('name', 'Unknown')
                module_count = len(feature.get('moduleIds', []))
                context += f"  - {name} ({module_count} modules)\n"
        
        # Smart module selection: prioritize important modules
        prioritized_modules = []
        
        # 1. Entry points
        prioritized_modules.extend(entry_modules)
        
        # 2. App components
        prioritized_modules.extend(component_modules)
        
        # 3. High-impact modules (high fan-in/fan-out)
        module_impact = {}
        for edge in edges:
            if edge.get('type') == 'imports':
                from_id = self.query_engine._extract_module_id(edge.get('from', ''))
                to_id = self.query_engine._extract_module_id(edge.get('to', ''))
                if from_id:
                    module_impact[from_id] = module_impact.get(from_id, 0) + 1
                if to_id:
                    module_impact[to_id] = module_impact.get(to_id, 0) + 1
        
        # Sort by impact
        high_impact_modules = sorted(
            [(mid, count) for mid, count in module_impact.items() if count > 3],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        for module_id, _ in high_impact_modules:
            module = self.query_engine.get_module_by_id(module_id)
            if module and module not in prioritized_modules:
                prioritized_modules.append(module)
        
        # 4. Feature modules
        feature_module_ids = set()
        for feature in features:
            feature_module_ids.update(feature.get('moduleIds', []))
        
        for module_id in list(feature_module_ids)[:10]:
            module = self.query_engine.get_module_by_id(module_id)
            if module and module not in prioritized_modules:
                prioritized_modules.append(module)
        
        # 5. Top modules by exports
        modules_by_exports = sorted(
            modules,
            key=lambda m: len(m.get('exports', [])),
            reverse=True
        )
        
        for module in modules_by_exports:
            if module not in prioritized_modules and len(prioritized_modules) < 30:
                prioritized_modules.append(module)
        
        # Add prioritized modules to context
        if prioritized_modules:
            context += f"\nKey Modules ({len(prioritized_modules)}):\n"
            for module in prioritized_modules[:30]:
                path = module.get('path', '')
                kinds = module.get('kind', [])
                summary = module.get('moduleSummary', '')
                exports = module.get('exports', [])
                
                context += f"  - {path}"
                if kinds:
                    context += f" ({', '.join(kinds)})"
                if summary:
                    context += f" - {summary[:100]}"
                elif exports:
                    context += f" ({len(exports)} exports)"
                context += "\n"
        
        return context
    
    def _answer_general_question(self, question: str) -> str:
        """Answer a general question using LLM with full PKG context."""
        if not self.llm:
            return "I can answer questions about the project structure, but LLM is not available for detailed analysis."
        
        # Build comprehensive context using full PKG data
        context = self._build_full_project_context()
        
        # Check if question is about specific topics and add specialized context
        question_lower = question.lower()
        
        if any(keyword in question_lower for keyword in ['entry', 'main file', 'startup', 'entry point', 'entry file']):
            context += "\n\n" + self._build_entry_file_context()
        
        if any(keyword in question_lower for keyword in ['app component', 'root component', 'main component']):
            context += "\n\n" + self._build_app_component_context()
        
        if any(keyword in question_lower for keyword in ['features', 'feature', 'what features']):
            context += "\n\n" + self._build_features_context()
        
        # Add version context for version-related questions
        version_keywords = ['version', 'what version', 'which version', 'v.', 'ver.']
        if any(keyword in question_lower for keyword in version_keywords):
            version_context = self._build_version_context()
            if version_context and version_context != "No version information available.":
                context += "\n\n=== VERSION INFORMATION ===\n" + version_context
        
        # Add config context for configuration-related questions
        config_keywords = ['config', 'configuration', 'tsconfig', 'angular.json', 'package.json', 'requirements.txt', 'pom.xml']
        if any(keyword in question_lower for keyword in config_keywords):
            config_context = self._build_config_context()
            if config_context and config_context != "No configuration file details available.":
                context += "\n\n=== CONFIGURATION DETAILS ===\n" + config_context
        
        prompt = f"""You are a helpful assistant answering questions about a codebase. Use the following comprehensive project information to answer the user's question.

{context}

User question: {question}

Provide a clear, concise, and accurate answer based on the complete project structure and knowledge graph. 
- If asked about entry files, identify and describe the main entry point files
- If asked about app components, identify and describe the root/app component files
- If asked about features, list and describe the feature areas
- If asked about versions (e.g., "what version of Angular?"), provide the specific version information from the metadata
- If asked about configurations, provide details from the configuration files
- Use the module summaries and exports information when relevant
- The version information section contains framework versions, language versions, and build tool versions
- If the question cannot be answered from the available information, say so explicitly."""
        
        try:
            response = self.llm.invoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Error answering general question: {e}", exc_info=True)
            return f"I encountered an error while processing your question. Please try rephrasing it or ask about specific modules or dependencies."
    
    def _find_modules_by_filename(self, filename: str) -> List[Dict[str, Any]]:
        """Find modules by filename (handles both exact and partial matches)."""
        return self.query_engine.get_modules_by_filename(filename)
    
    def _extract_module_from_query(self, query: str) -> Optional[str]:
        """Try to extract module ID or path from query."""
        # First, try to find mod: pattern
        mod_match = re.search(r'mod:([^\s]+)', query)
        if mod_match:
            return mod_match.group(0)
        
        # Try to extract filename from query
        path_match = re.search(r'([a-zA-Z0-9_/\\\-\.]+\.(py|ts|js|tsx|jsx|java|cs|cpp|c))', query)
        if path_match:
            path = path_match.group(1)
            filename = os.path.basename(path)
            
            # First try file-by-name search
            matches = self._find_modules_by_filename(filename)
            if matches:
                # Prefer exact matches
                for match in matches:
                    if match.get('path', '').endswith(path) or os.path.basename(match.get('path', '')) == filename:
                        return match.get('id')
                # Return first match if no exact match
                return matches[0].get('id')
            
            # Fallback to path pattern matching
            matching_modules = self.query_engine.get_modules_by_path_pattern(f"*{path}*")
            if matching_modules:
                return matching_modules[0].get('id')
            
            # Last resort: check all modules for path inclusion
            for module in self.pkg_data.get('modules', []):
                module_path = module.get('path', '')
                if path in module_path or module_path.endswith(path):
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
