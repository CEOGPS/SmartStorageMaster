"""
Embeddings module for deep learning-based duplicate detection
"""
from pathlib import Path
from typing import Optional, List, Tuple
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torchvision.transforms as transforms
    from torchvision.models import resnet50
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available - deep learning features disabled")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available - advanced similarity search disabled")


class EmbeddingGenerator:
    """Generate embeddings for images using ResNet50"""
    
    def __init__(self):
        """Initialize embedding generator"""
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch and torchvision required for embeddings")
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Load pre-trained ResNet50
        self.model = resnet50(weights='DEFAULT')
        self.model = self.model.to(self.device)
        self.model.eval()
        
        # Remove classification layer to get embeddings
        self.model = torch.nn.Sequential(*(list(self.model.children())[:-1]))
        
        # Preprocessing
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
        ])
        
        logger.info(f"EmbeddingGenerator initialized on {self.device}")
    
    def generate(self, image_path: Path) -> Optional[np.ndarray]:
        """
        Generate embedding for image
        
        Args:
            image_path: Path to image file
        
        Returns:
            2048-dimensional embedding vector or None if processing fails
        """
        try:
            from PIL import Image
            
            img = Image.open(image_path).convert('RGB')
            img_tensor = self.transform(img).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                embedding = self.model(img_tensor)
                embedding = embedding.squeeze().cpu().numpy()
                
                # Normalize embedding
                embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
            
            return embedding.astype(np.float32)
        
        except Exception as e:
            logger.warning(f"Failed to generate embedding for {image_path}: {e}")
            return None


class FAISSVectorStore:
    """FAISS-based vector similarity search"""
    
    def __init__(self, dimension: int = 2048):
        """
        Initialize FAISS vector store
        
        Args:
            dimension: Embedding dimension (ResNet50 outputs 2048)
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("FAISS requires PyTorch")
        
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.embeddings: List[np.ndarray] = []
        self.file_paths: List[Path] = []
    
    def add_embedding(self, file_path: Path, embedding: np.ndarray) -> None:
        """
        Add embedding to index
        
        Args:
            file_path: Path to file
            embedding: Embedding vector
        """
        if embedding.shape[0] != self.dimension:
            raise ValueError(f"Expected dimension {self.dimension}, got {embedding.shape[0]}")
        
        embedding_reshaped = embedding.reshape(1, -1)
        self.index.add(embedding_reshaped)
        self.embeddings.append(embedding)
        self.file_paths.append(file_path)
    
    def search(
        self,
        embedding: np.ndarray,
        k: int = 10,
        threshold: float = 0.85,
    ) -> List[Tuple[Path, float]]:
        """
        Search for similar embeddings
        
        Args:
            embedding: Query embedding
            k: Number of results to return
            threshold: Minimum similarity threshold (0.0-1.0)
        
        Returns:
            List of (file_path, similarity) tuples
        """
        embedding_reshaped = embedding.reshape(1, -1)
        distances, indices = self.index.search(embedding_reshaped, min(k, len(self.file_paths)))
        
        results = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1:  # Invalid result
                continue
            
            # Convert L2 distance to similarity score
            similarity = 1.0 / (1.0 + float(distance))
            
            if similarity >= threshold:
                results.append((self.file_paths[idx], similarity))
        
        return results
    
    def __len__(self) -> int:
        """Number of embeddings in index"""
        return self.index.ntotal
