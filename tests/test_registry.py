"""
Tests for LLMRegistry — pluggable provider registration, lookup, and removal.
"""

import os
import sys
import pytest

# Add src to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_client import LLMRegistry


class FakeConfig:
    """Minimal config-like object for testing (no real API calls)."""

    def __init__(
        self, model="test-model", base_url="https://api.example.com", api_key="test-key"
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = 30.0
        self.max_retries = 2
        self.display_name = ""
        self.description = ""


class TestLLMRegistry:
    def test_register_and_list(self):
        """Registering a provider should make it appear in list_providers."""
        registry = LLMRegistry()
        cfg = FakeConfig(model="gpt-4")
        registry.register(
            "llm", "openai-gpt4", cfg, display_name="GPT-4", description="OpenAI"
        )

        providers = registry.list_providers("llm")
        assert len(providers) == 1
        assert providers[0]["id"] == "openai-gpt4"
        assert providers[0]["display_name"] == "GPT-4"
        assert providers[0]["description"] == "OpenAI"
        assert providers[0]["model"] == "gpt-4"

    def test_register_multiple(self):
        """Multiple providers can be registered under the same category."""
        registry = LLMRegistry()
        registry.register("llm", "a", FakeConfig(model="model-a"), display_name="A")
        registry.register("llm", "b", FakeConfig(model="model-b"), display_name="B")

        providers = registry.list_providers("llm")
        assert len(providers) == 2
        ids = [p["id"] for p in providers]
        assert "a" in ids
        assert "b" in ids

    def test_get_provider(self):
        """get_provider should return the registered entry."""
        registry = LLMRegistry()
        cfg = FakeConfig(model="test")
        registry.register("llm", "test-provider", cfg)

        entry = registry.get_provider("llm", "test-provider")
        assert entry["config"] is cfg
        assert entry["client"] is not None

    def test_get_provider_not_found(self):
        """get_provider should raise KeyError for unknown provider."""
        registry = LLMRegistry()
        with pytest.raises(KeyError):
            registry.get_provider("llm", "nonexistent")

    def test_get_provider_unknown_category(self):
        """get_provider should raise KeyError for unknown category."""
        registry = LLMRegistry()
        with pytest.raises(KeyError):
            registry.get_provider("unknown_category", "some-id")

    def test_set_default_and_get_default(self):
        """set_default + get_default should return the correct provider."""
        registry = LLMRegistry()
        registry.register("llm", "a", FakeConfig(model="a"))
        registry.register("llm", "b", FakeConfig(model="b"))
        registry.set_default("llm", "b")

        entry = registry.get_default("llm")
        assert entry["model"] == "b"

    def test_get_default_fallback(self):
        """get_default should fallback to first provider when no default is set."""
        registry = LLMRegistry()
        registry.register("image_llm", "only-one", FakeConfig(model="img"))

        entry = registry.get_default("image_llm")
        assert entry["model"] == "img"

    def test_get_default_no_providers(self):
        """get_default should raise KeyError when no providers exist."""
        registry = LLMRegistry()
        with pytest.raises(KeyError):
            registry.get_default("llm")

    def test_unregister(self):
        """Unregistered provider should no longer appear in list or be gettable."""
        registry = LLMRegistry()
        registry.register("llm", "to-remove", FakeConfig())
        assert len(registry.list_providers("llm")) == 1

        registry.unregister("llm", "to-remove")
        assert len(registry.list_providers("llm")) == 0

        with pytest.raises(KeyError):
            registry.get_provider("llm", "to-remove")

    def test_unregister_clears_default(self):
        """Unregistering the default provider should clear the default."""
        registry = LLMRegistry()
        registry.register("llm", "a", FakeConfig())
        registry.register("llm", "b", FakeConfig())
        registry.set_default("llm", "a")

        registry.unregister("llm", "a")
        # Default should now fallback to 'b'
        assert registry.get_default_id("llm") == "b"

    def test_unregister_nonexistent(self):
        """Unregistering a non-existent provider should not raise."""
        registry = LLMRegistry()
        registry.unregister("llm", "ghost")  # Should not raise

    def test_get_all_providers_info(self):
        """get_all_providers_info should return structured data for all categories."""
        registry = LLMRegistry()
        registry.register(
            "llm", "chat", FakeConfig(model="chat-model"), display_name="Chat"
        )
        registry.register(
            "image_llm", "img", FakeConfig(model="img-model"), display_name="Img"
        )
        registry.set_default("llm", "chat")
        registry.set_default("image_llm", "img")

        info = registry.get_all_providers_info()
        assert "llm" in info
        assert "image_llm" in info
        assert "video_llm" in info

        assert info["llm"]["default"] == "chat"
        assert len(info["llm"]["providers"]) == 1
        assert info["image_llm"]["default"] == "img"
        assert len(info["video_llm"]["providers"]) == 0

    def test_set_default_invalid(self):
        """set_default with unknown provider should raise KeyError."""
        registry = LLMRegistry()
        with pytest.raises(KeyError):
            registry.set_default("llm", "nonexistent")


class TestLLMRegistryFromSettings:
    """Test LLMRegistry.from_settings with config.toml loading."""

    def test_from_settings_loads_config(self):
        """from_settings should load providers from actual config.toml."""
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.toml")
        if not os.path.exists(config_path):
            pytest.skip("config.toml not found")

        from config import load_settings

        settings = load_settings(config_path)
        registry = LLMRegistry.from_settings(settings)

        # Should have at least one provider per category
        llm_list = registry.list_providers("llm")
        img_list = registry.list_providers("image_llm")
        vid_list = registry.list_providers("video_llm")

        assert len(llm_list) >= 1, f"Expected >=1 llm providers, got {llm_list}"
        assert len(img_list) >= 1, f"Expected >=1 image_llm providers, got {img_list}"
        assert len(vid_list) >= 1, f"Expected >=1 video_llm providers, got {vid_list}"

        # Check default IDs are set correctly
        assert registry.get_default_id("llm") == "deepseek-chat"
        assert registry.get_default_id("image_llm") == "seedream-5"
        assert registry.get_default_id("video_llm") == "seedance-1.5-pro"
