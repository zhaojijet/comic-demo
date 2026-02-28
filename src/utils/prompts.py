from pathlib import Path
from typing import Dict, Any
import re

PROMPTS_DIR = Path("prompts/tasks")


class PromptBuilder:
    """Builder for fixed templates with dynamic inputs"""
    
    def __init__(self, prompts_dir: Path = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}
    
    def _load_template(self, task: str, role: str, lang: str) -> str:
        """Load template file"""
        cache_key = f"{task}:{role}:{lang}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # prompts/tasks/filter_clips/zh/system.md
        template_path = self.prompts_dir / task / lang / f"{role}.md"
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        content = template_path.read_text(encoding='utf-8')
        self._cache[cache_key] = content
        return content
    
    def render(self, task: str, role: str, lang: str = "zh", **variables: Any) -> str:
        """Render single template"""
        template = self._load_template(task, role, lang)
        return re.sub(r"{{(.*?)}}", lambda m: str(variables[m.group(1)]), template)
    
    def build(self, task: str, lang: str = "zh", **user_vars: Any) -> Dict[str, str]:
        """
        Build a complete prompt pair
        
        Args:
            task: Task name, e.g., "filter_clips"
            lang: Language, defaults to "zh"
            **user_vars: User input variables (passed to user.md template)
        
        Returns:
            {"system": "...", "user": "..."}
        
        Example:
            builder.build(
                "filter_clips",
                clip_data="...",
                requirements="Keep exciting clips"
            )
        """
        return {
            "system": self.render(task, "system", lang),
            "user": self.render(task, "user", lang, **user_vars)
        }


# Global singleton
_builder = PromptBuilder()


def get_prompt(name: str, lang: str = "zh", **kwargs:Any) -> str:
    """
    获取单个 prompt
    
    Args:
        name: "task.role" 格式，如 "filter_clips.system"
        lang: 语言
        **kwargs: 模板变量
    
    Example:
        get_prompt("filter_clips.system")
        get_prompt("filter_clips.user", clip_data="...")
    """
    parts = name.split(".")
    if len(parts) != 2:
        raise ValueError(f"Invalid format: '{name}', expected 'task/role'")
    
    task, role = parts
    return _builder.render(task, role, lang, **kwargs)


def build_prompts(task: str, lang: str = "zh", **user_vars: Any) -> Dict[str, str]:
    """
    Get a single prompt.
    
    Args:
        name: Format "task.role", e.g., "filter_clips.system"
        lang: Language
        **kwargs: Template variables
    
    Example:
        get_prompt("filter_clips.system")
        get_prompt("filter_clips.user", clip_data="...")
    """
    return _builder.build(task, lang, **user_vars)