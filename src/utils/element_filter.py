import json
import random
from typing import Any, Dict, List, Optional, Union


FilterValue = Union[str, List[str]]
FilterDict = Dict[str, FilterValue]


class ElementFilter:
    """
    Generic filter for structured element libraries (music, effects, stickers, etc.)
    """

    def __init__(
        self,
        library: Optional[List[Dict[str, Any]]] = None,
        json_path: Optional[str] = None,
    ):
        self.library: List[Dict[str, Any]] = []

        if library is not None:
            self.library = library
        elif json_path is not None:
            self.update(json_path)
        else:
            raise ValueError("Either library or json_path must be provided")

    def update(
        self,
        json_path: Optional[str] = None,
        library: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Reload or replace the element library."""
        if library is not None:
            self.library = library
            return

        if json_path is None:
            raise ValueError("update() requires json_path or library")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Library JSON must be a list of dicts")

        self.library = data

    def filter(
        self,
        candidates: Optional[List[Dict[str, Any]]] = None,
        filter_include: Optional[FilterDict] = None,
        filter_exclude: Optional[FilterDict] = None,
        fallback_n: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Filter elements by include / exclude conditions.

        - candidates: candidates need to filter
        - include: fields that must match
        - exclude: fields that must NOT match
        - fallback_n: random fallback size if result is empty
        """
        candidates = candidates or self.library
        include = filter_include or {}
        exclude = filter_exclude or {}

        results = []

        for item in candidates:
            if not self._match_include(item, include):
                continue

            if self._match_exclude(item, exclude):
                continue

            results.append(item)

        if not results and fallback_n > 0:
            return random.sample(
                self.library, min(fallback_n, len(self.library))
            )

        return results

    @staticmethod
    def _normalize(value: Any) -> List[str]:
        """Normalize scalar or list values into a list of strings."""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]

    def _match_include(self, item: Dict[str, Any], include: FilterDict) -> bool:
        """All include conditions must be satisfied."""
        for key, expected in include.items():
            if key not in item:
                return False

            item_values = set(self._normalize(item[key]))
            expected_values = set(self._normalize(expected))

            if not item_values & expected_values:
                return False

        return True

    def _match_exclude(self, item: Dict[str, Any], exclude: FilterDict) -> bool:
        """Any exclude condition matched will reject the item."""
        for key, forbidden in exclude.items():
            if key not in item:
                continue

            item_values = set(self._normalize(item[key]))
            forbidden_values = set(self._normalize(forbidden))

            if item_values & forbidden_values:
                return True

        return False