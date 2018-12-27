# -*- coding: utf-8 -*-
"""
Copyright © 2017-2018 The University of New South Wales

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Except as contained in this notice, the name or trademarks of a copyright holder

shall not be used in advertising or otherwise to promote the sale, use or other
dealings in this Software without prior written authorization of the copyright
holder.

UNSW is a trademark of The University of New South Wales.

Created on Fri Jan 12 13:47:56 2018

@author: kjetil
"""


import sqlalchemy as sa
import pandas as pd
from pandas import DataFrame

from utils import Error, Defaults, conv_time
from ephem import Date as eDate
import json
import string, random, base64
from datetime import datetime


# The database types we allow to use in definitions. See
# http://docs.sqlalchemy.org/en/latest/core/type_basics.html#generic-types
#
# Try to stick to generic types to make the implementation independent of database schema
#
# These are the generic types:
#
# * BigInteger
# * Boolean
# * Date
# * DateTime
# * Enum
# * Float
# * Integer
# * Interval
# * LargeBinary
# * MatchType
# * Numeric
# * PickleType
# * SchemaType
# * SmallInteger
# * String
# * Text
# * Time
# * Unicode
# * UnicodeText
#
# See http://docs.sqlalchemy.org/en/latest/core/metadata.html for how to define tables using the Table
# syntax (the declarative base syntax is not used here)
#

import sqlalchemy.types as sa_t
from sqlalchemy import MetaData, Column, Table, func

#
# Define the maxium length to apply to Strings (in SQL this equals VARCHAR, so the length is less if possible)
#
_MAX_STRING_LEN = 1024


#
# Set up logger
#
import logging
log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())

#
# The metadata column name for the timestamp
#
TSTAMP_LBL = '_tstamp' #<--- warning. TSTAMP_LBL is accessed outside this class (restapi.py)

#
# The label to use for the primary key (ID).
# NOTE: Tables will only get a primary key if they are initialised with the create_table method
#
ID_LBL = '_id'


#
# IF _ALLOW_OLDSTYLE_HEX is set to true, then any entry in the database in the format
# AA-BB-CC-DD ... will decode into a bytearray so long as all the characters are valid hex. If it is not set to true
# then the database entries need to be prefixed with hex:// in order to decode this way.
# This only exists for backwards compatability. New versions of libgs will store all bytearrays as either
# base64 or hex using the appropriate label hex:// or base64://
#
_ALLOW_OLDSTYLE_HEX = True



#
# TODO: CHANGE type of pass_id to be BigInt rather than String. Does require some refactoring of db + restapi
#       as currently the pass id is occassionally stored as a string (e.g. no pass)
#



def tfilterstr2query(filters):
    """
    Convert a timestamp filter string into a well formated
    where query
    """

    query = []
    for f in filters:
        if f[0] in ['>', '<']:
            if f[1] == '=':
                op = f[:2]
                f1 = f[2:]
            else:
                op = f[0]
                f1 = f[1:]
        else:
            op = '='
            f1 = f

        try:
            tstamp = conv_time(f1, to='julian')
        except:
            return None

        query += [op + str(tstamp)]

    return (TSTAMP_LBL + (' AND {}'.format(TSTAMP_LBL)).join(query) + ' ')



