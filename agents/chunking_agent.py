try:
    from langchain.agents import create_agent
except ImportError:
    def create_agent(*args, **kwargs):
        raise ImportError("langchain is not installed. Please install it with: pip install langchain")

try:
    from langchain_core.tools import tool
except ImportError:
    try:
        from langchain.tools import tool
    except ImportError:
        # Fallback: create a dummy tool decorator
        def tool(*args, **kwargs):
            def decorator(func):
                return func
            return decorator
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.agents.structured_output import ToolStrategy
from typing import List, Optional
from pydantic import BaseModel
from typing import List

class ChunkOutput(BaseModel):
    chunks: List[str]


@tool
def chunk_text(
    content: str,
    chunk_size: Optional[int] = 1000,
    chunk_overlap: Optional[int] = 200,
    separators: Optional[List[str]] = None,
    max_chunks: Optional[int] = None
) -> ChunkOutput:
    """
    Chunk text using LangChain's RecursiveCharacterTextSplitter.
    
    Args:
        content: Input text to chunk
        chunk_size: Maximum size of each chunk (default: 1000)
        chunk_overlap: Overlap between chunks (default: 200)
        separators: List of separators to use for splitting (default: ["\n\n", "\n", ".", " ", ""])
        max_chunks: Maximum number of chunks to return (optional)
    
    Returns:
        List of text chunks as below:
        chunks: List[str]
    """
    
    # Set default separators if not provided
    if separators is None:
        separators = ["\n\n", "\n", ".", " ", ""]
    
    # Initialize the text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
        length_function=len,
        is_separator_regex=False
    )
    
    # Split the text
    chunks = text_splitter.split_text(content)
    
    # Apply max_chunks limit if specified
    if max_chunks and len(chunks) > max_chunks:
        chunks = chunks[:max_chunks]
    
    return {"chunks": chunks}


def create_chunking_agent():
    CHUNKING_SYSTEM = """
        You are a chunking assistant.
        Split the input text STRICTLY into chunks of 500-800 characters.
        Do NOT return a single long chunk.
        Return ONLY a ChunkOutput object with the field:

        chunks: List[str]

        Make sure each chunk is:
        - <= 800 chars
        - >= 300 chars
        - clean, no broken sentences
        """
    
    agent = create_agent(
        tools=[chunk_text],
        model="gpt-4o-mini",
        system_prompt=CHUNKING_SYSTEM,
        response_format=ToolStrategy(ChunkOutput),
    )
    return agent