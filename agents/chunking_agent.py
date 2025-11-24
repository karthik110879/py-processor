from langchain.agents import create_agent
from langchain.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Optional

@tool
def chunk_text(
    text: str,
    chunk_size: Optional[int] = 1000,
    chunk_overlap: Optional[int] = 200,
    separators: Optional[List[str]] = None,
    max_chunks: Optional[int] = None
) -> List[str]:
    """
    Chunk text using LangChain's RecursiveCharacterTextSplitter.
    
    Args:
        text: Input text to chunk
        chunk_size: Maximum size of each chunk (default: 1000)
        chunk_overlap: Overlap between chunks (default: 200)
        separators: List of separators to use for splitting (default: ["\n\n", "\n", ".", " ", ""])
        max_chunks: Maximum number of chunks to return (optional)
    
    Returns:
        List of text chunks
    """
    # Input validation
    if not text or not isinstance(text, str):
        raise ValueError("Input text must be a non-empty string")
    
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")
    
    if max_chunks is not None and max_chunks <= 0:
        raise ValueError("max_chunks must be positive if specified")
    
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
    chunks = text_splitter.split_text(text)
    
    # Apply max_chunks limit if specified
    if max_chunks and len(chunks) > max_chunks:
        chunks = chunks[:max_chunks]
    
    return chunks


@tool
def chunk_by_sentences(
    text: str,
    sentences_per_chunk: int = 5,
    overlap_sentences: int = 1
) -> List[str]:
    """
    Chunk text by grouping sentences together.
    
    Args:
        text: Input text to chunk
        sentences_per_chunk: Number of sentences per chunk
        overlap_sentences: Number of overlapping sentences between chunks
    
    Returns:
        List of text chunks
    """
    if not text or not isinstance(text, str):
        raise ValueError("Input text must be a non-empty string")
    
    if sentences_per_chunk <= 0:
        raise ValueError("sentences_per_chunk must be positive")
    
    if overlap_sentences < 0:
        raise ValueError("overlap_sentences must be non-negative")
    
    # Simple sentence splitting
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    
    chunks = []
    i = 0
    while i < len(sentences):
        end_idx = min(i + sentences_per_chunk, len(sentences))
        chunk = '. '.join(sentences[i:end_idx])
        if chunk:
            chunks.append(chunk + '.')
        i += sentences_per_chunk - overlap_sentences
    
    return chunks

@tool
def chunk_fixed_size(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[str]:
    """
    Chunk text using fixed-size chunks with character-level splitting.
    
    Args:
        text: Input text to chunk
        chunk_size: Maximum size of each chunk
        chunk_overlap: Overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not text or not isinstance(text, str):
        raise ValueError("Input text must be a non-empty string")
    
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative")
    
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        
        # Move start position for next chunk, accounting for overlap
        start += chunk_size - chunk_overlap
        
        # If we're at the end or overlap would cause infinite loop
        if start >= len(text) or chunk_overlap == 0:
            break
    
    return chunks


def create_chunking_agent():
    system_prompt = """
    You are a chunking agent with multiple text chunking strategies.
    
    Available tools:
    1. chunk_text - Recursive character splitting (default)
    2. chunk_by_sentences - Sentence-based grouping  
    3. chunk_fixed_size - Fixed-size character chunks
    
    Guidelines:
    - Use EXACTLY the user input text from: {input}
    - Choose the appropriate tool based on the user's needs
    - If the user specifies sentences or wants sentence-level chunks, use chunk_by_sentences
    - If the user wants fixed-size chunks, use chunk_fixed_size
    - Otherwise, use chunk_text as the default
    
    Output ONLY the JSON returned by the tool.
    """
    
    agent = create_agent(
        tools=[chunk_text, chunk_by_sentences, chunk_fixed_size],
        model="gpt-4o-mini",
        system_prompt=system_prompt,
    )
    return agent