from utils.register import NODE_REGISTRY

# The module imports will be auto-scanned by the registry,
# so we can import the nodes directly to ensure they are registered.

from .comic_script import ComicScriptNode
from .comic_style import ComicStyleNode
from .comic_character import ComicCharacterNode
from .comic_storyboard import ComicStoryboardNode
from .comic_storyboard_image import ComicStoryboardImageNode
from .comic_image2video import ComicImage2VideoNode

__all__ = [
    "ComicScriptNode",
    "ComicStyleNode",
    "ComicCharacterNode",
    "ComicStoryboardNode",
    "ComicStoryboardImageNode",
    "ComicImage2VideoNode",
]
