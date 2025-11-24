import os
from langchain.tools import tool
from langchain.agents import create_agent
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from typing import Dict, Any
import uuid

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
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",  # or "text-embedding-3-large"
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Generate embeddings
        print(f"Generating embeddings for {len(chunks)} chunks...")
        vectors = embeddings.embed_documents(chunks)
        print(f"Generated embeddings with dimension: {len(vectors[0])}")
        
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
        
        # Create points for storage
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vectors[i],
                payload={
                    "text": chunks[i],
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "text_length": len(chunks[i])
                }
            )
            for i in range(len(chunks))
        ]
        
        # Store in Qdrant
        operation_info = client.upsert(collection_name="documents", points=points)
        print(f"Upsert operation info: {operation_info}")
        
        print(f"Successfully stored {len(chunks)} chunks in Qdrant")
        return len(chunks)
        
    except Exception as e:
        print(f"Error storing vectors: {str(e)}")
        return f"Error storing vectors: {str(e)}"


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