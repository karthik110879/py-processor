from langchain.agents import tool
from docling.document_converter import DocumentConverter
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel
from typing import List, Dict, Any

class DocumentExtractionResult(BaseModel):
    raw_text: str
    document_type: str
    segments: List[Dict[str, Any]]
    entities: List[Dict[str, Any]]
    kpis: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]

@tool(
    "extract_text_docling",
    description="Extract raw text from a document using Docling converter (PDF, DOCX, PPTX, HTML)."
)
def extract_text_docling(file_path: str):
    try:
        print(f"[Docling] Extracting: {file_path}")
        converter = DocumentConverter()
        result = converter.convert(file_path)
        doc = result.document if hasattr(result, 'document') else result

        content = doc.export_to_markdown()

        print("[Docling] Extraction complete.")
        return {"success": True, "text": content}
    except Exception as e:
        print("[Docling] Failed:", e)
        return {"success": False, "message": str(e)}
    


@tool(
    "semantic_analysis",
    description="Perform semantic analysis on text to identify document type, segments, entities, KPIs, and relationships.")
def semantic_analysis(text: str):
    try:
        print("[Semantic] Running semantic analysis...")

        semantic_result = {
            "document_type": "generic",
            "segments": [],
            "entities": [],
            "kpis": [],
            "relationships": [],
        }

        print("[Semantic] Analysis complete.")
        return {"success": True, "semantic": semantic_result}

    except Exception as e:
        print("[Semantic] Failed:", e)
        return {"success": False, "message": str(e)}



agent = create_agent(
    model=ChatOpenAI(model="gpt-5", temperature=0),
    tools=[extract_text_docling, semantic_analysis],
    response_format=ToolStrategy(DocumentExtractionResult),
    system_prompt="""
You are an intelligent document extraction and semantic-analysis agent.
Always follow tool usage rules and output only valid structured data.
""",
    instructions="""
Rules:
1. If the user gives a file path → ALWAYS call extract_text_docling first.
2. After extracting text → ALWAYS call semantic_analysis.
3. Use the outputs of both tools to populate the final structured result.
4. Final output MUST strictly follow the DocumentExtractionResult JSON schema.
"""
)
