# core/registry.py
import pkgutil
import importlib
from typing import Optional
import os

class Registry:
    def __init__(self):
        self._items = {}


    def register(self, name: Optional[str] = None, override: bool = False):
        """
        Class decorator to register a class in the registry.
        
        Args:
            name (str, optional): Custom registration name. Defaults to module_name.ClassName.
            override (bool): If True, will replace an existing class with the same name. Defaults to False.
        """
        def decorator(cls):
            reg_name = name or f"{cls.__name__}"
            if reg_name in self._items:
                if override:
                    print(f"[Registry] {reg_name} already registered, override=True -> replacing")
                else:
                    raise KeyError(f"[Registry] {reg_name} already registered, override=False")
            
            self._items[reg_name] = cls
            print(f"[Registry] Registered: {reg_name}")
            return cls
        return decorator


    def get(self, name: str, default=None):
        """Get a registered class by name. Returns `default` if not found."""
        return self._items.get(name, default)


    def list(self):
        """Return a list of all registered names."""
        return list(self._items.keys())


    def __len__(self):
        return len(self._items)


    def clear(self):
        """Clear all registered classes."""
        self._items.clear()


    def scan_package(self, package_name: str):
        """
        Scan a Python package and its subpackages, import modules to trigger @REGISTRY.register().
        
        Args:
            package_name (str): Name of the package, e.g., "nodes"
        """
        package = importlib.import_module(package_name)
        if not hasattr(package, "__path__"):
            # Not a package, skip scanning
            print(f"[Registry] {package_name} is not a package, skipping scan")
            return


        for finder, modname, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            importlib.import_module(modname)
            print(f"[Registry] Scanned module: {modname}")


# Global registry instance
NODE_REGISTRY = Registry()