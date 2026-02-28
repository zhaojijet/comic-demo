import shutil
import uuid
import time
import threading
from pathlib import Path
from typing import Callable, Optional

from utils.logging import get_logger
from storage.agent_memory import ArtifactStore

logger = get_logger(__name__)


class SessionLifecycleManager:
    """
    Lifecycle Manager
    Responsibilities:
    1. Create and clean up artifacts directory
    2. Create and clean up .server_cache directory
    3. Produce ArtifactStore instances
    """
    def __init__(
        self, 
        artifacts_root: str | Path, 
        cache_root: str | Path, 
        max_items: int = 256,
        retention_days: int = 3,
        enable_cleanup: bool = False,
    ):
        self.artifacts_root = Path(artifacts_root)
        self.cache_root = Path(cache_root)
        self.max_items = max_items
        self.retention_days = retention_days
        self.enable_cleanup = enable_cleanup

        # Ensure project root directory exists
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        
        # Concurrency control: prevent multiple cleanup threads from interfering with each other
        self._cleanup_lock = threading.Lock()
        self._is_cleaning = False

    def _safe_rmtree(self, path: Path):
        """More robust directory deletion method"""
        def onerror(func, path, exc_info):
            import stat
            import os
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
                func(path)
            else:
                logger.warning(f"[Lifecycle] Failed to remove {path}: {exc_info[1]}")

        if path.is_dir():
            shutil.rmtree(path, onerror=onerror)
        else:
            path.unlink(missing_ok=True)

    def _cleanup_dir(self, target_dir: Path, exclude_name: str = None, filter_func: Callable[[Path], bool] = None):
        """
        Cleanup strategy: remove expired items first, then enforce quantity limit
        """
        if not target_dir.exists():
            return

        try:
            # 1. Calculate expiration timestamp cutoff
            now = time.time()
            # 86400 second = 1 day
            cutoff_time = now - (self.retention_days * 86400) 

            valid_items = []      # 没过期且合法的 Session
            expired_items = []    # 已经过期的 Session

            # 2. Iterate and check
            for p in target_dir.iterdir():
                # (A) Filter check (is it a directory, is it a UUID)
                if filter_func and not filter_func(p):
                    continue

                # (B) Protect currently in-use items (don't delete even if expired, to prevent running tasks from crashing)
                if exclude_name and p.name == exclude_name:
                    continue
                
                # (C) Check last modification time
                mtime = p.stat().st_mtime
                if mtime < cutoff_time:
                    # Exceeded retention_days, add to expired list
                    expired_items.append(p)
                else:
                    # Not yet expired, add to valid list
                    valid_items.append(p)

            # 3. Phase 1: Delete all expired items
            for item in expired_items:
                logger.info(f"[Lifecycle] Deleting expired item (> {self.retention_days} days): {item.name}")
                self._safe_rmtree(item)

            # 4. Phase 2: If remaining items still exceed max_items, delete the oldest
            if len(valid_items) > self.max_items:
                # Sort by time (oldest -> newest)
                valid_items.sort(key=lambda x: x.stat().st_mtime)
                
                num_to_delete = len(valid_items) - self.max_items
                logger.info(f"[Lifecycle] Item count {len(valid_items)} > limit {self.max_items}. Deleting {num_to_delete} oldest.")
                
                for item in valid_items[:num_to_delete]:
                    logger.info(f"[Lifecycle] Deleting excess item: {item.name}")
                    self._safe_rmtree(item)

        except Exception as e:
            logger.error(f"[Lifecycle] Error cleaning {target_dir}: {e}")

    def cleanup_expired_sessions(self, current_session_id: Optional[str] = None):
        """
        Trigger cleanup for all managed directories
        Use lock to ensure only one cleanup task runs at a time
        """
        if not self.enable_cleanup:
            return
        
        # Try acquiring the lock; if it fails (cleanup in progress), skip this round
        # Non-blocking approach suitable for high-frequency calls
        if not self._cleanup_lock.acquire(blocking=False):
            return

        def artifact_filter(p: Path) -> bool:
            return p.is_dir() and self._is_valid_session_id(p.name)

        try:
            self._is_cleaning = True
            # Clean up artifacts
            self._cleanup_dir(self.artifacts_root, exclude_name=current_session_id, filter_func=artifact_filter)
            # Clean up server_cache
            self._cleanup_dir(self.cache_root, exclude_name=current_session_id, filter_func=artifact_filter)
        finally:
            self._is_cleaning = False
            self._cleanup_lock.release()

    def _is_valid_session_id(self, name: str) -> bool:
        # 1. Quick filter: length must be 32 characters
        if len(name) != 32:
            return False
            
        # 2. Try to parse as UUID
        try:
            val = uuid.UUID(name)
            return val.hex == name and val.version == 4
        except (ValueError, AttributeError):
            return False

        

    def get_artifact_store(self, session_id: str) -> ArtifactStore:
        # 1. Trigger cleanup asynchronously
        # Even if called concurrently here, the non-blocking lock inside cleanup_expired_sessions handles concurrency issues
        if self.enable_cleanup:
            threading.Thread(
                target=self.cleanup_expired_sessions, 
                args=(session_id,), 
                daemon=True,
                name=f"CleanupThread-{session_id}"
            ).start()
        
        # 2. Return Store instance
        return ArtifactStore(self.artifacts_root, session_id)