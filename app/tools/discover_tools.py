from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from typing import List
from common.services.qdrant import Qdrant
from qdrant_client import models
from langchain_cohere import CohereRerank
from langchain.retrievers import ContextualCompressionRetriever
from settings import settings
from common.services.logger import logger


@tool
def filter_sessions(query: str, config: RunnableConfig) -> str:
    """
    Filter and retrieve user sessions based on a semantic search query.
    
    This tool searches through user session data to find the most relevant sessions 
    based on the provided query. It uses semantic similarity and reranking to return 
    the most pertinent session information.
    
    Args:
        query: The search query to find relevant user sessions
        
    Returns:
        A formatted string containing the relevant session data including session content,
        metadata, and relevance information that can be used to answer user questions
        about their sessions.
    """
    try:
        # Extract org_id from config
        org_id = config.get("configurable", {}).get("org_id")
        logger.info(f"org_id: {org_id}")
        if not org_id:
            raise ValueError("org_id not found in config")
        
        top_n = config.get("configurable", {}).get("top_n", 5)
        top_k = config.get("configurable", {}).get("top_k", 30)
        logger.info(f"top_n: {top_n}")
        logger.info(f"top_k: {top_k}")
            
        qdrant = Qdrant()

        retriever = qdrant.get_qdrant().as_retriever(search_type="similarity", search_kwargs={"k": top_k, "filter": models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.org_id",
                    match=models.MatchValue(value=org_id)
                )
            ]
        )})

        # Create Cohere's reranker with the vector DB using Cohere's embeddings as the base retriever
        reranker = CohereRerank(
            cohere_api_key=settings.COHERE_API_KEY, model="rerank-v3.5", top_n=top_n
        )
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=reranker, base_retriever=retriever
        )
        results = compression_retriever.invoke(query)
        
        # Format the results for better consumption by the agent
        if not results:
            return "No relevant sessions found for the given query."
        
        formatted_results = []
        for i, doc in enumerate(results, 1):
            session_data = f"Session {i}:\n"
            session_data += f"Content: {doc.page_content}\n"
            if doc.metadata:
                session_data += f"Metadata: {doc.metadata}\n"
            session_data += "---\n"
            formatted_results.append(session_data)
        
        return "\n".join(formatted_results)
        
    except Exception as e:
        logger.error(f"Error searching knowledge base for org {org_id if 'org_id' in locals() else 'unknown'}: {e}")
        raise e
