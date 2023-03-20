import ast
import io


def split_script(script):
    """Split code that comes after all function definitions.

    Essentially, we want to be able to instrument functions in the main script, which
    requires evaluating the functions, but we want to do this before executing the main
    code. So we split off code that comes after function definitions so that we can evaluate
    the module and then evaluate that code separately.

    Code between function definitions will be evaluated right away, but the bulk usually
    comes after these definitions (because they need to use them).
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
