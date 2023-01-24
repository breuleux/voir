from collections import Counter, defaultdict


class Plain:
    def __init__(self, x, fmt="{}"):
        self._object = x
        self.fmt = fmt

    def __rich__(self):
        return self.fmt.format(str(self._object))


def make_table(rows):
    from rich.table import Table

    table = Table.grid(padding=(0, 3, 0, 0))
    table.add_column("task", style="bold yellow")
    table.add_column("key", style="bold green")
    table.add_column("value")

    for task, values in rows.items():
        values = dict(values)
        progress = values.pop("progress", None)
        if progress is not None:
            table.add_row(task, "", progress)
            task = ""
        for key, value in values.items():
            table.add_row(task, key, value)
            task = ""  # Avoid displaying the task for the other rows

    return table


def dash(ov):
    """Create a simple terminal dashboard using rich.

    This displays a live table of the last value for everything given.
    """
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.pretty import Pretty
    from rich.progress import (
        BarColumn,
        Progress,
        TextColumn,
        TimeRemainingColumn,
    )

    yield ov.phases.init

    # Current rows are stored here
    rows = defaultdict(dict)

    console = Console()
    event_stats = Counter()
    event_types = {}

    def statistics(data):
        event_stats.update(list(data))
        event_types.update({k: type(v) for k, v in data.items()})

    # This updates the table every time we get new values
    def update_with(values):
        values = dict(values)

        units = values.pop("units", None)
        task = values.pop("task", "default")
        rowgroup = rows[task]

        if (
            isinstance(progress := values.get("progress", None), (list, tuple))
            and len(progress) == 2
        ):
            k = "progress"
            completed, total = progress
            if k not in rowgroup:
                progress_bar = Progress(
                    BarColumn(),
                    TimeRemainingColumn(),
                    TextColumn("({task.completed}/{task.total})"),
                )
                progress_bar._task = progress_bar.add_task(k)
                rowgroup[k] = progress_bar
            progress_bar = rowgroup[k]
            progress_bar.update(progress_bar._task, completed=completed, total=total)
            return

        for k, v in values.items():
            if k.startswith("$"):
                continue
            if k in rowgroup:
                rowgroup[k]._object = v
            else:
                if units:
                    rowgroup[k] = Plain(v, f"{{}} {units}")
                else:
                    rowgroup[k] = Pretty(v)

        if event_stats:
            strings = [
                f"{n}x {k} ({event_types[k].__name__})" for k, n in event_stats.items()
            ]
            lv.update(Panel(Group(make_table(rows), ", ".join(strings))))
        else:
            lv.update(Panel(make_table(rows)))

    panel = Panel("")

    ov.log >> update_with
    ov.given >> statistics

    with Live(panel, refresh_per_second=4, console=console) as lv:
        yield ov.phases.finalize(-1000)
