import warnings

import pandas
import requests

from cpe_help import util


# ACS variables that should not be converted to numbers
_NONNUMERIC_VARS = [
    'NAME',

]


class ACS(object):
    """
    I will help with the retrieval of data from the ACS web API

    Note that only the 5 year estimates will be available through this
    class.
    """
    def __init__(self, year=None, key=None):
        """
        Initialize a new ACS object

        Parameters
        ----------
        year : None or int, default None
            The last year to retrieve data from. For example, if
            year=2015, retrieve data from 2011-2015.

            If None, use the year specified in the configuration file.
        key : None or str, default None
            A key used to make requests for the data. If None, use the
            key specified in the configuration file.
        """
        # retrieve default values from configuration
        if year is None or key is None:
            config = util.get_configuration()
            if year is None:
                year = config['Census'].getint('Year')
            if key is None:
                key = config['Census']['Key']

        self.year = year
        self.key = key

    def __repr__(self):
        """
        Represent the ACS object
        """
        return f"ACS(year={self.year!r}, key={self.key!r})"

    def _query(self, variables, geography='us', inside=None):
        """
        Query the ACS API and returns the result as a list of lists

        Parameters
        ----------
        variables : list of str
            A list of variable names to query for.

            The list must not contain more than 50 elements.

            Example:

            ["B01001_002E", "B01001_026E"]
        geography : str, default 'us'
            The unit to retrieve statistics from. For example, if you
            want to retrieve statistics for census tracts, set
            geography='tract'.

            A complete list of geographies can be found here (look at
            the leftmost column):

            https://api.census.gov/data/2016/acs/acs5/examples.html
        inside : str, default None
            Restricts the search inside a specified area. For example,
            if you only want results inside the state of Alabama, you
            can set inside to:

            'state:01'

            If you want to nest deeper, you can specify the needed
            geographies in order. For example:

            'state:01 county:001'

            Will filter the results to Autauga County, Alabama.

        Returns
        -------
        list of lists
            The first list contains the variable names while the others
            carry the requested values.
        """
        # API limit
        assert len(variables) <= 50

        # generate query params
        params = {
            'get': ','.join(variables),
            'for': '{}:*'.format(geography),
        }
        if inside is not None:
            params['in'] = inside
        if self.key != '':
            params['key'] = self.key

        # generate headers
        ua = util.get_configuration()['Downloads']['UserAgent']
        headers = {'User-Agent': ua}

        # generate query url
        query_url = f'https://api.census.gov/data/{self.year}/acs/acs5'

        r = requests.get(query_url, params=params, headers=headers)
        r.raise_for_status()

        o = r.json()

        return o

    def data(self, variables, geography='us', inside=None):
        """
        Query the ACS API and return the result as a pandas DataFrame

        Multiple requests will be made if needed.

        Parameters
        ----------
        variables : list or dict
            If a list, represents variable names to query for.

            If a dict, the keys represent variable names to query for.
            The values represent how the variables should be named
            locally.

            Check the examples section!
        geography : str, default 'us'
            The unit to retrieve statistics from. For example, if you
            want to retrieve statistics for census tracts, set
            geography='tract'.

            A complete list of geographies can be found here (look at
            the leftmost column):

            https://api.census.gov/data/2016/acs/acs5/examples.html
        inside : str, default None
            Restricts the search inside a specified area. For example,
            if you only want results inside the state of Alabama, you
            can set inside to:

            'state:01'

            If you want to nest deeper, you can specify the needed
            geographies in order. For example:

            'state:01 county:001'

            Will filter the results to Autauga County, Alabama.

        Returns
        -------
        pandas.DataFrame

        Examples
        --------
        To retrieve the total population in the USA:

        >>> acs = ACS()
        >>> variables = ['B01001_001E']
        >>> df = acs.data(variables)

        Same case, but renaming 'B01001_001E' to 'Total Population':

        >>> acs = ACS()
        >>> variables = {'B01001_001E': 'Total Population'}
        >>> df = acs.data(variables)

        Retrieve variable for all tracts inside Autauga County, Alabama:

        >>> acs = ACS()
        >>> variables = ['B01001_001E']
        >>> geography = 'tract'
        >>> inside = 'state:01 county:001'
        >>> df = acs.data(variables, geography, inside)
        """
        if isinstance(variables, list):
            query_vars = variables
            rename_vars = None
        elif isinstance(variables, dict):
            query_vars = list(variables.keys())
            rename_vars = variables
        else:
            raise TypeError("wrong type for argument 'variables'")

        dframes = []
        # split variables into chunks of 50
        for chunk in util.misc.grouper(query_vars, 50):
            json_result = self._query(chunk, geography, inside)

            # generate DataFrame from chunk result
            columns = json_result[0]
            values = json_result[1:]
            dframe_result = pandas.DataFrame(values, columns=columns)
            dframes.append(dframe_result)

        result = pandas.concat(dframes, axis=1)

        # remove duplicate columns (caused by split requests)
        result = result.loc[:, ~result.columns.duplicated(keep='last')]

        # convert column values to numbers
        numeric_vars = [x for x in query_vars if x not in _NONNUMERIC_VARS]
        result[numeric_vars] = result[numeric_vars].apply(pandas.to_numeric)

        # check if there are columns whose values are all NaN (GH19)
        all_nans = result.isnull().all()
        if all_nans.any():
            columns = all_nans[all_nans].index.tolist()
            wmsg = ("The Census API returned an all null column for some"
                    " variables: {}. You can make sure that they are available"
                    " at the requested geography level {!r}.")
            wmsg = wmsg.format(columns, geography)
            warnings.warn(wmsg, UserWarning)

        if rename_vars is not None:
            result = result.rename(columns=rename_vars)

        return result