class Database(object):
    """
    Class for low-level database access.
    
    It can be connected to different engines; MySQL, SQLITE, etc...

    """

    def __init__(
            self, 
            db=Defaults.DB, 
            binary_fmt = 'hex', 
            get_from_disk = False, 
            disk_threshold=None, 
            disk_path=None):
        """
        Args:
            db (str)                 : `sqlalchemy engine connection string <https://docs.sqlalchemy.org/en/latest/core/engines.html>`_
            binary_fmt (str[hex/b64]): Format to store binary data as
            get_from_disk (bool)     : If True get linked content and insert in table before returning.
            disk_threshold           : Threshold (in bytes) before storing binary data to disk (None = do not store to disk)
            disk_path                : Absolute os path to store binary datafiles to

        .. note::

           If disk_threshold is specified, then data larger than <disk_theshold> bytes will be
           stored in the filesyste with only a reference inserted in the database.

           The path in which it is stored is <disk_path>/comms. This path needs to
           be available and writeable. If it is not, an log message will be will be raised and
           the data stored in the database instead.

        """

        #
        # pool_pre_ping is one way to try to avoide the MySQL connection gone aeay error. Other options
        # may be to enable pool_recycle.
        #
        #
        try:
            self._eng = sa.create_engine(db, pool_pre_ping=True)
        except Exception as e:
            log.exception("Error trying to create SQL engine using pool_pre_ping. Trying without")
            self._eng = sa.create_engine(db)   
            log.warning("Creating SQL engine without pool_pre_ping worked. *WARNING*: You may experience issues with long running connection.")


        #
        # Set up sqlalchemy metadata
        #
        self._metadata = MetaData(self._eng)
        self._metadata.reflect(self._eng)

        # If enabled then any *bytearray* that exceeds
        # the disk_theshold number of bytes will be 
        # saved to disk and a reference introduced in the database
        # rather than the actual data
        #
        self._disk_threshold = disk_threshold
        self._disk_threshold_text = disk_threshold
        self._disk_path = disk_path
        self._get_from_disk = get_from_disk
        
        
        #
        # Binary format. Either 'b64' or 'hex'. Any bytearray saved to disk
        # will be automatically converted to this format before saving
        #
        if binary_fmt not in ['b64', 'hex']:
            raise Error("binary_fmt must be 'b64' or 'hex', got {}".format(binary_fmt))

        self._binary_fmt = binary_fmt

    def count_rows(self, table):
        """ Return the number of rows in a table

        Args:
            table:

        Returns:
            Number of rows

        """
        t = self._metadata.tables[table]
        return self._eng.execute(func.count(t.columns[t.columns.keys()[0]])).scalar()

    def create_table(self, name, *columns, **kwargs):
        """ Set up the columns and add a unique key.

        The Database class can be used without creating a database
        first, but then pandas will take care of it on first access, and no primary key will be created.

        It is therefore encouraged to explicitly create the table with this method in the Database subclass constructor

        .. note::
           A primary key column will be automatically added. By default it is called as in the ID_LBL constant.
           Change by specify primary_key_col=

        Args:
            name:                               The table to create
            *columns:                           The list of :class:`sqlalchemy.types.Column` objects to add to the table
            primary_key_col (str, optional):    The column to use as primary key (must be sa.Integer type)

        Returns:


        """

        try:
            primary_key_col = kwargs['primary_key_col']
            if len(kwargs) > 1:
                raise  Exception("Invalid arguments to create_table")
        except:
            primary_key_col = ID_LBL
            if len(kwargs) > 0:
                raise  Exception("Invalid arguments to create_table")

        Table(name, self._metadata,
              Column(primary_key_col, sa_t.Integer(), primary_key=True),
              Column(TSTAMP_LBL, sa_t.Numeric(20,12)), #<-- dates are stored as julian dates (days since epoch). Add enough precision to allow microseconds to be stored
              *columns,
              keep_existing=True)
        self._metadata.create_all()


    def put_df(self, table, df, index=False, if_exists='append'):
        """ Add dataframe to database, appending metadata for when it was added

        Certain types will be encoded (bytearrays, dates,...) so that the data actually entered in the database is usually strings.
        This process is automatically reversed by the get_df method and as such is transparent to the user.

        Args:
            table (str):                The table
            df    (:py:class:`pandas.DataFrame`):   The :py:class:`pandas.DataFrame` to add (must have the correct headers)
            index (bool):               If true: add index as well
            if_exists (str):            What to do if table exists (directly passed to pd.to_sql method)

        Returns:
            None

        """

        df2 = df.copy()

        # Add timestamp as julian date
        df2[TSTAMP_LBL] = pd.Timestamp.utcnow().replace(tzinfo=None).to_julian_date()

        # Convert any bytearray into the designated binary encoding. Do not encode column names
        # that start with '_' (internal/private)
        columns = [d for d in df2.columns if d[0] != '_']
        df2[columns] = df2[columns].applymap(self._encode)


        try:
            df2.to_sql(table, self._eng, index=index, if_exists=if_exists)
        except Exception as e:
            log.info("ERROR {} trying to save to database: {}. Trying again".format(e.__class__.__name__, e))
            df2.to_sql(table, self._eng, index=index, if_exists=if_exists)


    def get_df(self, table, where=None, limit=None, orderby=None, descending = True, raw=False):
        """ Get data from communications database as a :py:class:`pandas.DataFrame` object

        Args:
            table (str):                    The table to fetch from
            where (str, optional):          SQL syntax to append to query as WHERE=...
            limit (int, optional):          Max number of rows to return
            orderby (str, optional):        The column to sort by
            descending (bool, optional):    If true: sort in descending order, otherwise sort in ascending order.
                                            Has no effect if orderby = None
            raw (bool, optional):           If true, do not decode anything in the database into native objects. Most
                                            data will be returned as strings with encoding flags intact.

        Returns:
            None

        """

        sql = "SELECT * from %s"%(table)

        if where is not None:
            sql += " WHERE {}".format(where)

        if orderby is None:
            orderby = TSTAMP_LBL

        if descending:
            order = 'DESC'
        else:
            order = 'ASC'

        if descending is not None:
            sql += " ORDER BY {} {}".format(orderby, order)

        if limit is not None:
            if isinstance(limit, int):
                sql += " LIMIT {}".format(limit)
            else:
                raise Error("Limit must be an integer, got {} of type {}".format(limit, type(limit)))


        # We ideally need to convert the sql string to raw, but or pd.read_sql seems to fail for some reason
        # but I cant find an obvious way to do so, so lets just replace % with %% for now.
        # TODO: come up with a more general solution
        df = pd.read_sql(sql.replace(r'%', r'%%'), self._eng)

        if not raw:

            # TSTAMP_LBL is a floating point julian date. Convert it to datetime too if we arent requesting raw
            try:
                df[TSTAMP_LBL] = df[TSTAMP_LBL].apply(lambda s: conv_time(s, to='datetime', float_t='julian'))
            except Exception as e:
                log.error("Failed to convert timestamp to datetime. {}:{}".format(e.__class__.__name__))

            # Decode remaining fields. But do not touch column names
            # that start with '_' (internal/private)
            columns = [d for d in df.columns if d[0] != '_']
            df[columns] = df[columns].applymap(self._decode)

        return df
        
    def get_file(self, fname):
        """ Grab a file resource and return the bytes or string (.bin or .txt)

        Args:
            fname: The name of the file resource

        Returns:
            The resource, either as a string (if its a .txt file) or as a bytearray (if its a .bin file)

        """

        if fname[-3:] == 'txt':
            with open(self._disk_path + '/' + fname, 'r') as fp:
                out = fp.read()
        else:
            with open(self._disk_path + '/' + fname, 'rb') as fp:
                out = bytearray(fp.read())

        return out
        
    def _encode(self, data):
        """
        Encode datatypes appropriately for storing in database
        Args:
            data: The data to encode

        Returns:
            The data in a format suitable for storing in database
        """
        

        types_to_encode = [basestring, bytearray, eDate, pd.Timestamp, datetime]
        types_to_skip   = [int, float, type(None)]


        # Only worry about encoding strings, bytearrays or datetime objects, for anything else. Try to just make it
        # a dumb string using the __str__ method. Note that this is a non-nominal situation
        if not any([isinstance(data, t) for t in types_to_encode]):
            if  any([isinstance(data, t) for t in types_to_skip]):
                # These types are ignored
                return data

            else:
                # Other strange types will probably not be possible to save in database, so try to conver dumbly to a
                # string.

                log.debug("_encode: No encoding handler for type {}, trying to convert dumbly to string".format(type(data)))
                try:
                    return str(data)
                except:
                    log.error("_encode: Failed to convert type {} to string, database entry will be replaced with 'ERROR'".format(type(data)))
                    return "ERROR"

        # Handle normal string data
        if isinstance(data, basestring):

            # Make sure strings are propely utf-8 encoded
            if isinstance(data, unicode):
                data = data.encode('utf-8')

            if self._disk_threshold_text is not None and len(data) > self._disk_threshold_text:

                try:
                    #
                    # 1.1 Data meets condition to be be saved to disk. Try to do so.
                    #
                    fname = datetime.strftime(datetime.utcnow(), '%Y%m%d%H%M%S')
                    fname += '_' + ''.join([random.choice(string.ascii_letters + string.digits) for i in range(8)])
                    fname += '.txt'
                    full_fname = '{}/{}'.format(self._disk_path, fname)

                    with open(full_fname, 'w') as fp:
                        fp.write(data)
                        
                    log.debug("data is a text field but len(data) > {} and has so it has been stored in filesystem".format(self._disk_threshold))
                    return 'file://' + fname

                except Exception as e:
                    #
                    # 1.2 Data failed to save to disk, return it so that at least it is saved in db
                    #
                    log.error("{}: len(data) > {} but failed too save to filesystem: {}".format(e.__class__.__name__, self._disk_threshold, e))
                    return data

            else:
                #
                # 1.2 Data is small enough to return without saving to disk
                #
                return data

        # binary data
        elif isinstance(data, bytearray):
            if self._disk_threshold is not None and len(data) > self._disk_threshold: 
                          

                try:
                    fname = datetime.strftime(datetime.utcnow(), '%Y%m%d%H%M%S')
                    fname += '_' + ''.join([random.choice(string.ascii_letters + string.digits) for i in range(8)])
                    fname += '.bin'
                    full_fname = '{}/{}'.format(self._disk_path, fname)
                    with open(full_fname, 'wb') as fp:
                        fp.write(data)
                        
                    log.debug("data is binary and len(data) > {} so it has been stored in filesystem".format(self._disk_threshold))
                    
                    #
                    # 2.1 Data is binary and met conditions for saving to disk
                    #
                    return 'file://{}'.format(fname)
                except Exception as e:
                    
                    #
                    # 2.2 Data is binary but failed to save to disk. Continue with data conversion so at least it is saved in database
                    # 
                    log.error("{}: len(data) > {} but failed to save to filesystem: {}".format(e.__class__.__name__, self._disk_threshold, e))


            if self._binary_fmt == 'b64':
                
                #
                # 2.3 a. Return base64 encoded data
                #
                return 'base64://' + base64.b64encode(data)
            elif self._binary_fmt == 'hex':
                #
                # 2.3 b. Return hex encoded data
                #
                b16data = base64.b16encode(data)
                return 'hex://' + '-'.join([b16data[n:n+2] for n in range(len(b16data))[::2]])
            else:
                raise Error("Unexpected binary format {}".format(self._binary_fmt))

        elif isinstance(data, eDate):
            return 'ts-ephem://' + conv_time(data, to='iso')
        elif isinstance(data, pd.Timestamp):
            return 'ts-pandas://' + conv_time(data, to='iso')
        elif isinstance(data, datetime):
            return 'ts-dtime://' + conv_time(data, to='iso')
        else:
            raise Error("Unexpected. This should not be possible")
            

    def _decode(self, data):
        """ Reverse the _encode operation. Convert database strings into native types.

        Args:
            data: The string to decode

        Returns:
            Native data type

        """

        if not isinstance(data, basestring):
            return data
            
        out = data
        if self._get_from_disk and data[:10].find('file://') == 0:
            # Load data file
            try:
                out = self.get_file(data[7:])
            except Exception as e:
                log.error("{} reading data file linked from SQL: {}".format(e.__class__.__name__, e))

        elif data[:10].find('base64://') == 0:
            try:
                out = bytearray(base64.b64decode(data[9:]))
            except Exception as e:
                log.error('{} parsing base 64 data from SQL: {}'.format(e.__class__.__name__, e))
        
        # Hex dealt with differently to be backwards compatible
        # Instead of looking for marker, it is just assumed that all strings in the
        # format AA-BB-XX... are binary strings
        elif (_ALLOW_OLDSTYLE_HEX and (len(data.split('-')) > 1 and (all([len(x) == 2 for x in data.split('-')])))):
            try:
                out = bytearray(base64.b16decode(''.join(data.split('-'))))
            except Exception as e:
                log.error('{} parsing hex data from SQL: {}'.format(e.__class__.__name__, e))
        # New style hex encoding uses the hex:// keyword
        # NOTE: it is still splitting by '-' but the '-' in the encoded string is optional. It will decode either way
        elif (data[:10].find('hex://') == 0):
            try:
                out = bytearray(base64.b16decode(''.join(data[6:].split('-'))))
            except Exception as e:
                log.error('{} parsing hex data from SQL: {}'.format(e.__class__.__name__, e))

        elif data[:15].find('ts-ephem://')  == 0:
            out = conv_time(data[11:], to='ephem')
        elif data[:15].find('ts-pandas://') == 0:
            out = conv_time(data[12:], to='pandas')
        elif data[:15].find('ts-dtime://')  == 0:
            out = conv_time(data[11:], to='datetime')

        return out      

            


