# -*- coding: utf-8 -*-
"""
..
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


:date: Thu Jul 27 20:40:36 2017
:author: kjetil

Overview
---------

This module contains utilities and settings for the libgs package.


Examples
---------


Module Reference
-----------------

"""
from __future__ import print_function

import threading

import logging
import time
import os
import pandas as pd
import traceback
import collections
from datetime import datetime
import ephem
from libgs_ops.rpc import RPCClient


abort_all = threading.Event()

log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())



##########################
#
# Exceptions
#
##########################

class Error(Exception):
    """Generic Error for libgs"""

    def __init__(self, msg, original_Error=None):
        if original_Error is not None:
            super(Error, self).__init__(msg + (": %s" % original_Error))
            self.original_Error = original_Error
        else:
            super(Error, self).__init__(msg)


class AbortAllException(Error):
    """
    Exception representing the abort_all event
    """
    pass


##########################
#
# Default values used throughout
#
##########################


class Defaults:
    """
    Defines default values used by the different classes.

    .. note:

        Many (probably most) of these values are configurable in other ways (through class interfaces, constructors, etc...)

        This class just holds all the fallback values (defaults).

    """

    #
    # The interval at which to save monitoring values to database
    # when tracking and when not tracking
    #

    #: The time inteval (in seconds) at which to save monitor values to database while tracking
    MONITOR_SAVE_DT_TRACK   = 5   # 5 seconds

    #: The time inteval (in seconds) at which to save monitor values to database while not tracking
    MONITOR_SAVE_DT_NOTRACK = 900 # 15 minutes


    ##############################################
    #
    # Hardware interfaces
    #
    ##############################################

    #
    # XMLRPC interface to scheduler
    #

    #: The host to bind the XMLRPC scheduler interface to
    XMLRPC_SCH_SERVER_ADDR = "localhost"

    #: The port to bind the XMLRPC scheduler interface to
    XMLRPC_SCH_SERVER_PORT = 8000

    #
    # XMLRPC interface to ground station
    #

    #: The host to bind the XMLRPC ground station interface to
    XMLRPC_GS_SERVER_ADDR = "localhost"

    #: The port to bind the XMLRPC ground station interface to
    XMLRPC_GS_SERVER_PORT = 8001

    #:
    #: Default client timeout for xmlrpc calls
    #:
    XMLRPC_CLI_TIMEOUT = 2
    


    #:
    #: Dashboard port
    #:
    DASH_PORT = 5001

    #
    # REST API
    #

    #: The host to bind the REST API to
    API_ADDR = "localhost"

    #: The port to bind the REST API to
    API_PORT = 8080



    ##############################################
    #
    # Configuration parameters
    #
    ##############################################


    #
    # Default rotator configurations
    # (Set in rotator base class, but usually overwritten in derived classes)
    #

    #: Default azimuth angle to stow antennae to (normally overridden in rotator class)
    ROTATOR_STOWED_AZ = 0

    #: Default elevation angle to stow antennae to (normally overridden in rotator class)
    ROTATOR_STOWED_EL = 90

    #: Default antenna beamwidth (normally overridden in rotator class). Sets the granularity at which the rotator
    #: moves the antenna
    ROTATOR_ANTENNA_BEAMWIDTH = 10 #<-- sets the granularity at which the rotator moves the antenna

    #: Default maximum azimuth angle for antenna rotator  (normally overridden in rotator class)
    ROTATOR_MAX_AZ    = 360

    #: Default minimum azimuth angle for antenna rotator  (normally overridden in rotator class)
    ROTATOR_MIN_AZ    = 0

    #: Default maximum elevation for antenna rotator  (normally overridden in rotator class)
    ROTATOR_MAX_EL    = 90

    #: Default minimum elevation for antenna rotator  (normally overridden in rotator class)
    ROTATOR_MIN_EL    = 0

    #: Default timeout for slewing antennae  (normally overridden in rotator class)
    ROTATOR_SLEW_TIMEOUT = 100


    #
    # Log config
    #
    LOG_PATH = './logs'       #: Path to store log files in
    LOG_FILE = 'libgs.log'    #: Log file name
    LOG_BACKUPCOUNT = 100     #: Number of log files to keep
    LOG_MAXFILESIZE = 1000000 #: Max log filesize in bytes
    LOG_FORMAT = '%(asctime)s - %(name)14s - %(levelname)5s - %(module)20s:%(lineno)4s - "%(message)s"' #: log format string
    LOG_STRING_LEN = 23+3+14+3+5+3 + 24+3+1  #: length of log format string

    #:
    #: Length of log to keep in UI
    #:
    UI_LOG_LEN = 200



    #:
    #: Database connection (See SQLAlchemy for syntax)
    #:
    DB = 'sqlite:///libgs.db'


    #
    # Rotctld ppolling
    # TODO: This might also be an old one that should be removed
    #
    GS_ROTATOR_POLLING_INTERVAL = 0.25 #: Deprecated. Will be removed in future updates



    #:
    #: Communications timeout after requesting data, and waiting for reply
    #:
    TX_REPLY_TIMEOUT=1000 #<--- large number to let spacelink handle the timeouts.


    #:
    #: Color log entries
    #:
    USE_LOG_COLOUR = True

    #:
    #: Log level  for extra verbose logging (normally disabled but can be enabled)
    #:
    # VERY_VERB_LOG = 5


    #:
    #: Update delay for frequency plot (should be around .2 - 2)
    #:
    VIS_FREQUENCY_PLOT_UPDATE_DELAY = .5


    #
    # Spectrum recording
    #
    RECORD_SPECTRA = True           #: If false, spectra will not be recorded and stored in database
    RECORD_SPECTRA_MAX_LEN = 900    #: If spectrum recording enabled, maximum number of spectra to record in a single pass
    RECORD_SPECTRA_DT = 1.0         #: If spectrum recording enabled, time delay between subsequent recorded spectra (in seconds)

    #
    # Max allowed dt (in seconds) in data used for gs tracking
    #
    MAX_TRACK_DT = 1.0

    #:
    #: Path to store datafiles in (that are not stored in db)
    #:
    DB_BIN_PATH = '.'

    #: For backwards compatability only. Will be removed in future updates.
    DATA_PATH = DB_BIN_PATH #<-- todo: refactor and delete

    #
    # Visualisation waterfalls
    #
    WFALL_COLORMAP = 'Viridis256' #: Bokeh colormap. see https://bokeh.pydata.org/en/0.12.6/docs/reference/palettes.html
    WFALL_JPG_COLORMAP = 'viridis' #: Matplotlib colormap. See: https://matplotlib.org/examples/color/colormaps_reference.html
    WFALL_JPG_WIDTH = 250 #: Width of each recorded waterfall plot (in pixels) if dpi=100
    WFALL_JPG_HEIGHT = 600 #: Height of each recorded waterfall plot(in pixels) if dpi = 100
    WFALL_JPG_WIDTH_EXTRA = 200 #: Extra width of each recorded waterfall plot in pixels if dpi = 100
    WFALL_JPG_DPI = 100 #: DPI for recorded waterfall plots
    WFALL_JPG_OUT_SCALE = 1 #: Scaling of DPI on output of recorded waterfall plots.. Affects font size

    #
    # REST API
    #
    RESTAPI_DEBUG_MODE = False #: Put restapi in debug mode (more verbose error messages)
    RESTAPI_TABLE_LIMIT = 400  #: Max rows to return by restapi if nothing has been explicitly given

