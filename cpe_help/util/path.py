from pathlib import Path


# Base directories for the project

BASE_DIR = (Path(__file__).resolve().parent.parent.parent)
DATA_DIR = BASE_DIR / 'data'


# Utils

def ensure_path(path):
    """
    Ensure that the directories that lead to a path exist

    Parameters
    ----------
    path : str or Path

    Examples
    --------
    Create directories A and B (if they don't exist):

    >>> ensure_path('./A/B/file.py')

    The path can also point to a directory. This line below will have
    the same effect as the one above:

    >>> ensure_path('./A/B/C')
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
