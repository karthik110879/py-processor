import os
from utils.config import Config
try:
    from langchain_core.tools import tool
except ImportError:
    try:
        from langchain.tools import tool
    except ImportError:
        # Fallback: create a dummy tool decorator if langchain is not available
        def tool(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

try:
    from langchain.agents import create_agent
except ImportError:
    # Fallback: create a dummy create_agent function
    def create_agent(*args, **kwargs):
        raise ImportError("langchain is not installed. Please install it with: pip install langchain")
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from qdrant_client.http.exceptions import UnexpectedResponse
from typing import Dict, Any
import uuid
import json

COLLECTION_NAME = "documents"

@tool("store_vectors")
def store_vectors(payload: Dict[str, Any]) -> int:
    """
    Store text chunks with OpenAI embeddings in Qdrant database.
    
    Args:
        payload: Dictionary containing "chunks" key with list of text chunks
        
    Returns:
        int: Number of chunks stored
        
    Example:
        payload = {"chunks": ["chunk 1 text", "chunk 2 text", "chunk 3 text"]}
    """
    try:
        # Input validation
        if not payload or "chunks" not in payload:
            raise ValueError("Payload must contain 'chunks' key")
        
        chunks = payload["chunks"]
        if not chunks or not isinstance(chunks, list):
            raise ValueError("Chunks must be a non-empty list")
        
        # Initialize OpenAI embeddings
        config = Config()
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",  # or "text-embedding-3-large"
            openai_api_key=config.openai_api_key
        )
        
        # Generate vectors
        vectors = embeddings.embed_documents(chunks)
        vector_dim = len(vectors[0])
        
        # Initialize Qdrant client
        client = QdrantClient(path="qdrant_local")
        
        # Recreate collection with proper vector size
        client.recreate_collection(
            collection_name="documents",
            vectors_config=VectorParams(
                size=len(vectors[0]),  # Dynamic size based on OpenAI embeddings
                distance=Distance.COSINE
            )
        )
        
        # Format points
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=[float(x) for x in vectors[i]],  # ensure float32
                payload={
                    "text": chunks[i],
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "text_length": len(chunks[i])
                }
            )
            for i in range(len(chunks))
        ]

        # Upsert into Qdrant
        client.upsert(collection_name=COLLECTION_NAME, points=points)

        return {
            "status": "success",
            "stored": len(chunks),
            "collection": COLLECTION_NAME,
            "dimension": vector_dim
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
    

@tool("search_vectors")
def search_vectors(query: str, limit: int = 5) -> str:
    """
    Search for similar text chunks using vector similarity.
    
    Args:
        query: Search query text
        limit: Maximum number of results to return (default: 5)
        
    Returns:
        str: JSON string of search results
    """
    try:
        # Initialize OpenAI embeddings
        config = Config()
        api_key = config.openai_api_key
        if not api_key:
            return "Error: OPENAI_API_KEY environment variable not set"
        
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            openai_api_key=api_key
        )
        
        # Generate query embedding
        query_vector = embeddings.embed_query(query)
        
        # Initialize Qdrant client
        client = QdrantClient(path="./qdrant_local")
        
        # Search for similar vectors
        search_results, _ = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=limit
        )

        
        # Format results
        results = []
        for result in search_results:
            results.append({
                "score": result.score,
                "text": result.payload.get("text", ""),
                "document_id": result.payload.get("document_id", ""),
                "chunk_index": result.payload.get("chunk_index", -1)
            })
        
        return json.dumps(results, indent=2)
        
    except Exception as e:
        error_msg = f"Error searching vectors: {str(e)}"
        print(error_msg)
        return error_msg


def create_store_agent():
    """Create agent for storing and managing vectors in Qdrant with OpenAI embeddings."""
    system_prompt = """
    You are a vector storage agent that manages document chunks in Qdrant database using OpenAI embeddings.
    
    Available tools:
    store_vectors - Store text chunks with OpenAI embeddings in Qdrant
    
    Instructions:
    - For storing chunks, use store_vectors with payload containing "chunks" list
    
    Always return clear confirmation messages or search results.
    """
    
    agent = create_agent(
        tools=[
            store_vectors
        ],
        model="gpt-4o-mini",
        system_prompt=system_prompt,
    )
    return agent