from qdrant_client import QdrantClient
from qdrant_client.models import (VectorParams, Distance, PointStruct)

from langchain_openai import OpenAIEmbeddings
import uuid

def store_in_qdrant(chunks, collection_name="documents"):

    # Initialize Qdrant (local persistent)
    client = QdrantClient(path="qdrant_local")

    # Create Embedding model
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

    # Create collection if not exists
    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=3072,          # dimension of text-embedding-3-large
            distance=Distance.COSINE
        )
    )

    # Embed chunks
    vectors = embeddings.embed_documents(chunks)

    points = []
    for vector, chunk in zip(vectors, chunks):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"text": chunk}
            )
        )

    client.upsert(
        collection_name=collection_name,
        points=points,
    )

    # Return number of stored chunks
    return len(points)



def get_all_chunks(collection_name="documents"):
    client = QdrantClient(path="qdrant_local")

    records = client.scroll(
        collection_name=collection_name,
        limit=9999,
        with_payload=True,
        with_vectors=False
    )

    chunks = [point.payload["text"] for point in records[0]]
    return chunks