from typing import List
from langchain_qdrant import QdrantVectorStore
from settings import settings
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models

from common.services.logger import logger

from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams

class Qdrant:
    def __init__(self):
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY, model="text-embedding-3-large")
        self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

        # Initialize Qdrant client
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=10000  # Adjust timeout as needed
        )

        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                # 3072
                # 1536
                # vectors_config=rest_models.VectorParams(size=1536, distance=rest_models.Distance.COSINE),
                vectors_config={"dense": VectorParams(size=3072, distance=Distance.COSINE)},
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=rest_models.SparseIndexParams(on_disk=False))
                },
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="metadata.org_id",
                field_schema=rest_models.PayloadSchemaType.INTEGER
            )
            
        self.qdrant = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense",
            sparse_vector_name="sparse",
        )
        

    def get_qdrant(self) -> QdrantVectorStore:
        return self.qdrant
            
    

