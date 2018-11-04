"""
Preparation tasks for doit

The tasks present here are required for the creation of tasks in the
main dodo.py file.
"""

import doit
import doit.tools

from cpe_help import Department
from cpe_help.tiger import get_tiger
from cpe_help.util.doit_tasks import TaskHelper
from cpe_help.util.path import DATA_DIR, maybe_mkdir, maybe_rmtree


BASE_DIRECTORIES = [
    DATA_DIR / 'departments',
    DATA_DIR / 'inputs',
    DATA_DIR / 'tiger',
]

INPUTS_DIR = DATA_DIR / 'inputs'
KAGGLE_ZIPFILE = INPUTS_DIR / 'data-science-for-good.zip'
DEPARTMENTS_DIR = INPUTS_DIR / 'cpe-data'


# helper/actions

class InputDepartment():
    """
    I represent a Department that was just unzipped
    """

    @property
    def path(self):
        return DEPARTMENTS_DIR / f'Dept_{self.name}'

    @property
    def acs_path(self):
        return self.path / f'{self.name}_ACS_data'

    @property
    def shp_path(self):
        return self.path / f'{self.name}_Shapefiles'

    @property
    def acs_files(self):
        return list(self.acs_path.glob(f'**/*_with_ann.csv'))

    @property
    def other_files(self):
        return [x for x in self.path.iterdir() if x.is_file()]

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'InputDepartment(name={self.name!r})'

    def to_department(self):
        return Department(self.name)

    @classmethod
    def from_path(cls, path):
        return InputDepartment(path.name[5:])

    @classmethod
    def list(cls):
        return [cls.from_path(x)
                for x in DEPARTMENTS_DIR.iterdir()
                if x.is_dir()]


def create_base_directories():
    """
    Create base data directories
    """
    for dir in BASE_DIRECTORIES:
        maybe_mkdir(dir)


def preprocess_inputs():
    """
    Fix errors in the raw department data
    """
    dept1 = InputDepartment('35-00016')
    maybe_rmtree(dept1.acs_path / '35-00016_employment')

    dept2 = InputDepartment('11-00091')
    maybe_rmtree(dept2.acs_path / '11-00091_ACS_race-age-sex')


# basic tasks

def task_create_base_directories():
    """
    Create base data directories
    """
    return {
        'targets': BASE_DIRECTORIES,
        'actions': [create_base_directories],
        'uptodate': [True],
    }


@doit.create_after('create_base_directories')
def task_download_inputs():
    """
    Retrieve raw departments data from Kaggle
    """
    return {
        'actions': [[
            'kaggle',
            'datasets',
            'download',
            '-d',
            'center-for-policing-equity/data-science-for-good',
            '-p',
            'data/inputs'
        ]],
        'targets': [KAGGLE_ZIPFILE],
        'uptodate': [True],
    }


@doit.create_after('download_inputs')
def task_unzip_inputs():
    """
    Unzip raw departments data from Kaggle
    """
    return TaskHelper.unzip(KAGGLE_ZIPFILE, DEPARTMENTS_DIR)


@doit.create_after('unzip_inputs')
def task_preprocess_inputs():
    """
    Fix errors in the raw department data
    """
    return {
        'actions': [preprocess_inputs],
    }


# tiger tasks

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


# department tasks

@doit.create_after('preprocess_inputs')
def task_create_department_directories():
    """
    Create departments' directories
    """
    depts = InputDepartment.list()
    depts = [d.to_department() for d in depts]
    for dept in depts:
        yield {
            'name': dept.name,
            'targets': dept.directories,
            'actions': [dept.create_directories],
            'uptodate': [True],
        }
