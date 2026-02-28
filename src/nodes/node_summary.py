from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional
import logging
from datetime import datetime

from utils.logging import get_logger


@dataclass
class LogEntry:
    """Single log entry"""
    level: str
    message: str
    timestamp: str
    artifact_id: Optional[str] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NodeSummary:
    """
    Node Execution Status Summary - Reuses existing logger module

    Features:
    1. ERROR - Error messages for LLM
    2. WARNING - Warning messages for LLM
    3. DEBUG - Debug information for developers
    4. INFO_LLM - Detailed information for LLM
    5. INFO_USER - Brief information for users

    Capabilities:
    - Reuses get_logger() configuration
    - Hierarchical log storage and extraction
    - Colored console output
    - Log compression functionality
    - Supports artifact tracking
    """
    ERROR: str = "ERROR"
    DEBUG: str = "DEBUG"
    WARNING: str = "WARNING"
    INFO_LLM: str = "INFO_LLM"
    INFO_USER: str = "INFO_USER"
    LOGGER_LEVELS: Tuple[str, ...] = (ERROR, DEBUG, WARNING, INFO_LLM, INFO_USER)


    # Log storage
    log_error: List[LogEntry] = field(default_factory=list)
    log_warn: List[LogEntry] = field(default_factory=list)
    log_info_llm: List[LogEntry] = field(default_factory=list)
    log_info_user: List[LogEntry] = field(default_factory=list)
    log_debug: List[LogEntry] = field(default_factory=list)
    
    # Artifact mapping
    artifact_warnings: Dict[str, List[str]] = field(default_factory=dict)
    artifact_errors: Dict[str, List[str]] = field(default_factory=dict)
    
    # Configuration options
    logger_name: Optional[str] = field(default=None)
    auto_console: bool = field(default=True) # Auto output to console
    summary_levels: Optional[List[str]] = field(default=None)

    # Internal state
    _logger: Optional[logging.Logger] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Initialize logger - reuses get_logger"""
        if self.logger_name is None:
            self.logger_name = "NodeSummary"
        self._logger = get_logger(self.logger_name)
        if self.summary_levels is None:
            self.summary_levels = [self.ERROR, self.WARNING, self.INFO_LLM, self.INFO_USER]

    def _log_to_console(self, level: int, message: str, artifact_id: Optional[str] = None):
        """Output to console (using configured logger)"""
        if not self.auto_console:
            return
        
        prefix = f"[ARTIFACT:{artifact_id}] " if artifact_id else ""
        self._logger.log(level, f"{prefix}{message}")
    
    def add_error(self, message: str, artifact_id: Optional[str] = None, **kwargs: Any):
        """Log error messages - for LLM"""
        entry = LogEntry(
            level=self.ERROR,
            message=message,
            timestamp=datetime.now().isoformat(),
            artifact_id=artifact_id,
            extra_data=kwargs
        )
        self.log_error.append(entry)
        
        if artifact_id:
            self.artifact_errors.setdefault(artifact_id, []).append(message)
        
        self._log_to_console(logging.ERROR, message, artifact_id)
    
    def add_warning(self, message: str, artifact_id: Optional[str] = None, **kwargs: Any):
        """Log warning messages - for LLM"""
        entry = LogEntry(
            level="WARNING",
            message=message,
            timestamp=datetime.now().isoformat(),
            artifact_id=artifact_id,
            extra_data=kwargs
        )
        self.log_warn.append(entry)
        
        if artifact_id:
            self.artifact_warnings.setdefault(artifact_id, []).append(message)
        
        self._log_to_console(logging.WARNING, message, artifact_id)
    
    def info_for_llm(self, message: str, artifact_id: Optional[str] = None, **kwargs: Any):
        """Log detailed information - for LLM"""
        entry = LogEntry(
            level="INFO_LLM",
            message=message,
            timestamp=datetime.now().isoformat(),
            artifact_id=artifact_id,
            extra_data=kwargs
        )
        self.log_info_llm.append(entry)
        self._log_to_console(logging.INFO, f"[{self.INFO_LLM}] {message}", artifact_id)
    
    def info_for_user(self, message: str, artifact_id: Optional[str] = None, **kwargs: Any):
        """Log general information - for users"""
        entry = LogEntry(
            level="INFO_USER",
            message=message,
            timestamp=datetime.now().isoformat(),
            artifact_id=artifact_id,
            extra_data=kwargs
        )
        self.log_info_user.append(entry)
        self._log_to_console(logging.INFO, f"[{self.INFO_USER}] {message}", artifact_id)
    
    def debug_for_dev(self, message: str, artifact_id: Optional[str] = None, **kwargs: Any):
        """Log debug information - for developers"""
        entry = LogEntry(
            level=self.DEBUG,
            message=message,
            timestamp=datetime.now().isoformat(),
            artifact_id=artifact_id,
            extra_data=kwargs
        )
        self.log_debug.append(entry)
        self._log_to_console(logging.DEBUG, f"[{self.DEBUG}] {message}", artifact_id)
    
    def get_logs_by_level(
        self,
        level:str ,
        compress_log: bool=False, # 暂时未实现 TODO
    ) -> Dict[str,Any]:
        self.all_logs = {
            self.ERROR: self.log_error,
            self.DEBUG: self.log_debug,
            self.WARNING: self.log_warn,
            self.INFO_LLM: self.log_info_llm,
            self.INFO_USER: self.log_info_user
        }

        selected_log = self.all_logs[level]

        return self._extract_log(selected_log)
    
    def _extract_log(
        self,
        log_content: List[LogEntry],
    ) -> Dict[str,Any]:
        """
        Extract log content into string format.

        Args:
            log_content: List of log entries
            
        Returns:
            Formatted log string with each log entry on a separate line
        """
        if not log_content:
            return {}
        
        log_lines: List[str] = []
        extra_data_list: List[Dict[str,Any]] = []
        for entry in log_content:
            log_line = f"[{entry.timestamp}] {entry.message}"

            if entry.artifact_id:
                log_line += f" [artifact_id: {entry.artifact_id}]"
            
            log_lines.append(log_line)
            extra_data_list.append(entry.extra_data)
        result: Dict[str,Any] = {
            "log_lines": "\n".join(log_lines),
            "extra_data_list": extra_data_list
        }
        return result
    
    def _get_preview_urls(
        self,
        extra_data_list: List[Dict[str,Any]],
    ) -> List[str]:
        preview_urls: List[str] = []
        for extra_data in extra_data_list:
            preview_urls.extend([str(url) for url in extra_data.get('preview_urls', [])])
        return preview_urls

    def get_summary(
        self,
        artifact_id: str,
        compress_log: bool=True,
        **kwargs: Dict[str,Any],
    ) -> Dict[str,Any]:
        summary: Dict[str,Any] = {}
        preview_urls: List[str] = []
        if self.summary_levels is None:
            return summary

        for level in self.summary_levels:
            summary_log = self.get_logs_by_level(level, compress_log)
            log_lines = summary_log.get('log_lines', "")
            extra_data_list = summary_log.get('extra_data_list', [])
            preview_urls.extend(self._get_preview_urls(extra_data_list))
            summary[level] = log_lines
        
        summary['preview_urls'] = preview_urls
        summary['artifact_id'] = artifact_id
        return summary

    def clear(self):
        """Clear all logs"""
        self.log_error.clear()
        self.log_warn.clear()
        self.log_info_llm.clear()
        self.log_info_user.clear()
        self.log_debug.clear()
        self.artifact_warnings.clear()
        self.artifact_errors.clear()