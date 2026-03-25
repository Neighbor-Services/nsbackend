import numpy as np
from openai import OpenAI
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
            if not api_key:
                logger.warning("OPENAI_API_KEY is not set.")
                return None
            cls._client = OpenAI(api_key=api_key)
        return cls._client

    @classmethod
    def get_embedding(cls, text):
        """
        Generates an embedding vector for the given text using OpenAI's wrapper.
        Returns a list of floats or None on failure.
        """
        client = cls.get_client()
        if not client or not text:
            return None

        try:
            # text-embedding-3-small is cost-effective and performant
            response = client.embeddings.create(
                input=text.replace("\n", " "),
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    @classmethod
    def cosine_similarity(cls, vec_a, vec_b):
        """
        Calculates cosine similarity between two vectors.
        Returns float between -1 and 1.
        """
        if not vec_a or not vec_b:
            return 0.0
        
        a = np.array(vec_a)
        b = np.array(vec_b)
        
        if a.shape != b.shape:
             # Ensure dimensions match (truncate or pad if absolutely necessary, but usually implies model mismatch)
             return 0.0

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return np.dot(a, b) / (norm_a * norm_b)