class CommsLog(Database):
    """ Database class for storing communications with the satellite.

    The columns are:

    ========= =================================================================
    nid       The norad id of the object that is being communicated with
    pass_id   The current pass ID
    orig      The :attr:`actor <.ACTORS>` that sent the message
    dest      The :attr:`actor <.ACTORS>` that received the message
    msg       The message itself
    ========= =================================================================

    Additionally a primary key and timestamp is automatically added to each record.


    """

    #: Name of the various actors that send or receive communications
    ACTORS = ['Sat', 'GS', 'Protocol']

    # The name of the database table
    _TABLE = "comms"


    def __init__(self, db=Defaults.DB, binary_fmt='hex', disk_path=Defaults.DATA_PATH, **kwargs):
        """
        See :class:`.Database` for description of available arguments
        """
        super(CommsLog, self).__init__(
            db, 
            binary_fmt=binary_fmt, 
            disk_path = disk_path + '/' + self._TABLE,
            **kwargs)

        self.create_table(self._TABLE,
                          Column("nid", sa_t.String(_MAX_STRING_LEN)),
                          Column("pass_id", sa_t.String(_MAX_STRING_LEN)),
                          Column("orig", sa_t.String(_MAX_STRING_LEN)),
                          Column("dest", sa_t.String(_MAX_STRING_LEN)),
                          Column("msg", sa_t.Text()))


    def put(self, nid, pass_id, orig, dest, msg):
        """
        Add new item to the log

        Args:
            nid(int):       Norad ID of the satellite commuicated with
            pass_id (str):  ID of the pass the communication belongs to
            orig (str):     Originator of the message
            dest (str):     Destination of the message
            msg (str):      The message itself

        """
        if orig not in self.ACTORS:
            raise Error('Invalid origin, must be one of %s'%(self.ACTORS))

        if orig not in self.ACTORS:
            raise Error('Invalid destination, must be one of %s'%(self.ACTORS))

        df = DataFrame({'nid': [nid], 'pass_id': [pass_id], 'orig': [orig], 'dest':[dest], 'msg':[msg]})
        self.put_df(self._TABLE, df, index=False)

    def get(self, limit=None, tstamps=None, **kwargs):
        """ Get the communication log

        Args:
            where: a WHERE=... SQL query to apply to the query
            limit: limit to a number of results

        Returns:
            :class:`.DataFrame` containing the stored data

        """

        # Onlu accept arguments for the columns in the db.
        if len(set(kwargs.keys()).intersection(['nid', 'pass_id', 'orig', 'dest'])) == 0:
            raise Exception("One or more invalid arguments {}".format(kwargs))

        where = None
        for k, v in kwargs.items():
            if v is None:
                continue
            where = '' if where is None else where + ' AND '
            where += '`{}` like "{}"'.format(k, v)


        if tstamps is not None:
            where = '' if where is None else where + ' AND '
            where += tfilterstr2query(tstamps)

        df = self.get_df(self._TABLE, where=where, limit=limit)


        # TODO: file:// should be loaded from file ...
        # def decode(d):
        #     if isinstance(d, basestring) and d[:7] == 'file://':
        #         # TODO: Load from file
        #         return d
        #     else:
        #         return d  # <-- note: baseclass does decoding/enocding of some types
        #
        # df.msg = df.msg.apply(decode)
        return df