########################
#
# Functions and classes
#
########################

def raise_if_aborted():
    """
    This method will raise an exception if the abort_all global event has been set.
    """
    if abort_all.is_set():
        raise AbortAllException("abort_all event has been set")



class RegularCallback(object):

    def __init__(self, func, delay, min_interval=0.05):
        """

        Args:
            func:  Callback funciton to call
            delay: Time between two subsequent calls
            min_interval: Minimum time between the end of one call and the beginning of th next

        """
        self.func = func
        self.delay = delay
        self._pthr = threading.Thread(target=self._regular_callback)
        self._pthr.daemon = True
        self.min_interval=min_interval
        self._suppressing_errors = False
        self._last_e = (None, None)

    def _regular_callback(self):
        """
            A function to regularly call a callback based on the specified delay
        """

        # This property can be changed to stop the callback
        self._stop_thread = False
        stop_thread_fn = lambda: self._stop_thread
        
        log.debug("Regular callback of '{}' started".format(self.func.__name__))

        while True:

            t0 = time.time()

            try:
                self.func()
            except Exception, e:
                new_e = (e.__class__.__name__, str(e))
                if new_e == self._last_e:
                    if not self._suppressing_errors:
                        log.error("Repeat Exception '{}:{}' in regular callback, suppressing output until something new happens".format(*new_e))
                        self._suppressing_errors = True

                else:
                    if self._suppressing_errors:
                        log.info("Repeat Exception '{}:{}' has stopped occurring. Regular callback resumed normal operation".format(*self._last_e))
                    self._suppressing_errors = False
                    self._last_e = new_e
                    err = traceback.format_exc()
                    log.error("Exception in regular callback function. Stack trace:\n%s"%(err))
                #Error("Exception in regular callback function: %s"%(e))

            # Sleep until next call unless an event happens in which case we break from the loop
            try:
                if wait_loop([stop_thread_fn], timeout=max(self.delay - (time.time() - t0), self.min_interval)) is not None:
                    break
            except AbortAllException as e:
                log.debug("Abort All event caught. Shutting down regular callback")
                break


        log.debug("Regular callback of '{}' ended".format(self.func.__name__))
            #time.sleep(max(self.delay - (time.time() - t0), self.min_interval))

    def start(self):
        self._pthr.start()

    def stop(self):
        self._stop_thread = True
        self._pthr.join()



