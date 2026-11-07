"""Resolve new and existing workspaces without moving or replacing their data."""
from pathlib import Path


def default_data_directory():
    root = Path(__file__).resolve().parent.parent
    current = root / '.lipso-data'
    legacy = root / '.margin-data'
    if not current.exists() and (legacy / 'margin.sqlite3').is_file():
        return legacy
    return current


def workspace_database(directory):
    directory = Path(directory)
    current = directory / 'lipso.sqlite3'
    legacy = directory / 'margin.sqlite3'
    if not current.exists() and legacy.is_file():
        return legacy
    return current
