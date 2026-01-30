"""Shim: prefer importing the compiled extension `astock_engine._native` if present."""

try:
    # Try to import the compiled extension placed inside the package as `_native`
    from . import _native as module
except Exception as e:
    raise ImportError(f"Failed to import compiled native extension astock_engine._native: {e}")

# Re-export public symbols from the compiled module
for name in dir(module):
    if not name.startswith("_"):
        globals()[name] = getattr(module, name)
# Also place module in sys.modules under alias 'quant_core_native'
import sys
sys.modules['quant_core_native'] = module
