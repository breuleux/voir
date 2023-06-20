"""Utilities to split a script in a prelude and main part.

See :func:`split_script` for a more thorough description of what we are trying
to do here.
"""

import ast
import io
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType


def resolve_script(script, module_name=None):
    """Return a function that calculates the main body of the script.

    Imports and functions are exec()ed by ``resolve_script``. Only the main body is
    not executed. The separation of the script in two parts is done via
    :func:`split_script`.

    Arguments:
        script: Path to the script.
        module_name: (optional) The name of the module that the script is supposed to
            represent.

    Returns:
        A nullary function that executes the script.
    """
    prep, mainsection = split_script(script)
    mod = ModuleType("__main__")
    glb = vars(mod)
    glb["__file__"] = script
    if module_name:
        glb["__spec__"] = ModuleSpec(name=module_name, loader=None)
    sys.modules["__main__"] = mod
    exec(prep, glb, glb)
    return lambda: exec(mainsection, glb, glb)


def split_script(script):
    """Split code that comes after all function definitions.

    Essentially, we want to be able to instrument functions in the main script, which
    requires evaluating the functions, but we want to do this before executing the main
    code. So we split off code that comes after function definitions so that we can evaluate
    the module and then evaluate that code separately.

    Code between function definitions will be evaluated right away, but the bulk usually
    comes after these definitions (because they need to use them).

    Arguments:
        script: Path to the script.

    Returns:
        A ``(prepare, run)`` tuple such that:

        * ``prepare()`` runs the import statements and function declarations up to the
          first statement.
        * ``run()`` runs the rest of the program after that.
    """

    with io.open_code(script) as f:
        source_code = f.read()

    tree = ast.parse(source_code, mode="exec")

    last_def = 0
    for i, stmt in enumerate(tree.body):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            last_def = i + 1

    mod_before = ast.copy_location(
        ast.Module(
            body=tree.body[:last_def],
            type_ignores=[],
        ),
        tree,
    )

    mod_after = ast.copy_location(
        ast.Module(
            body=tree.body[last_def:],
            type_ignores=[],
        ),
        tree,
    )

    return (
        compile(mod_before, script, "exec"),
        compile(mod_after, script, "exec"),
    )
