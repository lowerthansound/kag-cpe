"""
Preparation tasks for doit

The tasks present here are required for the creation of tasks in the
main dodo.py file.
"""

import doit

from cpe_help import Department, util
from cpe_help.tiger import get_tiger


DATA_DIR = util.path.DATA_DIR
BASE_DIRECTORIES = [
    # TODO: think about these

    DATA_DIR / 'kaggle',

    DATA_DIR / 'input',
    DATA_DIR / 'input' / 'department',

    DATA_DIR / 'output',
    DATA_DIR / 'output' / 'department',

    DATA_DIR / 'department',
    DATA_DIR / 'tiger',
]


def _create_base_directories():
    """
    Create base data directories
    """
    for dir in BASE_DIRECTORIES:
        util.file.maybe_mkdir(dir)


def task_create_base_directories():
    """
    Create base data directories
    """
    return {
        'targets': BASE_DIRECTORIES,
        'actions': [_create_base_directories],
        'uptodate': [True],
    }


@doit.create_after('create_base_directories')
def task_create_department_directories():
    """
    Create departments' directories
    """
    depts = Department.list()
    for dept in depts:
        yield {
            'name': dept.name,
            'targets': dept.directories,
            'actions': [dept.create_directories],
            'uptodate': [True],
        }


@doit.create_after('create_base_directories')
def task_create_tiger_directories():
    """
    Create TIGER's directories
    """
    tiger = get_tiger()
    return {
        'targets': tiger.directories,
        'actions': [tiger.create_directories],
        'uptodate': [True],
    }
