"""
AI module initialization
"""
from .image_hash import ImageHasher, ImageHashDatabase

__all__ = ['ImageHasher', 'ImageHashDatabase']

# Embeddings are optional (requires PyTorch)
try:
    from .embeddings import EmbeddingGenerator, FAISSVectorStore
    __all__.extend(['EmbeddingGenerator', 'FAISSVectorStore'])
except ImportError:
    pass
