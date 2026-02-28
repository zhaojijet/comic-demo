"""
skills_io.py — Skill loading and management.
No LangChain dependency.
"""

import aiofiles
from pathlib import Path
from typing import Optional

from agent_loop import ToolDef
from utils.logging import get_logger

logger = get_logger(__name__)


async def load_skills(
    skill_dir: str = ".comic_demo/skills",
) -> list[ToolDef]:
    """
    Discover and load skills from the skill directory.
    Returns a list of ToolDef objects.

    Note: If skillkit is available, skills are loaded through it.
    Otherwise, returns an empty list.
    """
    skill_path = Path(skill_dir)
    if not skill_path.exists():
        logger.info(f"[Skills] Skill directory not found: {skill_dir}")
        return []

    tools = []
    try:
        from skillkit import SkillManager

        manager = SkillManager(skill_dir=skill_dir)
        await manager.adiscover()

        # Convert skills to ToolDef format
        for skill in manager.skills:
            name = getattr(skill, "name", "unknown_skill")
            description = getattr(skill, "description", "")
            schema = getattr(
                skill, "input_schema", {"type": "object", "properties": {}}
            )

            async def _make_caller(s):
                async def caller(**kwargs):
                    result = await s.arun(**kwargs)
                    return str(result) if result else ""

                return caller

            tools.append(
                ToolDef(
                    name=name,
                    description=description,
                    parameters=(
                        schema
                        if isinstance(schema, dict)
                        else {"type": "object", "properties": {}}
                    ),
                    callable=await _make_caller(skill),
                )
            )
        logger.info(f"[Skills] Loaded {len(tools)} skills from {skill_dir}")

    except ImportError:
        logger.info("[Skills] skillkit not available, skipping skill loading")
    except Exception as e:
        logger.warning(f"[Skills] Error loading skills: {e}")

    return tools


async def dump_skills(
    skill_name: str = "",
    skill_dir: str = "",
    skill_content: str = "",
    **kwargs,
):
    clean_name = skill_name.strip()
    if not clean_name:
        return {"status": "error", "message": "skill_name cannot be empty"}

    base_path = Path.cwd()
    target_path = base_path / skill_dir / f"cutskill_{clean_name}"
    target_file_path = target_path / "SKILL.md"

    try:
        final_path = target_file_path.resolve()
        if base_path not in final_path.parents:
            return {
                "status": "error",
                "message": f"Security Alert: Writing to paths outside the project directory is forbidden: {final_path}",
            }
    except Exception as e:
        return {"status": "error", "message": f"Path resolution error: {str(e)}"}

    try:
        if not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(final_path, mode="w", encoding="utf-8") as f:
            await f.write(skill_content)

        return {
            "status": "success",
            "message": f"Skill '{clean_name}' successfully created.",
            "dir_path": str(target_path),
            "file_path": str(final_path),
            "size_bytes": len(skill_content.encode("utf-8")),
        }

    except PermissionError:
        return {
            "status": "error",
            "message": f"Permission denied: Cannot write to directory {target_path}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Write operation failed: {str(e)}"}