class KVDb(Database):
    """
    Generic Key-Value database with optional "standard" fields (columns).

    This class is not used directly. See :class:`MonitorDb` and :class:`PassDb`

    When initialised by itself, this class will create a key/value database with two columns; key and value
    that can store arbitrary data. Values will be attempted encoded using JSON, which allows the database
    to store almost arbitrary data types.

    Additionally a set of other columns can be specified with any sqlalchemytype required.
    """

    # Change this in derived classes
    def __init__(self, db, table, ncols=[], ntypes=sa_t.Text(), **kwargs):
        """

        Args:
            ncols:  Normal columns; a list of column names
            ntypes: SQLAlchemy types associated with the columns (defaults to Text)

        See :class:`.Database` for the definition of the additional arguments.
        """
        
        # The table to use
        self._TABLE = table
        
        # Normal (non-kv) columns
        
        if 'key' in ncols or 'value' in ncols:
            raise Error("'key' or 'value' cant be used as a normal field name")
        
        self._NCOLS = ncols
        
        super(KVDb, self).__init__(db, **kwargs)

        if not isinstance(ntypes, list):
            ntypes = [ntypes for n in ncols]

        columns = [Column(n, t) for n,t in zip(ncols, ntypes)]
        self.create_table(self._TABLE, Column('key', sa_t.String(_MAX_STRING_LEN)), Column('value', sa_t.Text()), *columns)


    def put(self, key, value, **kwargs):
        
        if any([k not in self._NCOLS for k in kwargs.keys()]):
            raise Error("{} is not a clolumn in this database. Valid columns are {}".format(k, self._NCOLS))
    
        if not isinstance(key, list):
            key = [key]
            value = [value]
            kwargs = {k:[v] for k,v in kwargs.items()}   
        
        kwargs['key'] = key
        kwargs['value'] = value
        
        # Complete the empty columns otherwise the db gets confused when
        # creating new table
        for c in self._NCOLS:
            if c not in kwargs.keys():
                kwargs[c] = [None] * len(key)
                
        
        # Create the dataframe
        df = pd.DataFrame(kwargs)

        def encode(d):
            # Encode anything that we can as json
            if not (isinstance(d, bytearray) or isinstance(d, datetime) or isinstance(d, eDate) or isinstance(d, pd.Timestamp)):
                try:
                    return 'json://' + json.dumps(d)
                except:
                    # json encoding failed so just return as is, it should be encoded as strings by Database base class
                    return d
            else:
                return d #<-- the other types are automatically encoded as strings by the Database base class

        # Save timestamps as ISO strings
        # df.value = df.value.apply(lambda x: conv_time(x, to='iso', ignore_ambig_types=True))
        
        # The type is encoded with json in order to not have to worry
        # about storing type.
        try:
            df.value = df.value.apply(encode)
        except Exception, e:
            log.error("Could not convert data {} to json. Not saved to database!: {}".format(value, e))
        
        self.put_df(self._TABLE, df, index=False)
        
        
    def get(self, limit=None, keys=None, tstamps=None, **kwargs):
        """      
        .. note:: 
        
           To do partial matches, use the % wildchar.
           eg keys = ['%NW%', '%NE%'] will match all keys
           with NW and NE in their names.
        """
        
        where = None
        for k,v in kwargs.items():
            where = '' if where is None else where + ' AND '
            where = '{} like "{}"'.format(k,v)
            
        if keys is not None:
            where = '' if where is None else where + ' AND '
            where += ' (`key` like "' + '" or `key` like "'.join(keys) + '")'
            
        if tstamps is not None:
            where = '' if where is None else where + ' AND '
            where += tfilterstr2query(tstamps)

        df =  self.get_df(self._TABLE, where=where, limit=limit)
        
        #file:// and byttearray passthroughs fail json decoding unless we do a bit of wranglign:
        def decode(d):
            if isinstance(d, basestring) and d[:7] == 'json://':
                return json.loads(d[7:])
            elif isinstance(d, basestring) and d[:7] == 'file://':
                # TODO: Load from file if required (?)
                return d
            else:
                return d #<-- note: baseclass does decoding/enocding of some types
                    
        
        #print("B, ", [v for v in df.value],[type(v) for v in df.value])        
        df.value = df.value.apply(decode)

        return df




