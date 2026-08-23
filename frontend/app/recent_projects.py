import json
from pathlib import Path


APP_DIR = Path.home() / ".config" / "QuantumStudio"
RECENT_FILE = APP_DIR / "recent_projects.json"

MAX_RECENT_PROJECTS = 10


def _ensure_directory():
    APP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def load_recent_projects():
    """
    Return recently opened Quantum Studio project paths.

    Invalid or deleted projects are automatically removed.
    """

    _ensure_directory()

    if not RECENT_FILE.exists():
        return []

    try:

        with RECENT_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

    except (
        OSError,
        json.JSONDecodeError,
    ):

        return []

    paths = []

    for item in data:

        path = Path(item).expanduser()

        if path.exists() and path.suffix == ".qs":

            paths.append(
                str(path.resolve())
            )

    # Remove duplicates while preserving order.
    unique = []

    for path in paths:

        if path not in unique:
            unique.append(path)

    return unique[:MAX_RECENT_PROJECTS]


def save_recent_projects(paths):
    """
    Persist the recent project list.
    """

    _ensure_directory()

    unique = []

    for item in paths:

        path = Path(item).expanduser()

        if (
            path.exists()
            and path.suffix == ".qs"
            and str(path.resolve()) not in unique
        ):

            unique.append(
                str(path.resolve())
            )

    unique = unique[:MAX_RECENT_PROJECTS]

    with RECENT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            unique,
            file,
            indent=4,
        )


def add_recent_project(path):
    """
    Add a project to the top of the recent list.
    """

    path = Path(path).expanduser().resolve()

    if not path.exists():
        return

    if path.suffix != ".qs":
        return

    current = load_recent_projects()

    path_string = str(path)

    current = [
        item
        for item in current
        if item != path_string
    ]

    current.insert(
        0,
        path_string,
    )

    save_recent_projects(
        current
    )


def remove_recent_project(path):
    """
    Remove a project from the recent list.
    """

    path = str(
        Path(path)
        .expanduser()
        .resolve()
    )

    current = load_recent_projects()

    current = [
        item
        for item in current
        if item != path
    ]

    save_recent_projects(
        current
    )


def clear_recent_projects():
    """
    Clear the entire recent-project list.
    """

    _ensure_directory()

    if RECENT_FILE.exists():
        RECENT_FILE.unlink()
