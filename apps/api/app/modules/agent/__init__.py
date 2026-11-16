__all__ = [
    "HybridToolExecutor",
    "build_hybrid_tool_executor",
]


def __getattr__(name):
    if name in __all__:
        from .hybrid_adapter import HybridToolExecutor, build_hybrid_tool_executor

        return {
            "HybridToolExecutor": HybridToolExecutor,
            "build_hybrid_tool_executor": build_hybrid_tool_executor,
        }[name]
    raise AttributeError(name)