def conv_time(d, to='iso', float_t='julian', ignore_ambig_types = False):
    """
    There are a number of different date formats used around libgs
    ephem.Date, datetime, pandas.Timestamp to mention some.
    Also modified Julian time and various string formats.
    
    
    """
    if ignore_ambig_types and not (isinstance(d, ephem.Date) or isinstance(d, pd.Timestamp) or isinstance(d, datetime)):
        return d
        
    
    # first make a pandas Timestamp object
    if isinstance(d, ephem.Date):
        d2 = pd.to_datetime(d.datetime())
    elif isinstance(d, pd.Timestamp):
        d2 = d
    elif isinstance(d, float):
        if float_t == 'julian':
            d2 = pd.to_datetime(d, unit='D', origin='julian')
        elif float_t == 'unix':
            d2 = pd.to_datetime(d, unit="s", origin="unix" )
            #d2 = pd.to_datetime(datetime.fromtimestamp(d))
        else:
            raise Error("Unknown float  time type {}".format(float_t))
    elif isinstance(d, basestring):
        # Try to work out if we have year first (iso like or day first)
        if len(d.split('-')[0].strip()) == 4:
            d2 = pd.to_datetime(d)
        else:
            d2 = pd.to_datetime(d, dayfirst=True)
    elif isinstance(d, datetime):
        d2 = pd.to_datetime(d)
    else:
        raise Error("Dont know how to convert obejct of type {} to time".format(type(d)))

    d2 = d2.replace(tzinfo=None)

    if to == 'iso': #w milliseconds
        d3 = d2.strftime('%Y-%m-%dT%H:%M:%S,%f')[:-3]   
        d3 += 'Z'
    elif to == 'julian':
        d3 =d2.replace(tzinfo=None).to_julian_date()
    elif to == 'unix':
        d3= time.mktime(d2.timetuple()) + d2.microsecond/1e6
    elif to == 'datetime':
        d3 = d2.to_pydatetime()
    elif to == 'pandas':
        d3 = d2
    elif to == 'ephem':
        d3 = ephem.Date(d2.to_pydatetime())
    else:
        raise Error("Dont know how to convert to {}".format(to))
        
        
    return d3


def wait_loop(events_or_callables = [], timeout=None, dt=0.1):
    """
    Generic waiting loop. It will wait for any event
    (of type threading.Event) to be set, or for any callable to return True
    """
    t0 = time.time()

    if not isinstance(events_or_callables, collections.Iterable):
        events_or_callables = [events_or_callables]

    fns = [ec.is_set if isinstance(ec, threading._Event) else ec for ec in events_or_callables]

    for ec in events_or_callables:
        if not (isinstance(ec, threading._Event) or callable(ec)):
            raise Error("events_or_callable must be a list of events or callables, got {}".format(type(ec)))


    while True:

        if abort_all.is_set():
            raise AbortAllException("global wait_loop abort_all has been set")

        if timeout is not None and time.time() - t0 > timeout:
            return None


        e_set = [e for (e,f) in zip(events_or_callables, fns) if f()]

        if len(e_set) > 0:
            return e_set


        rdt = max(0, timeout - (time.time() - t0)) if timeout is not None else 0
        time.sleep(min(rdt, dt))


def safe_sleep(t):
    """
    safe_sleep uses a subset of the wait_loop capabilities to implement an anologe to the time.sleep() function.

    The advantage is that it will raise an exception if the global abort event gets set, and as such is safe to
    use in thread loops that need to exit on adfa-gs exit.

    """
    wait_loop(timeout=t)



class UTCLogFormatter(logging.Formatter):
    converter = time.gmtime
    use_colour = Defaults.USE_LOG_COLOUR

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        s = "%s.%03dZ" % (t, record.msecs)

        return s

    def format(self, record):

        s =  super(UTCLogFormatter, self).format(record)

        if record.levelno >= logging.ERROR and self.use_colour:
            s = "\033[1;31m%s\033[1;0m"%(s)

        return s

