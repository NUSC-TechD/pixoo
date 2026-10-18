import importlib
import inspect
import pkgutil

import pixoo_server


def test_every_project_class_has_a_docstring() -> None:
    undocumented: list[str] = []

    for module_info in pkgutil.walk_packages(
        pixoo_server.__path__, prefix=f"{pixoo_server.__name__}."
    ):
        module = importlib.import_module(module_info.name)
        for _, class_ in inspect.getmembers(module, inspect.isclass):
            if class_.__module__ == module.__name__ and not (class_.__doc__ or "").strip():
                undocumented.append(f"{module.__name__}.{class_.__name__}")

    assert undocumented == []
