"""Diagram Generator - Creates dependency diagrams from PKG data."""

import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict

from services.pkg_query_engine import PKGQueryEngine

logger = logging.getLogger(__name__)


class DiagramGenerator:
    """Generates dependency diagrams and visualizations from PKG data."""
    
    def __init__(self, pkg_data: Dict[str, Any], pkg_query_engine: Optional[PKGQueryEngine] = None):
        """
        Initialize diagram generator.
        
        Args:
            pkg_data: Complete PKG dictionary
            pkg_query_engine: Optional PKGQueryEngine instance (will create if not provided)
        """
        self.pkg_data = pkg_data
        self.query_engine = pkg_query_engine or PKGQueryEngine(pkg_data)
    
    def generate_diagram(self, intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Generate a diagram based on the request.
        
        Args:
            intent: Extracted intent dictionary
            user_message: User's message
            
        Returns:
            Dictionary with diagram content, format, and metadata
        """
        message_lower = user_message.lower()
        
        # Determine diagram type and scope
        if 'architecture' in message_lower or 'project' in message_lower:
            diagram_type = "architecture"
            module_ids = None  # All modules
        elif 'module' in message_lower:
            # Try to extract specific module
            module_id = self._extract_module_from_query(user_message)
            if module_id:
                diagram_type = "module"
                module_ids = [module_id]
            else:
                diagram_type = "dependency"
                module_ids = None
        else:
            diagram_type = "dependency"
            module_ids = None
        
        # Determine format preference
        if 'mermaid' in message_lower:
            format_type = "mermaid"
        elif 'dot' in message_lower or 'graphviz' in message_lower:
            format_type = "dot"
        else:
            format_type = "text"  # Default to text
        
        # Determine depth
        depth = 2
        if 'depth' in message_lower or 'level' in message_lower:
            import re
            depth_match = re.search(r'(?:depth|level)\s*[:\s]*(\d+)', message_lower)
            if depth_match:
                depth = int(depth_match.group(1))
        
        # Build dependency graph
        graph_data = self._build_dependency_graph(module_ids, depth)
        
        # Generate diagram in requested format
        if format_type == "text":
            content = self._generate_text_diagram(graph_data)
        elif format_type == "dot":
            content = self._generate_dot_format(graph_data)
        elif format_type == "mermaid":
            content = self._generate_mermaid_format(graph_data)
        else:
            content = self._generate_text_diagram(graph_data)
        
        return {
            "diagram_type": diagram_type,
            "format": format_type,
            "content": content,
            "modules_included": graph_data.get('module_ids', []),
            "metadata": {
                "depth": depth,
                "edge_count": len(graph_data.get('edges', [])),
                "module_count": len(graph_data.get('module_ids', []))
            }
        }
    
    def _build_dependency_graph(self, module_ids: Optional[List[str]], depth: int) -> Dict[str, Any]:
        """
        Build dependency graph from PKG data.
        
        Args:
            module_ids: List of starting module IDs (None for all modules)
            depth: Maximum depth to traverse
            
        Returns:
            Dictionary with module_ids, edges, and module_info
        """
        if module_ids is None:
            # Include all modules
            all_modules = self.pkg_data.get('modules', [])
            module_ids = [m.get('id') for m in all_modules if m.get('id')]
        else:
            # Expand to include dependencies up to depth
            impacted = self.query_engine.get_impacted_modules(module_ids, depth)
            module_ids = impacted.get('impacted_module_ids', module_ids)
        
        # Build edge list for included modules
        edges = []
        all_edges = self.pkg_data.get('edges', [])
        module_id_set = set(module_ids)
        
        for edge in all_edges:
            edge_from = edge.get('from', '')
            edge_to = edge.get('to', '')
            edge_type = edge.get('type', '')
            
            # Extract module IDs
            from_module = self.query_engine._extract_module_id(edge_from)
            to_module = self.query_engine._extract_module_id(edge_to)
            
            # Only include edges between modules in our set
            if from_module and to_module and from_module in module_id_set and to_module in module_id_set:
                # Only include import and call relationships for dependency diagrams
                if edge_type in ['imports', 'calls']:
                    edges.append({
                        'from': from_module,
                        'to': to_module,
                        'type': edge_type
                    })
        
        # Get module info
        module_info = {}
        for mod_id in module_ids:
            module = self.query_engine.get_module_by_id(mod_id)
            if module:
                module_info[mod_id] = {
                    'path': module.get('path', mod_id),
                    'kind': module.get('kind', [])
                }
        
        return {
            'module_ids': module_ids,
            'edges': edges,
            'module_info': module_info
        }
    
    def _generate_text_diagram(self, graph_data: Dict[str, Any]) -> str:
        """Generate a text/ASCII diagram."""
        module_ids = graph_data.get('module_ids', [])
        edges = graph_data.get('edges', [])
        module_info = graph_data.get('module_info', {})
        
        if not module_ids:
            return "No modules found to diagram."
        
        # Build adjacency list
        adj_list = defaultdict(list)
        for edge in edges:
            from_mod = edge.get('from')
            to_mod = edge.get('to')
            if from_mod and to_mod:
                adj_list[from_mod].append(to_mod)
        
        # Generate tree-like representation
        diagram = "Dependency Diagram\n"
        diagram += "=" * 50 + "\n\n"
        
        # Group by root modules (modules with no incoming edges)
        incoming = set()
        for edge in edges:
            incoming.add(edge.get('to'))
        
        root_modules = [m for m in module_ids if m not in incoming]
        
        if not root_modules:
            # If no clear roots, just show all modules
            root_modules = module_ids[:10]  # Limit to 10
        
        def format_module_name(mod_id: str) -> str:
            """Format module name for display."""
            info = module_info.get(mod_id, {})
            path = info.get('path', mod_id)
            # Shorten path if too long
            if len(path) > 40:
                parts = path.split('/')
                if len(parts) > 2:
                    return f".../{'/'.join(parts[-2:])}"
            return path
        
        def print_tree(node: str, prefix: str = "", is_last: bool = True, visited: Set[str] = None, depth: int = 0):
            """Recursively print tree structure."""
            if visited is None:
                visited = set()
            if depth > 3 or node in visited:  # Limit depth and avoid cycles
                return ""
            
            visited.add(node)
            result = prefix + ("└── " if is_last else "├── ") + format_module_name(node) + "\n"
            
            children = adj_list.get(node, [])
            if children:
                for i, child in enumerate(children[:5]):  # Limit children
                    is_last_child = (i == len(children) - 1) or i >= 4
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    result += print_tree(child, child_prefix, is_last_child, visited.copy(), depth + 1)
            
            return result
        
        for i, root in enumerate(root_modules[:5]):  # Limit roots
            is_last = (i == len(root_modules) - 1) or i >= 4
            diagram += print_tree(root, "", is_last, set(), 0)
            if i < len(root_modules) - 1:
                diagram += "\n"
        
        if len(module_ids) > len(root_modules):
            remaining = len(module_ids) - len(root_modules)
            diagram += f"\n... and {remaining} more modules\n"
        
        return diagram
    
    def _generate_dot_format(self, graph_data: Dict[str, Any]) -> str:
        """Generate Graphviz DOT format diagram."""
        module_ids = graph_data.get('module_ids', [])
        edges = graph_data.get('edges', [])
        module_info = graph_data.get('module_info', {})
        
        dot = "digraph Dependencies {\n"
        dot += "  rankdir=LR;\n"
        dot += "  node [shape=box, style=rounded];\n\n"
        
        # Add nodes
        for mod_id in module_ids:
            info = module_info.get(mod_id, {})
            path = info.get('path', mod_id)
            # Escape special characters and shorten
            label = path.replace('"', '\\"')
            if len(label) > 30:
                parts = label.split('/')
                if len(parts) > 1:
                    label = f".../{parts[-1]}"
            
            # Create safe node ID
            node_id = mod_id.replace(':', '_').replace('/', '_').replace('.', '_')
            dot += f'  "{node_id}" [label="{label}"];\n'
        
        dot += "\n"
        
        # Add edges
        for edge in edges:
            from_mod = edge.get('from')
            to_mod = edge.get('to')
            if from_mod and to_mod:
                from_id = from_mod.replace(':', '_').replace('/', '_').replace('.', '_')
                to_id = to_mod.replace(':', '_').replace('/', '_').replace('.', '_')
                dot += f'  "{from_id}" -> "{to_id}";\n'
        
        dot += "}\n"
        
        return dot
    
    def _generate_mermaid_format(self, graph_data: Dict[str, Any]) -> str:
        """Generate Mermaid format diagram."""
        module_ids = graph_data.get('module_ids', [])
        edges = graph_data.get('edges', [])
        module_info = graph_data.get('module_info', {})
        
        mermaid = "graph TD\n"
        
        # Create node mapping
        node_map = {}
        for i, mod_id in enumerate(module_ids):
            info = module_info.get(mod_id, {})
            path = info.get('path', mod_id)
            # Shorten path
            if len(path) > 25:
                parts = path.split('/')
                if len(parts) > 1:
                    display_name = f".../{parts[-1]}"
                else:
                    display_name = path[:25] + "..."
            else:
                display_name = path
            
            node_id = f"M{i}"
            node_map[mod_id] = node_id
            # Escape special characters for Mermaid
            display_name = display_name.replace('"', '&quot;').replace("'", "&#39;")
            mermaid += f'  {node_id}["{display_name}"]\n'
        
        mermaid += "\n"
        
        # Add edges
        for edge in edges:
            from_mod = edge.get('from')
            to_mod = edge.get('to')
            if from_mod and to_mod and from_mod in node_map and to_mod in node_map:
                mermaid += f'  {node_map[from_mod]} --> {node_map[to_mod]}\n'
        
        return mermaid
    
    def _extract_module_from_query(self, query: str) -> Optional[str]:
        """Try to extract module ID or path from query."""
        import re
        
        # Look for "mod:path" pattern
        mod_match = re.search(r'mod:([^\s]+)', query)
        if mod_match:
            return mod_match.group(0)
        
        # Look for file paths
        path_match = re.search(r'([a-zA-Z0-9_/\\]+\.(py|ts|js|tsx|jsx))', query)
        if path_match:
            path = path_match.group(1)
            # Try to find module with this path
            for module in self.pkg_data.get('modules', []):
                if path in module.get('path', '') or module.get('path', '').endswith(path):
                    return module.get('id')
        
        return None
