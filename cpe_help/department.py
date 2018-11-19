"""
This is the main file for dealing with departments

Probably will become the main file of the project.
"""

from importlib import import_module

import geopandas as gpd
import pandas as pd
import us

# TODO clean imports

from cpe_help import util
from cpe_help.acs import get_acs
from cpe_help.tiger import get_tiger
from cpe_help.util import crs
from cpe_help.util.io import (
    load_json,
    load_zipshp,
    save_json,
    save_zipshp,
)
from cpe_help.util.configuration import get_acs_variables
from cpe_help.util.interpolation import weighted_areas
from cpe_help.util.path import DATA_DIR, maybe_mkdir, maybe_rmfile


class InputError(Exception):
    pass


class Department():
    """
    Represents a police department

    All department related functionality will be here.
    """

    @property
    def path(self):
        return DATA_DIR / 'departments' / self.name

    @property
    def directories(self):
        return [
            self.path,
            self.external_dir,
            self.raw_dir,
            self.preprocessed_dir,
            self.processed_dir,
        ]

    @property
    def external_dir(self):
        return self.path / 'external'

    @property
    def raw_dir(self):
        return self.path / 'raw'

    @property
    def preprocessed_dir(self):
        return self.path / 'preprocessed'

    @property
    def processed_dir(self):
        return self.path / 'processed'

    @property
    def external_acs_path(self):
        return self.external_dir / 'ACS'

    @property
    def external_shapefile_path(self):
        return self.external_dir / 'shapefiles'

    @property
    def preprocessed_shapefile_path(self):
        return self.preprocessed_dir / 'shapefile.zip'

    @property
    def guessed_state_path(self):
        return self.path / 'guessed_state.json'

    @property
    def guessed_counties_path(self):
        return self.path / 'guessed_counties.json'

    @property
    def guessed_city_path(self):
        return self.path / 'guessed_city.json'

    @property
    def tract_values_path(self):
        return self.raw_dir / 'tract_values.pkl'

    @property
    def bg_values_path(self):
        return self.raw_dir / 'bg_values.pkl'

    @property
    def census_tracts_path(self):
        return self.processed_dir / 'census_tracts.geojson'

    @property
    def block_groups_path(self):
        return self.processed_dir / 'block_groups.geojson'

    @property
    def police_precincts_path(self):
        return self.processed_dir / 'police_precincts.geojson'

    @property
    def city_path(self):
        return self.processed_dir / 'city.geojson'

    def __new__(cls, name):
        """
        Create a new department object

        This method makes the Department constructor return a specific
        subclass, based on the name.

        Parameters
        ----------
        name : str
            Represents the department name, e.g. '37-00027' for Austin.

        Returns
        -------
        Department object
        """
        # avoid direct instantiation of subclasses
        assert cls == Department

        name = name.replace('-', '')
        module_name = f"cpe_help.departments.department{name}"
        class_name = f"Department{name}"

        try:
            # instantiate specific subclass
            mod = import_module(module_name)
            klass = getattr(mod, class_name)
            return super().__new__(klass)
        except ModuleNotFoundError:
            # no specific subclass
            # use generic version Department
            return super().__new__(cls)

    def __init__(self, name):
        """
        Initialize a new department object

        Parameters
        ----------
        name : str
            Represents the department name, e.g. '37-00027' for Austin.
        """
        self.name = name

    def __repr__(self):
        return "{klass}({name!r})".format(
            klass=type(self).__name__,
            name=self.name,
        )

    # utils

    @property
    def city(self):
        """
        Return a string representing my city's name

        Examples
        --------
        >>> dept = Department('11-00091')
        >>> dept.city
        'Boston'
        """
        return self.load_guessed_city()

    def load_city_metadata(self):
        """
        Load data associated with my city from TIGER

        Returns
        -------
        geopandas.GeoDataFrame
            A 1-lined GeoDataFrame whose only entry corresponds to the
            requested metadata.
        """
        tiger = get_tiger()
        places = tiger.load_place_boundaries(self.state.fips)
        places = places[places['NAME'] == self.city]
        assert places.shape[0] == 1
        return places

    @property
    def state(self):
        """
        Return a us.states.State object representing my state

        Reference:

        https://github.com/unitedstates/python-us

        Examples
        --------
        >>> dept = Department('11-00091')
        >>> dept.state
        <State:Massachusetts>
        """
        fips = self.load_guessed_state()
        return us.states.lookup(fips)

    @property
    def location(self):
        """
        Return a string representing my location

        Examples
        --------
        >>> dept = Department('11-00091')
        >>> dept.location
        'Boston, MA'
        """
        return '{}, {}'.format(
            self.city,
            self.state.abbr,
        )

    @property
    def full_name(self):
        """
        Return a string representing my name and location

        Examples
        --------
        >>> dept = Department('11-00091')
        >>> dept.full_name
        '11-00091 (Boston, MA)'
        """
        return '{} ({})'.format(
            self.name,
            self.location,
        )

    @classmethod
    def sample(cls):
        """
        Return one sample department from the list
        """
        return list_departments()[0]

    # doit actions

    def create_directories(self):
        """
        Create the directories where files will be saved
        """
        for dir in self.directories:
            maybe_mkdir(dir)

    def preprocess_shapefile(self):
        """
        Preprocess the raw shapefile for this department

        The default implementation (Department) copies from source to
        destination, while setting the Coordinate Reference System to
        the default (defined at util.crs.DEFAULT).

        Note that the source is a usual shapefile, while the destination
        is a shapefile in a zip archive (a single file facilitates
        pipelining).
        """
        raw = self.load_external_shapefile()

        if not raw.crs:
            msg = f"Department {self.name} has no projection defined"
            raise InputError(msg)
        pre = raw.to_crs(crs.DEFAULT)

        self.save_preprocessed_shapefile(pre)

    def remove_preprocessed_shapefile(self):
        maybe_rmfile(self.preprocessed_shapefile_path)

    def guess_state(self):
        """
        Guess the state this department is in
        """
        tiger = get_tiger()
        states = tiger.load_state_boundaries()
        states = states.set_index('GEOID')

        shape = self.load_preprocessed_shapefile()
        shape = shape.to_crs(states.crs)
        union = shape.unary_union

        intersecting = [ix for ix, geom in states.geometry.iteritems()
                        if union.intersects(geom)]
        assert len(intersecting) == 1

        self.save_guessed_state(intersecting[0])

    def remove_guessed_state(self):
        maybe_rmfile(self.guessed_state_path)

    def guess_counties(self):
        """
        Guess the counties that make part of this city and department
        """
        tiger = get_tiger()
        counties = tiger.load_county_boundaries()
        counties = counties.set_index('COUNTYFP')

        shape1 = self.load_preprocessed_shapefile()
        shape1 = shape1.to_crs(counties.crs)
        shape1 = shape1.unary_union

        shape2 = self.load_city_boundaries()
        shape2 = shape2.to_crs(counties.crs)
        shape2 = shape2.unary_union

        union = shape1.union(shape2)

        intersecting = [ix for ix, geom in counties.geometry.iteritems()
                        if union.intersects(geom)]
        self.save_guessed_counties(intersecting)

    def remove_guessed_counties(self):
        maybe_rmfile(self.guessed_counties_path)

    def guess_city(self):
        """
        Guess the city this department is in
        """
        tiger = get_tiger()

        places = tiger.load_place_boundaries(self.state.fips)
        police = self.load_preprocessed_shapefile()
        police = police.to_crs(places.crs)

        # we want to avoid statistical entities
        # ref: https://www.census.gov/geo/reference/funcstat.html
        places = places[places['FUNCSTAT'] == 'A']

        # speeding things up
        places = places[places.intersects(police.unary_union)]

        proj = crs.equal_area_from_geodf(places)
        places = places.to_crs(proj)
        police = police.to_crs(proj)

        idx = places.intersection(police.unary_union).area.idxmax()
        city_name = places.loc[idx, 'NAME']

        self.save_guessed_city(city_name)

    def remove_guessed_city(self):
        maybe_rmfile(self.guessed_city_path)

    def download_tract_values(self):
        """
        Download ACS values for relevant census tracts

        Relevant census tracts are those inside counties that compose
        this department.
        """
        acs = get_acs()
        state = self.load_guessed_state()
        counties = self.load_guessed_counties()
        variables = get_acs_variables()

        # must make 1 request per county
        frames = []
        for county in counties:
            df = acs.data(
                variables,
                geography='tract',
                inside='state:{} county:{}'.format(state, county),
            )
            frames.append(df)
        frame = pd.concat(frames)
        self.save_tract_values(frame)

    def remove_tract_values(self):
        maybe_rmfile(self.tract_values_path)

    def download_bg_values(self):
        """
        Download ACS values for relevant block groups

        Relevant block groups are those inside counties that compose
        this department.
        """
        acs = get_acs()
        state = self.load_guessed_state()
        counties = self.load_guessed_counties()
        variables = get_acs_variables()

        # must make 1 request per county
        frames = []
        for county in counties:
            df = acs.data(
                variables,
                geography='block group',
                inside='state:{} county:{}'.format(state, county),
            )
            frames.append(df)
        frame = pd.concat(frames)
        self.save_bg_values(frame)

    def remove_bg_values(self):
        maybe_rmfile(self.bg_values_path)

    def process_census_tracts(self):
        """
        Merge census tract values with geography (for intersecting
        counties)
        """
        tiger = get_tiger()

        state = self.load_guessed_state()
        counties = self.load_guessed_counties()

        boundaries = tiger.load_tract_boundaries(state)
        boundaries = boundaries[
            (boundaries['STATEFP'] == state) &
            (boundaries['COUNTYFP'].isin(counties))
        ]
        values = self.load_tract_values()
        assert boundaries.shape[0] == values.shape[0]

        index1 = ['STATEFP', 'COUNTYFP', 'TRACTCE']
        to_join1 = boundaries.set_index(index1)
        to_join1 = to_join1[['geometry']]

        index2 = ['state', 'county', 'tract']
        to_join2 = values.set_index(index2)

        to_join1.index.names = to_join2.index.names
        joined = to_join1.join(to_join2)
        assert joined.shape[0] == to_join1.shape[0]

        # move geometry column to end
        geometry = joined.pop('geometry')
        joined['geometry'] = geometry

        # GeoDataFrame.to_file() ignores indexes
        joined = joined.reset_index()

        self.save_census_tracts(joined)

    def remove_census_tracts(self):
        maybe_rmfile(self.census_tracts_path)

    def process_block_groups(self):
        """
        Merge block group values with geography (intersecting counties)
        """
        tiger = get_tiger()

        state = self.load_guessed_state()
        counties = self.load_guessed_counties()

        boundaries = tiger.load_bg_boundaries(state)
        boundaries = boundaries[
            (boundaries['STATEFP'] == state) &
            (boundaries['COUNTYFP'].isin(counties))
        ]
        values = self.load_bg_values()
        assert boundaries.shape[0] == values.shape[0]

        index1 = ['STATEFP', 'COUNTYFP', 'TRACTCE', 'BLKGRPCE']
        to_join1 = boundaries.set_index(index1)
        to_join1 = to_join1[['geometry']]

        index2 = ['state', 'county', 'tract', 'block group']
        to_join2 = values.set_index(index2)

        to_join1.index.names = to_join2.index.names
        joined = to_join1.join(to_join2)
        assert joined.shape[0] == boundaries.shape[0]

        # move geometry column to end
        geometry = joined.pop('geometry')
        joined['geometry'] = geometry

        # GeoDataFrame.to_file() ignores indexes
        joined = joined.reset_index()

        self.save_block_groups(joined)

    def remove_block_groups(self):
        maybe_rmfile(self.block_groups_path)

    def process_police_precincts(self):
        """
        Generate police precincts file

        This currently made as a join between the externally provided
        shapefiles (proprocessed_shapefile) data and data that comes
        from the Census interpolated into the relevant regions.
        """
        police = self.load_preprocessed_shapefile()
        bgs = self.load_block_groups()
        new_police = weighted_areas(bgs, police.geometry)
        joined = police.join(new_police.drop('geometry', axis=1))
        self.save_police_precincts(joined)

    def remove_police_precincts(self):
        maybe_rmfile(self.police_precincts_path)

    def process_city(self):
        """
        Generate city file

        The city file is a one-entry geojson file that, alongside
        geography information, has general statistics from the city that
        were retrieved from the U.S. Census.
        """
        city = self.load_city_boundaries()
        bgs = self.load_block_groups()
        new_city = util.interpolation.weighted_areas(bgs, city.geometry)
        joined = city.join(new_city.drop('geometry', axis=1))
        self.save_city(joined)

    def remove_city(self):
        maybe_rmfile(self.city_path)

    # input

    def load_external_shapefile(self):
        path = str(self.external_shapefile_path)
        return util.io.load_shp(path)

    def load_preprocessed_shapefile(self):
        return load_zipshp(self.preprocessed_shapefile_path)

    def load_guessed_state(self):
        return load_json(self.guessed_state_path)

    def load_guessed_counties(self):
        return load_json(self.guessed_counties_path)

    def load_guessed_city(self):
        return load_json(self.guessed_city_path)

    def load_tract_values(self):
        return pd.read_pickle(self.tract_values_path)

    def load_bg_values(self):
        return pd.read_pickle(self.bg_values_path)

    def load_block_groups(self):
        return util.io.load_geojson(self.block_groups_path)

    def load_census_tracts(self):
        return util.io.load_geojson(self.census_tracts_path)

    def load_police_precincts(self):
        return util.io.load_geojson(self.police_precincts_path)

    def load_city(self):
        return util.io.load_geojson(self.city_path)

    # output

    def save_preprocessed_shapefile(self, df):
        save_zipshp(df, self.preprocessed_shapefile_path)

    def save_guessed_state(self, geoid):
        save_json(geoid, self.guessed_state_path)

    def save_guessed_counties(self, lst):
        save_json(lst, self.guessed_counties_path)

    def save_guessed_city(self, city_name):
        save_json(city_name, self.guessed_city_path)

    def save_tract_values(self, df):
        df.to_pickle(self.tract_values_path)

    def save_bg_values(self, df):
        df.to_pickle(self.bg_values_path)

    def save_block_groups(self, df):
        util.io.save_geojson(df, self.block_groups_path)

    def save_census_tracts(self, df):
        util.io.save_geojson(df, self.census_tracts_path)

    def save_police_precincts(self, df):
        util.io.save_geojson(df, self.police_precincts_path)

    def save_city(self, df):
        util.io.save_geojson(df, self.city_path)


class DepartmentCollection():
    """
    Represents a collection of all departments in the data
    """
    @property
    def path(self):
        return DATA_DIR / 'departments'

    @property
    def list_of_states_path(self):
        return self.path / 'list_of_states.json'

    # util

    def list(self):
        names = [x.name for x in self.path.iterdir() if x.is_dir()]
        return [Department(name) for name in sorted(names)]

    # doit actions

    def create_list_of_states(self):
        """
        Create a list of states where the departments are

        (to later retrieve census tracts from those)
        """
        states = [dept.load_guessed_state() for dept in self.list()]
        states = set(states)
        states = sorted(states)
        self.save_list_of_states(states)

    def remove_list_of_states(self):
        """
        Remove the list of states
        """
        maybe_rmfile(self.list_of_states_path)

    # input/output

    def load_list_of_states(self):
        return load_json(self.list_of_states_path)

    def save_list_of_states(self, lst):
        save_json(lst, self.list_of_states_path)


def list_departments():
    """
    Returns a list with all available Department's

    This is a shortcut.
    """
    return DepartmentCollection().list()


def list_states():
    """
    Returns a list with all states where the departments are
    """
    dept_coll = DepartmentCollection()
    return dept_coll.load_list_of_states()
