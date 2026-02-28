"""
recall.py — Vector recall using direct FAISS + sentence-transformers.
No LangChain dependency.
"""

import os
import numpy as np
from typing import Optional


class ComicDemoRecall:
    @staticmethod
    def build_vectorstore(
        data: list[dict],
        field: str = "description",
        model_name: str = "./.comic_demo/models/all-MiniLM-L6-v2",
        device: str = "cpu",
    ):
        """
        Build a FAISS index using sentence-transformers directly.

        Args:
            data: list of dicts
            field: which text field to embed
            model_name: sentence-transformers model identifier
            device: "cpu" or "cuda"

        Returns:
            (index, docs) tuple or None
        """
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            print(f"[RECALL] Missing dependency: {e}")
            return None

        if not os.path.exists(model_name):
            model_name = "sentence-transformers/all-MiniLM-L6-v2"

        model = SentenceTransformer(model_name, device=device)

        # Extract texts and their source dicts
        texts = []
        docs = []
        for item in data:
            text = item.get(field, "")
            if text:
                texts.append(text)
                docs.append(item)

        if not texts:
            print(f"[RECALL] Cannot find field: {field}, return None.")
            return None

        # Encode and build FAISS index
        embeddings = model.encode(texts, normalize_embeddings=True)
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(
            dim
        )  # Inner product (cosine sim with normalized vectors)
        index.add(embeddings.astype(np.float32))

        return (index, docs, model)

    @staticmethod
    def query_top_n(vectorstore, query: str, n: int = 32):
        """
        Query the vectorstore and return top-N original dicts.

        Args:
            vectorstore: (index, docs, model) tuple
            query: query string
            n: number of results

        Returns:
            list of original dict entries
        """
        if vectorstore is None:
            return []

        index, docs, model = vectorstore
        query_embedding = model.encode([query], normalize_embeddings=True)
        scores, indices = index.search(
            query_embedding.astype(np.float32), min(n, len(docs))
        )

        results = []
        for idx in indices[0]:
            if 0 <= idx < len(docs):
                results.append(docs[idx])
        return results
