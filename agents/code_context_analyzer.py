"""Code Context Analyzer - Deep PKG analysis for code generation."""

import logging
from typing import Dict, Any, List, Set, Optional
from services.pkg_query_engine import PKGQueryEngine

logger = logging.getLogger(__name__)


class CodeContextAnalyzer:
    """Analyzes PKG data to provide rich context for code generation."""
    
    def __init__(self, pkg_data: Dict[str, Any], query_engine: PKGQueryEngine):
        """
        Initialize code context analyzer.
        
        Args:
            pkg_data: Complete PKG dictionary
            query_engine: PKGQueryEngine instance
        """
        self.pkg_data = pkg_data
        self.query_engine = query_engine
        self.modules = pkg_data.get('modules', [])
        self.symbols = pkg_data.get('symbols', [])
        self.edges = pkg_data.get('edges', [])
    
    def analyze_symbol_context(self, symbol_id: str) -> Dict[str, Any]:
        """
        Get full context for a symbol.
        
        Args:
            symbol_id: Symbol ID
            
        Returns:
            Dictionary with signature, usage examples, related symbols, tests
        """
        symbol = self.query_engine.get_symbol_by_id(symbol_id)
        if not symbol:
            return {}
        
        # Get symbol details
        context = {
            "symbol": symbol,
            "signature": symbol.get('signature', ''),
            "summary": symbol.get('summary', ''),
            "examples": symbol.get('examples', []),
            "is_exported": symbol.get('isExported', False),
            "visibility": symbol.get('visibility', 'public'),
            "kind": symbol.get('kind', ''),
            "related_symbols": [],
            "test_symbols": [],
            "callers": [],
            "callees": []
        }
        
        # Find related symbols through edges
        related_symbols = self.find_related_symbols(symbol_id, max_depth=1)
        context["related_symbols"] = related_symbols
        
        # Find test symbols (edges with type "tests")
        for edge in self.edges:
            if edge.get('type') == 'tests' and edge.get('to') == symbol_id:
                test_symbol_id = edge.get('from')
                if test_symbol_id:
                    test_symbol = self.query_engine.get_symbol_by_id(test_symbol_id)
                    if test_symbol:
                        context["test_symbols"].append(test_symbol)
        
        # Find callers and callees
        for edge in self.edges:
            edge_type = edge.get('type', '')
            if edge_type == 'calls':
                if edge.get('to') == symbol_id:
                    # Someone calls this symbol
                    caller_id = edge.get('from')
                    if caller_id:
                        caller = self.query_engine.get_symbol_by_id(caller_id)
                        if caller:
                            context["callers"].append(caller)
                elif edge.get('from') == symbol_id:
                    # This symbol calls something
                    callee_id = edge.get('to')
                    if callee_id:
                        callee = self.query_engine.get_symbol_by_id(callee_id)
                        if callee:
                            context["callees"].append(callee)
        
        return context
    
    def find_related_symbols(self, symbol_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Find symbols that interact with this one (calls, imports, extends).
        
        Args:
            symbol_id: Symbol ID
            max_depth: Maximum depth to traverse
            
        Returns:
            List of related symbol dictionaries
        """
        related: Set[str] = set()
        visited: Set[str] = set()
        queue = [(symbol_id, 0)]
        
        while queue:
            current_id, depth = queue.pop(0)
            
            if current_id in visited or depth > max_depth:
                continue
            
            visited.add(current_id)
            
            # Find related symbols through edges
            for edge in self.edges:
                edge_type = edge.get('type', '')
                edge_from = edge.get('from')
                edge_to = edge.get('to')
                
                # Only consider relevant edge types
                if edge_type not in ['calls', 'imports', 'implements', 'extends']:
                    continue
                
                if edge_from == current_id and edge_to:
                    if edge_to not in visited:
                        related.add(edge_to)
                        queue.append((edge_to, depth + 1))
                elif edge_to == current_id and edge_from:
                    if edge_from not in visited:
                        related.add(edge_from)
                        queue.append((edge_from, depth + 1))
        
        # Get symbol objects
        related_symbols = []
        for sym_id in related:
            symbol = self.query_engine.get_symbol_by_id(sym_id)
            if symbol:
                related_symbols.append(symbol)
        
        return related_symbols
    
    def extract_code_patterns(self, module_id: str) -> Dict[str, Any]:
        """
        Extract framework patterns, architectural patterns from module.
        
        Args:
            module_id: Module ID
            
        Returns:
            Dictionary with framework_type, patterns (decorators, annotations), style
        """
        module = self.query_engine.get_module_by_id(module_id)
        if not module:
            return {}
        
        patterns = {
            "framework_type": None,
            "patterns": [],
            "style": {},
            "kind": module.get('kind', []),
            "metadata": module.get('metadata', {})
        }
        
        # Determine framework from kind and metadata
        kinds = module.get('kind', [])
        metadata = module.get('metadata', {})
        
        # Framework detection
        kind_str = ' '.join(kinds).lower() if isinstance(kinds, list) else ''
        if 'nestjs' in kind_str or 'controller' in kind_str or 'decorator' in kind_str:
            patterns["framework_type"] = "nestjs"
        elif 'spring' in kind_str or 'annotation' in kind_str or 'java' in kind_str:
            patterns["framework_type"] = "spring"
        elif 'react' in kind_str or 'component' in kind_str:
            patterns["framework_type"] = "react"
        elif 'angular' in kind_str:
            patterns["framework_type"] = "angular"
        elif 'vue' in kind_str:
            patterns["framework_type"] = "vue"
        elif 'flask' in kind_str or 'django' in kind_str:
            patterns["framework_type"] = "python_web"
        elif 'express' in kind_str or 'koa' in kind_str:
            patterns["framework_type"] = "nodejs"
        
        # Extract patterns from metadata
        if metadata:
            if 'decorators' in metadata:
                patterns["patterns"].extend(metadata.get('decorators', []))
            if 'annotations' in metadata:
                patterns["patterns"].extend(metadata.get('annotations', []))
            if 'imports' in metadata:
                patterns["style"]["import_style"] = metadata.get('imports', {})
        
        # Extract patterns from symbols in this module
        module_symbols = [s for s in self.symbols if s.get('moduleId') == module_id]
        for symbol in module_symbols:
            symbol_metadata = symbol.get('metadata', {})
            if symbol_metadata:
                if 'decorator' in symbol_metadata:
                    patterns["patterns"].append(symbol_metadata.get('decorator'))
                if 'annotation' in symbol_metadata:
                    patterns["patterns"].append(symbol_metadata.get('annotation'))
        
        return patterns
    
    def get_import_graph(self, module_id: str) -> Dict[str, Any]:
        """
        Get complete import dependency graph for a module.
        
        Args:
            module_id: Module ID
            
        Returns:
            Dictionary with direct_imports, transitive_imports, export_chain
        """
        module = self.query_engine.get_module_by_id(module_id)
        if not module:
            return {}
        
        direct_imports: Set[str] = set()
        transitive_imports: Set[str] = set()
        visited: Set[str] = set()
        
        # Get direct imports from module
        module_imports = module.get('imports', [])
        for imp in module_imports:
            direct_imports.add(imp)
        
        # Get imports from edges
        for edge in self.edges:
            if edge.get('type') == 'imports':
                edge_from = edge.get('from')
                edge_to = edge.get('to')
                
                # Extract module IDs
                from_module = self.query_engine._extract_module_id(edge_from) if edge_from else None
                to_module = self.query_engine._extract_module_id(edge_to) if edge_to else None
                
                if from_module == module_id and to_module:
                    direct_imports.add(to_module)
        
        # Build transitive imports (BFS)
        queue = list(direct_imports)
        while queue:
            current_module_id = queue.pop(0)
            
            if current_module_id in visited or current_module_id == module_id:
                continue
            
            visited.add(current_module_id)
            transitive_imports.add(current_module_id)
            
            # Get imports of this module
            current_module = self.query_engine.get_module_by_id(current_module_id)
            if current_module:
                current_imports = current_module.get('imports', [])
                for imp in current_imports:
                    if imp not in visited:
                        queue.append(imp)
        
        # Get export chain (modules that import this one)
        export_chain: Set[str] = set()
        for edge in self.edges:
            if edge.get('type') == 'imports':
                edge_from = edge.get('from')
                edge_to = edge.get('to')
                
                from_module = self.query_engine._extract_module_id(edge_from) if edge_from else None
                to_module = self.query_engine._extract_module_id(edge_to) if edge_to else None
                
                if to_module == module_id and from_module:
                    export_chain.add(from_module)
        
        # Get module objects
        direct_import_modules = [
            self.query_engine.get_module_by_id(mid) for mid in direct_imports
            if self.query_engine.get_module_by_id(mid)
        ]
        
        transitive_import_modules = [
            self.query_engine.get_module_by_id(mid) for mid in transitive_imports
            if self.query_engine.get_module_by_id(mid)
        ]
        
        export_chain_modules = [
            self.query_engine.get_module_by_id(mid) for mid in export_chain
            if self.query_engine.get_module_by_id(mid)
        ]
        
        return {
            "direct_imports": direct_import_modules,
            "transitive_imports": transitive_import_modules,
            "export_chain": export_chain_modules,
            "direct_import_ids": list(direct_imports),
            "transitive_import_ids": list(transitive_imports),
            "export_chain_ids": list(export_chain)
        }
    
    def build_code_generation_context(
        self, 
        target_module_id: str, 
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build comprehensive context for code generation.
        
        Args:
            target_module_id: Target module ID
            intent: Intent dictionary from intent router
            
        Returns:
            Dictionary with all relevant context needed for LLM to generate code
        """
        module = self.query_engine.get_module_by_id(target_module_id)
        if not module:
            logger.warning(f"Module not found: {target_module_id}")
            return {}
        
        context = {
            "target_module": module,
            "target_module_id": target_module_id,
            "framework": None,
            "patterns": {},
            "related_modules": [],
            "similar_modules": [],
            "import_patterns": {},
            "symbols": [],
            "type_information": {},
            "code_style": {}
        }
        
        # Extract code patterns
        patterns = self.extract_code_patterns(target_module_id)
        context["framework"] = patterns.get("framework_type")
        context["patterns"] = patterns
        
        # Get import graph
        import_graph = self.get_import_graph(target_module_id)
        context["import_patterns"] = {
            "direct_imports": [m.get('path', '') for m in import_graph.get('direct_imports', [])],
            "import_style": patterns.get('style', {}).get('import_style', {})
        }
        
        # Find related modules (from PKG edges)
        related_module_ids: Set[str] = set()
        
        # Get modules that this module imports
        for imp_id in import_graph.get('direct_import_ids', []):
            related_module_ids.add(imp_id)
        
        # Get modules that import this module
        for exp_id in import_graph.get('export_chain_ids', []):
            related_module_ids.add(exp_id)
        
        # Get related modules from edges
        for edge in self.edges:
            edge_type = edge.get('type', '')
            edge_from = edge.get('from')
            edge_to = edge.get('to')
            
            from_module = self.query_engine._extract_module_id(edge_from) if edge_from else None
            to_module = self.query_engine._extract_module_id(edge_to) if edge_to else None
            
            if from_module == target_module_id and to_module:
                related_module_ids.add(to_module)
            elif to_module == target_module_id and from_module:
                related_module_ids.add(from_module)
        
        # Get related module objects
        related_modules = []
        for mod_id in related_module_ids:
            mod = self.query_engine.get_module_by_id(mod_id)
            if mod:
                related_modules.append(mod)
        
        context["related_modules"] = related_modules[:10]  # Limit to 10
        
        # Find similar modules (same kind)
        module_kinds = module.get('kind', [])
        similar_modules = []
        for mod in self.modules:
            if mod['id'] == target_module_id:
                continue
            
            mod_kinds = mod.get('kind', [])
            # Check if they share any kind
            if any(k in mod_kinds for k in module_kinds if k):
                similar_modules.append(mod)
        
        context["similar_modules"] = similar_modules[:5]  # Limit to 5
        
        # Get symbols in target module
        module_symbols = [s for s in self.symbols if s.get('moduleId') == target_module_id]
        context["symbols"] = module_symbols
        
        # Extract type information from symbols
        type_info = {}
        for symbol in module_symbols:
            if symbol.get('signature'):
                type_info[symbol.get('name', '')] = {
                    "signature": symbol.get('signature'),
                    "kind": symbol.get('kind'),
                    "summary": symbol.get('summary', '')
                }
        
        context["type_information"] = type_info
        
        # Extract code style hints
        context["code_style"] = {
            "naming_convention": self._infer_naming_convention(module_symbols),
            "export_style": "named" if any(s.get('isExported') for s in module_symbols) else "default"
        }
        
        return context
    
    def _infer_naming_convention(self, symbols: List[Dict[str, Any]]) -> str:
        """Infer naming convention from symbols."""
        if not symbols:
            return "unknown"
        
        # Check for common patterns
        camel_case_count = 0
        snake_case_count = 0
        pascal_case_count = 0
        
        for symbol in symbols:
            name = symbol.get('name', '')
            if not name:
                continue
            
            if '_' in name:
                snake_case_count += 1
            elif name[0].isupper() if name else False:
                pascal_case_count += 1
            elif name[0].islower() if name else False:
                camel_case_count += 1
        
        if snake_case_count > camel_case_count and snake_case_count > pascal_case_count:
            return "snake_case"
        elif pascal_case_count > camel_case_count:
            return "PascalCase"
        else:
            return "camelCase"
