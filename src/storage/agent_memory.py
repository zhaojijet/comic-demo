from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, List, Optional, Tuple
import json
import time

from storage.file import FileCompressor
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ArtifactMeta:
    session_id: str
    artifact_id: str
    node_id: str
    path: str
    summary: Optional[str]
    created_at: float

class ArtifactStore:
    def __init__(self, artifacts_dir: str | Path, session_id: str) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.session_id = session_id
        self.blobs_dir = self.artifacts_dir / session_id
        self.meta_path = self.blobs_dir / "meta.json"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        if (not self.meta_path.exists()) or self.meta_path.stat().st_size == 0:
            self._save_meta_list([])
        
    def _load_meta_list(self) -> List[ArtifactMeta]:
        if not self.meta_path.exists():
            return []
        with self.meta_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return [ArtifactMeta(**item) for item in data]
    
    def _save_meta_list(self, metas: List[ArtifactMeta]):
        with self.meta_path.open("w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in metas], f, ensure_ascii=False, indent=2)

    def _append_meta(self, meta: ArtifactMeta) -> None:
        metas = self._load_meta_list()
        metas.append(meta)
        self._save_meta_list(metas)

    def _is_media_list(self, items) -> bool:
        """Check if it is a valid media list"""
        return isinstance(items, list) and all(isinstance(i, dict) for i in items)

    def _save_single_media(self, item: dict, store_dir: Path, artifact_id: str) -> None:
        """Save a single media file"""
        base64_data = item.pop('base64', None)
        if not base64_data:
            return
        
        file_path = store_dir / item.get('path', '')
        logger.info(f"Saving media: artifact={artifact_id}, path={file_path}")
        
        FileCompressor.decompress_from_string(base64_data, file_path)
        item['path'] = str(file_path)
    
    def _save_media(self, tool_execute_result, store_dir, artifact_id):
        """Process tool execution results and save media files"""
        if not isinstance(tool_execute_result, dict):
            return
        
        for items in tool_execute_result.values():
            if self._is_media_list(items):
                for item in items:
                    self._save_single_media(item, store_dir, artifact_id)
            else:
                self._save_media(items, store_dir, artifact_id)

    def save_result(
        self,
        session_id,
        node_id,
        data: Any,
        search_media_dir: Optional[Path] = None
    ) -> ArtifactMeta:
        # Save intermediate results as JSON and include file information in meta.json for tracking
        create_time = time.time()
        artifact_id = data['artifact_id']
        summary = data['summary']
        tool_excute_result = data['tool_excute_result']
        store_dir = self.blobs_dir / node_id
        file_path = store_dir / f"{artifact_id}.json"

        if not store_dir.exists():
            store_dir.mkdir(parents=True, exist_ok=True)
        
        if search_media_dir is None:
            search_media_dir = store_dir
        self._save_media(tool_excute_result, search_media_dir, artifact_id)
            
        save_data = {
            "payload": tool_excute_result,
            "session_id": session_id,
            "artifact_id": artifact_id,
            'node_id': node_id,
            'create_time': create_time,
        }
        with file_path.open("w", encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        logger.info(f"[Node `{node_id}`] save result to {file_path}")
        
        meta = ArtifactMeta(
            session_id=session_id,
            artifact_id=artifact_id,
            node_id=node_id,
            path=str(file_path),
            summary=summary,
            created_at=create_time,
        )
        self._append_meta(meta)
        return meta

    def load_result(self, artifact_id: str) -> Tuple[ArtifactMeta, Any]:
        metas = self._load_meta_list()
        meta = next((m for m in metas if m.artifact_id == artifact_id), None)

        if meta is None:
            msg = f"artifact `{artifact_id}` not found"
            return None, msg
        
        with open(meta.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return meta, data
    
    def generate_artifact_id(self, node_id):
        unique_id = time.time()
        artifact_id = f"{node_id}_{unique_id}"
        return artifact_id

    def get_latest_meta(
        self,
        *,
        node_id: str,
        session_id: str,
    ) -> Optional[ArtifactMeta]:
        metas = self._load_meta_list()
        candidates = [
            m for m in metas
            if m.node_id == node_id
            and m.session_id == session_id
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.created_at)