class UTCLogFormatterHTML(UTCLogFormatter):

    def format(self, record):

        frec   =  super(UTCLogFormatter, self).format(record)

        if record.levelno >= logging.ERROR and self.use_colour:
            s = '<pre style="color:red;'
        else:
            s = '<pre style="'

        #s += 'max-width: 100%;overflow-x: auto;">{}</pre>\n'.format(frec)
        s += '">{}</pre>\n'.format(frec)
        return s


def setup_logger(logger,
                 cons_loglvl = logging.INFO,
                 file_logpath=None,
                 file_loglvl=logging.INFO,
                 fmt=Defaults.LOG_FORMAT):
    """
    Function to set up logging for libgs. Should only ever be called
    once.

    It sill set up logging to console and to file if requested.

    It will also make sure all logging is timestamped in UTC time
    following ISO 8601

    Args:
     logger: The log to setup
     cons_loglvl: log level for console logging,
     file_logpath: Path to log to if logging to file (None for no file logging),
     file_loglvl: log level for file log
     fmt: log formatting string
    """

    if hasattr(logger, '_has_been_setup'):
        raise Error("setup_logger can only be called once per logger")



    #
    # TODO: NOTE: When moving to a python module, this stuff should probably
    # be in the __init__ ...
    #

    #
    # Add custom log level
    #
    DEBUG_LEVELV_NUM = 9
    logging.addLevelName(DEBUG_LEVELV_NUM, "DBG_V")
    def debugv(self, message, *args, **kws):
        # Yes, logger takes its '*args' as 'args'.
        self._log(DEBUG_LEVELV_NUM, message, args, **kws)
    logging.Logger.debugv = debugv

    # create logger
    logger.setLevel(logging.DEBUG)

    # create formatter

    # class MyFormatter(logging.Formatter):
    #     converter = time.gmtime
    #     use_colour = Defaults.USE_LOG_COLOUR
    #
    #     def formatTime(self, record, datefmt=None):
    #         ct = self.converter(record.created)
    #         t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
    #         s = "%s.%03dZ" % (t, record.msecs)
    #
    #         return s
    #
    #     def format(self, record):
    #
    #         s =  super(MyFormatter, self).format(record)
    #
    #         if record.levelno >= logging.ERROR and self.use_colour:
    #             s = "\033[1;31m%s\033[1;0m"%(s)
    #
    #         return s



    formatter = UTCLogFormatter(fmt)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(cons_loglvl)

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)


    #
    # Set up file logging as specificed
    #
    if file_logpath is not None:

        logpath = os.path.realpath(file_logpath)

        if not os.path.exists(logpath):
            os.mkdir(logpath)


        cf = logging.handlers.TimedRotatingFileHandler(logpath +'/' + Defaults.LOG_FILE,when='midnight',interval=1,backupCount=0,utc=True)
        cf.setFormatter(formatter)
        cf.setLevel(file_loglvl)

        logger.addHandler(cf)

        logger.info("File-logging enabled to %s"%(logpath))


    logger._has_been_setup = True


def schedule_regular_callback(func, delay):
    cb =  RegularCallback(func, delay)
    cb.start()
    return cb




def _print( *arg, **kwarg):
    """
        Function to print.

        This wrapper funciton is provided to allow for more easy redirection
        of output to other destinations (including Bokeh GUI, or files) if
        necessary.

        It should be used for information targeted at an interactive user, not
        for logging messages

    """

    print(*arg, **kwarg)




def bytes2prettyhex(data, whitespacelen= Defaults.LOG_STRING_LEN):

    #log.info(st)

    st = ''
    if data is not None:
        data_array = bytearray(data)
        datastr=["%02X"%(x) for x in data_array]
        N = range(0, len(datastr), 16)
        for n in N:
           st += '\n' + (' '*whitespacelen) + "{:06x}  ".format(n) + "-".join(datastr[0+n:16+n])

    return st

def bytes2hex(data):
    data =bytearray(data)
    return('-'.join(["%02X"%(x) for x in data]))


def hex2bytes(hexstr):
    data = hexstr.split('-')
    return bytearray(''.join([chr(int(x, 16)) for x in data]))



class XMLRPCTimeoutServerProxy(RPCClient):
    """
    .. warning::

        Deprecated in favor of RPCClient. The implmeentation is now just that this is an alias for RPCClient

    .. todo::

        Refactor the code to no longer use this so we can delete
    """
    pass




if __name__ == '__main__':
    x = 2
    setup_logger(log, cons_loglvl=logging.DEBUG)
    #m = Monitor(dt = 1)
    #fn = lambda: x
    #alfn = lambda r: 'RED' if r < 0 else 'GREEN'
    #m.register_monitor('blah test', 5, fn, alert_fn = alfn)
    #m.start()