class MonitorDb(KVDb):
    """ Monitor database interface class
    
    The monitor database is a key/value type database
    that stores arbitrary monitoring values. Each key/value pair
    is additionally associated with the pass id for easy search.

    It sets up a table with the following columns

    ========= =================================================================
    key       The name of the monitor point
    value     The monitor point value (JSON encoded)
    pass_id   The pass id associated with the current monitor entry
    alert     The alert level of the current monitor entry
    ========= =================================================================

    Additionally each row is assigned a primary key and a timestamp

    """
    
    _TABLE = 'monitor'
    
    def __init__(self, db=Defaults.DB, binary_fmt='b64', disk_threshold=1000,disk_path=Defaults.DATA_PATH, **kwargs):
        """
        See :class:`.Database` for description of available arguments

        """
        super(MonitorDb, self).__init__(
            table=self._TABLE, 
            db=db, 
            ncols=['pass_id', 'alert'],
            ntypes=[sa_t.String(_MAX_STRING_LEN), sa_t.String(_MAX_STRING_LEN)],
            binary_fmt     = binary_fmt,
            disk_threshold = disk_threshold,
            disk_path = disk_path + '/' + self._TABLE,
            **kwargs)    
    

    def put(self, pass_id, key, value, alert=None):
        super(MonitorDb, self).put(key, value, pass_id = pass_id, alert=alert)

    # get doesnt require a wrapper as it will act correctly anyway.


