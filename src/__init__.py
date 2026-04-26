"""
src 包入口。

注意：
为避免在导入 `src` 时就加载重量级可选依赖（例如天文计算相关的 astropy），
这里不再进行子模块的“自动导入”。需要使用哪个子模块，请显式导入：

    from src import celestial
    from src import qweather_interaction
"""

__all__: list[str] = []
