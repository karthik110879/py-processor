"""Generate summaries for modules and symbols using LangChain/OpenAI."""

import os
from typing import Dict, Any, List, Optional
from utils.config import Config

try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


def generate_module_summary(module: Dict[str, Any], llm) -> str:
    """
    Generate a summary for a module.
    
    Args:
        module: Module dictionary
        llm: LangChain LLM instance
        
    Returns:
        Summary string
    """
    path = module.get("path", "")
    kinds = module.get("kind", [])
    exports_count = len(module.get("exports", []))
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a code documentation assistant. Generate concise, informative summaries for code modules."),
        ("human", "Generate a 1-2 sentence summary for this module:\n"
                  f"Path: {path}\n"
                  f"Types: {', '.join(kinds) if kinds else 'generic'}\n"
                  f"Exports: {exports_count} symbols\n"
                  "Summary:")
    ])
    
    try:
        chain = prompt | llm
        response = chain.invoke({})
        return response.content.strip()
    except Exception:
        return f"Module at {path} with {exports_count} exports"


def generate_symbol_summary(symbol: Dict[str, Any], llm) -> str:
    """
    Generate a summary for a symbol.
    
    Args:
        symbol: Symbol dictionary
        llm: LangChain LLM instance
        
    Returns:
        Summary string
    """
    name = symbol.get("name", "")
    kind = symbol.get("kind", "")
    signature = symbol.get("signature", "")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a code documentation assistant. Generate concise summaries for code symbols."),
        ("human", f"Generate a 1 sentence summary for this {kind}:\n"
                  f"Name: {name}\n"
                  f"Signature: {signature}\n"
                  "Summary:")
    ])
    
    try:
        chain = prompt | llm
        response = chain.invoke({})
        return response.content.strip()
    except Exception:
        return f"{kind} {name}"


def generate_project_summary(project: Dict[str, Any], modules: List[Dict[str, Any]], llm) -> str:
    """
    Generate a project-level summary.
    
    Args:
        project: Project dictionary
        modules: List of module dictionaries
        llm: LangChain LLM instance
        
    Returns:
        Summary string
    """
    name = project.get("name", "")
    languages = project.get("languages", [])
    modules_count = len(modules)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a code documentation assistant. Generate concise project summaries."),
        ("human", f"Generate a 2-3 sentence summary for this project:\n"
                  f"Name: {name}\n"
                  f"Languages: {', '.join(languages)}\n"
                  f"Modules: {modules_count}\n"
                  "Summary:")
    ])
    
    try:
        chain = prompt | llm
        response = chain.invoke({})
        return response.content.strip()
    except Exception:
        return f"Project {name} with {modules_count} modules in {', '.join(languages)}"


def generate_summaries(pkg_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate summaries for modules, symbols, and project.
    
    Args:
        pkg_data: Complete PKG dictionary
        
    Returns:
        PKG dictionary with summaries added
    """
    if not LANGCHAIN_AVAILABLE:
        return pkg_data
    
    config = Config()
    api_key = config.openai_api_key
    if not api_key:
        # Skip summary generation if API key not available
        return pkg_data
    
    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            openai_api_key=api_key
        )
    except Exception:
        return pkg_data
    
    # Generate module summaries
    modules = pkg_data.get("modules", [])
    for module in modules:
        if not module.get("moduleSummary"):
            try:
                module["moduleSummary"] = generate_module_summary(module, llm)
            except Exception:
                pass
    
    # Generate symbol summaries
    symbols = pkg_data.get("symbols", [])
    for symbol in symbols:
        if not symbol.get("summary"):
            try:
                symbol["summary"] = generate_symbol_summary(symbol, llm)
            except Exception:
                pass
    
    # Generate project summary
    project = pkg_data.get("project", {})
    if not project.get("summary"):
        try:
            project["summary"] = generate_project_summary(project, modules, llm)
        except Exception:
            pass
    
    # Add summaries section
    if "summaries" not in pkg_data:
        pkg_data["summaries"] = {}
    
    if project.get("summary"):
        pkg_data["summaries"]["projectSummary"] = project["summary"]
    
    # Add top modules summary
    top_modules = sorted(modules, key=lambda m: len(m.get("exports", [])), reverse=True)[:5]
    top_summaries = [m.get("moduleSummary", "") for m in top_modules if m.get("moduleSummary")]
    if top_summaries:
        pkg_data["summaries"]["topModulesSummary"] = top_summaries
    
    return pkg_data