class PassDb(KVDb):
    """
    Interface class to Pass Information Database.
    
    The Pass Information Database is a key/value type database
    that stores arbitrary data about a pass (pass information). Each key/value pair
    is associated with the pass id and module from which it was added for easy 
    search.
    
    It sets up a table with the following columns

    ========= =================================================================
    key       The pass information key
    value     The pass information value
    pass_id   The pass id associated with the current monitor entry
    module    The module that requested the data to be added to the database
    ========= =================================================================

    Additionally each row is assigned a primary key and a timestamp


    """
    

    _TABLE = "passes"
    
    def __init__(self, db=Defaults.DB, binary_fmt='b64', disk_threshold=1000, disk_path=Defaults.DATA_PATH, **kwargs):
        super(PassDb, self).__init__(
            table=self._TABLE, 
            db=db, 
            ncols=['pass_id', 'module'],
            ntypes=[sa_t.String(_MAX_STRING_LEN), sa_t.String(_MAX_STRING_LEN)],
            binary_fmt     = binary_fmt,
            disk_threshold = disk_threshold,
            disk_path = disk_path + '/' + self._TABLE,
            **kwargs)    

    
    def put(self, module, pass_id, key, value):
        """ Add a key/value pair to the database

        Args:
            module: The module that stored the information (scheduler/groundstation)
            pass_id: The pass id
            key:   User defined key
            value: User defined value
        """
        
        super(PassDb, self).put(key, value, module=module, pass_id=pass_id)
    

if __name__ == '__main__':
    pass
