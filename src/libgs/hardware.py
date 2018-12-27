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



Created on Fri Jan 12 13:17:51 2018

@author: kjetil
"""


import time
import socket
from utils import Error, RegularCallback, Defaults, wait_loop, conv_time, XMLRPCTimeoutServerProxy, raise_if_aborted, AbortAllException
import xmlrpclib
from pandas import DataFrame
import sys
from os.path import abspath
import os
from math import pi
import angles
import subprocess
import select
import threading
import random
import re
from collections import deque
import zmq
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import serial
import time


import logging
log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())


class RotatorBase(object):
    """
    Base class for any rotator hardware interface

    The following configuration parameters can be changed by any derived class in order to appropriately configure
    the rotator

    ======================= ===================
    Parameter               Description
    ----------------------- -------------------
    STOWED_AZ               Azimuth to move antenna to when stowing
    STOWED_EL               Elevation to move antenna to when stowing
    BEAMWIDTH               Antenna beamwidth (used when calculating granularity of antenna movements)
    MAX_AZ                  Maximum allowed Azimuth
    MIN_AZ                  Minimum allowed Azimuth
    MAX_EL                  Maximum allowed Elevation
    MIN_EL                  Minimum allowed Elevation
    SLEW_TIMEOUT            Max time to wait while waiting for slewing to complete
    ======================= ===================

    """

    #
    # Any derived class may change these variables
    # to suit the rotator type
    #

    #: Stowed position
    STOWED_AZ = Defaults.ROTATOR_STOWED_AZ
    STOWED_EL = Defaults.ROTATOR_STOWED_EL

    #: Antenna beamwidth
    BEAMWIDTH = Defaults.ROTATOR_ANTENNA_BEAMWIDTH

    #: Maximum allowd azimuth command
    MAX_AZ = Defaults.ROTATOR_MAX_AZ

    #: Minimum allowed azimuth command
    MIN_AZ = Defaults.ROTATOR_MIN_AZ

    #: Maximum allowed elevation command
    MAX_EL = Defaults.ROTATOR_MAX_EL

    #: Minimum allowed elevation command
    MIN_EL = Defaults.ROTATOR_MIN_EL

    #: Slewing Timeout (s)
    SLEW_TIMEOUT = Defaults.ROTATOR_SLEW_TIMEOUT

    # Instance counter (for unnamed rotators)
    _instance_name_cntr = 0

    #####
    #
    # Properties for getting/setting the radio name. If no name is supplied, none is generated based
    # on the isntance counter
    #
    #####
    @property
    def name(self):
        if not hasattr(self, '_name'):
            self._name = 'Rotator{:03d}'.format(RotatorBase._instance_name_cntr)
            RotatorBase._instance_name_cntr += 1
        return  self._name

    @name.setter
    def name(self, name):
        self._name = name



    ####################
    #
    # Internal methods
    #
    ####################
    def __str__(self):
        return "< Rotator (name = '{}') >".format(self.name)

    def __repr__(self):
        return self.__str__()

    ####################
    #
    # Private methods
    #
    ####################


    def _wait_for_in_pos(self, az = None, el = None):
        t0 = time.time()
        last_print_t = t0

        while not self.in_pos(az, el):
            if time.time() - t0 > self.SLEW_TIMEOUT:
                raise Error('Timed out waiting for antenna to complete slewing')

            if time.time() - last_print_t > 2.0:
                log.debug("Antenna slewing - currently at az={:.1f}, el={:.1f}".format(*self.azel))
                last_print_t = time.time()

                # TODO: Remove. This is not really necessary except if rotctl/socat crashes while we are waiting
                if az is not None and el is not None:
                    self.set_azel(az, el, block=False)
                if self.cmd_az is not None and self.cmd_el is not None:
                    try:
                        self.set_azel(self.cmd_az, self.cmd_el, block=False)
                    except Exception as e:
                        log.debug("Error communicating with hamlib while waiting for positioning, no biggie so ignoring {}".format(e))

            time.sleep(0.1)

    ####################
    #
    # Public methods
    #
    ####################

    def stow(self, block=False):
        """
        Stow antenna
        """
        self.set_azel(self.STOWED_AZ, self.STOWED_EL, block=block)


    def azel_err(self, az, el):

        def az_dist(az1, az2):
            az1 = az1%360
            az2 = az2%360

            if ((360-az1) < az1) and ( (360 - az2) > az2):
                return (az2+360) - az1
            elif ((360-az1) > az1) and ( (360 - az2) < az2):
                return (az1 + 360) - az2
            else:
                return abs(az1-az2)


        def el_dist(el1, el2):
            el1 = el1%180
            el2 = el2%180

            if ((180-el1) < el1) and ( (180 - el2) > el2):
                return (el2+180) - el1
            elif ((180-el1) > el1) and ( (180 - el2) < el2):
                return (el1 + 180) - el2
            else:
                return abs(el1-el2)

        az1,el1 = self.get_azel()

        return (az_dist(az1, az), el_dist(el1, el))


    def in_pos(self, az = None, el = None):
        """
        Check if antenna is in position

        Returns:
            True if antenna is in position, False otherwise
        """

        if hasattr(self, 'cmd_az') and az is None:
            az = self.cmd_az
        if hasattr(self, 'cmd_el') and el is None:
            el = self.cmd_el

        if (az is None or el is None):
            raise Error("in_pos called with arguments az={} and el={}, which is invalid".format(az,el))

        if az is None and el is None:
            az = self.cmd_az
            el = self.cmd_el
        azerr, elerr = self.azel_err(az, el)

        if azerr < self.BEAMWIDTH/2.0 and elerr < self.BEAMWIDTH/2.0:
            return True
        else:
            return False



    def azel_to_antenna_angles(self, pdat, cont_track_method= None):
        """
        From a table of az/el pointings, compute a new table that minimises the
        amount of movements while keeping the off-pointing within the antenna
        beamwidth

        Note: this method does *not* interpolate, it just uses nearest neighbour
              so pdat must be at sufficient time resolution.


        Also transform antenna pointing vectors in such a way that the antenna will track continously  throughout
        the pass. We do this by checking if the antenna ever needs to enter both the NE and NW quarters, and
        if so, depending on the antenna rotator capabilities we can use one of 2 methods to achieve a continous
        (up to 3 quadrant) track.
          * flipover:         We move the antenna in the 90 -- 180 degree extended elevation range
          * extended_azimuth: We move the antenna in the 360 -- 540 degree extended azimuth range

        4 quadrant tracking is not currently supported. If the trajectory enters 4 quadrants, or if the antenna
        capabilities do not meet the requirements for flipover or extended_azimuth, then the antenna will be commanded
        in the "normal" 0-360 az and 0-90 el range and there may be discontinuities.

        args:
           pdat (DataFrame): must have at least an az and el column.
           cont_track_method (str): Try to force a continous tracking method. If omited a method will be chosen
                             based on antenna capabilities.
        """

        if not isinstance(pdat, DataFrame):
            raise Error("pdat must be a DataFrame, got {}".format(type(pdat)))

        if 'az'not in pdat.columns or 'el' not in pdat.columns:
            raise Error("pdat must have at least an az and el column")


        #
        # Transform antenna pointing vectors in such a way that the antenna will track continously  throughout
        # the pass. We do this by checking if the antenna ever needs to enter both the NE and NW quarters, and
        # if so, depending on the antenna rotator capabilities we can use one of 2 methods to achieve a continous
        # (up to 3 quadrant) track.
        #   * flipover: We move the antenna in the 90 -- 180 degree extended elevation range
        #   * extended_azimuth: We move the antenna in the 360 -- 540 degree extended azimuth range
        #
        # 4 quadrant tracking is not currently supported. If the trajectory enters 4 quadrants, or if the antenna
        # capabilities do not meet the requirements for flipover or continue, then the antenna will be commanded
        # in the "normal" 0-360 az and 0-90 el range and there may be discontinuities.
        #

        if cont_track_method is None:
            # TODO (maybe one day): Enable 4 quadrant continous tracking by utilising extended range (360->450 deg)
            if self.MAX_AZ >= 540:
                cont_track_method = 'extended_azimuth'
            elif self.MAX_EL >= 180:
                cont_track_method = 'flipover'
            else:
                cont_track_method = 'none'

        # Compute quadrants the trajectory passes through
        quadrants = set([('N' if p.az < 90 or p.az > 270 else 'S') + ('E' if p.az < 180 else 'W') for _, p in pdat.iterrows()])

        # Note NE and NW in quadrants and len(q) <=3 implies that SW and SE cant both be passed through and so the below
        # works. It would *not* work if the track crossed the SW-SE boundary.
        if len(quadrants) <= 3 and 'NE' in quadrants and 'NW' in quadrants and cont_track_method == 'flipover':
            # Make sure antenna tracks continously when crossing NE->NW boundary by flipping antenna over
            # i.e by applying elevation angles between 180 -> 90, and adjusting azimuth appropriately.
            log.info('Antenna track crosses between NE and NW quadrant. Using "flipover" method for continous tracking')
            pdat = pdat.copy()
            pdat.az -= 180
            pdat.loc[pdat.az < 0, 'az'] += 360
            pdat.el = 180 - pdat.el
        elif len(quadrants) <= 3 and 'NE' in quadrants and 'NW' in quadrants and cont_track_method == 'extended_azimuth':
            # Make sure antenna tracks continously when crossing NE-->NW boundary by using the 180-->540 azimuth
            # range instead of 0 --> 360
            #
            log.info('Antenna track crosses between NE and NW quadrant. Using "extended_azimuth" method for continous tracking')
            pdat = pdat.copy()
            pdat.loc[pdat.az < 180, 'az'] += 360
        else:
            if len(quadrants) > 3:
                log.warning("4 Quadrant continous tracking is not currently supported.")

            az = pdat.az
            el = pdat.el


        ant_p = DataFrame(columns=pdat.columns)
        ant_p = ant_p.append(pdat.iloc[0])


        R2D = 180.0/pi
        D2R = pi/180.0

        for k,r in pdat.iterrows():
            s = angles.sep(ant_p.iloc[-1].az*D2R, ant_p.iloc[-1].el*D2R, r.az*D2R, r.el*D2R)*R2D

            if (s >= self.BEAMWIDTH/2.2): #<--- half beamwdith less 10% margin
                ant_p = ant_p.append(r)

        if len(ant_p) > 1:
            t = ant_p.index[:-1:2]
            ant_p = ant_p.iloc[1::2]
            ant_p.index =t
        elif len(ant_p) == 0:
            raise Error("Failed to compute any antenna points")

        return ant_p



    ####################
    #
    # Interface methods. Shall be overloaded
    #
    ####################

    def get_azel(self):
        raise Error("Rotator.get_azel was called but has not been implemented")

    def set_azel(self, az, el, block):
        raise Error("Rotator.set_azel was called but has not been implemented")

    def get_azel_rate(self):
        raise Error("Rotator.get_azel_rate was called but has not been implemented")

    def set_azel_rate(self, az, el, block):
        raise Error("Rotator.set_azel_rate was called but has not been implemented")



    #####################
    #
    # Also allow access via properties because some people prefer that
    #
    #####################

    @property
    def azel(self):
        return self.get_azel()

    @azel.setter
    def azel(self, val):
        self.set_azel(*val, block=True)

    @property
    def az(self):
        return self.get_azel()[0]

    @az.setter
    def az(self, val):
        a,e = self.get_azel()
        self.set_azel(val, e, block=True)

    @property
    def el(self):
        return self.get_azel()[1]

    @el.setter
    def el(self, val):
        a,e = self.get_azel()
        self.set_azel(a, val, block=True)

    @property
    def cmd_az(self):
        if not hasattr(self, '_cmd_az'):
            return 0
        else:
            return self._cmd_az

    @cmd_az.setter
    def cmd_az(self, az):
        self._cmd_az = az

    @property
    def cmd_el(self):
        if not hasattr(self, '_cmd_el'):
            return 0
        else:
            return self._cmd_el

    @cmd_el.setter
    def cmd_el(self, el):
        self._cmd_el = el

    @classmethod
    def _assure_azel_in_range(cls, fn):

        def wrapped(self, az, el, *args, **kwargs):
            if az < self.MIN_AZ:
                log.debug("commanded az = {:.1f} deg < MIN_AZ, using MIN_AZ = {:.1f} deg".format(az, self.MIN_AZ))
                az = self.MIN_AZ

            if az > self.MAX_AZ:
                log.debug("commanded az = {:.1f} deg > MAX_AZ, using MAX_AZ = {:.1f} deg".format(az, self.MAX_AZ))
                az = self.MAX_AZ

            if el < self.MIN_EL:
                log.debug("commanded el = {:.1f} deg < MIN_EL, using MIN_EL = {:.1f} deg".format(el, self.MIN_EL))
                el = self.MIN_EL

            if el > self.MAX_EL:
                log.debug("commanded el = {:.1f} deg > MAX_EL, using MAX_EL = {:.1f} deg".format(el, self.MIN_EL))
                el = self.MAX_EL

            # Also use this wrapper to ensure cmd_az and cmd_el gets set.
            self.cmd_az = az
            self.cmd_el = el

            return fn(self, az, el, *args, **kwargs)

        return wrapped

class DummyRotator(RotatorBase):
    """
    A dummy class that responds like the rotator but does nothing
    """

    def get_azel(self):
        return self._azel

    @RotatorBase._assure_azel_in_range
    def set_azel(self, az, el, block=False):
        self._azel = (az, el)






class GS232B(RotatorBase):
    """
    This Rotator class implements a subset of the Yaesu GS232-B protocol.

    It can be used directly to control rotators either directly connected via USB or serial port as a local tty
    or remotely over the ethernet. The initialiser url_or_dev is used to specify how to connect.

    See https://pythonhosted.org/pyserial/url_handlers.html for the syntax.


    Available configuration parameters are all of RotatorBase as well as the following additional parameters

    ======================= ===================
    Parameter               Description
    ----------------------- -------------------
    STALE_TIME              Time before azel reading is considered stale (default = 3 seconds)
    SERIAL_PORT_TIMEOUT     Timeout delay waiting for serial port comms (default = 0.1 seconds)
    ROT_SETTLETIME_GET      Delay after getting position from rotator (default = 0 seconds)
    ROT_SETTLETIME_SET      Delay after setting position from rotator (default = 0.75 seconds)
    SET_DT                  Time interval to wait before re-issuing a position command (default = 10 seconds, ignored if SET_REGULARLY = False)
    GET_DT                  Time delay to wait between consecutive attempts to get position (default = 0 seconds)
    SET_REGULARLY           Whether to continuously issue set commands to rotators, or only on request. (Default=True)
    ======================= ===================

    """


    ############
    #
    # Configuration parameters
    #
    ############


    #
    # Within STALE_TIME, if no reply can be obtained from rotator return the last valid reply
    #
    STALE_TIME = 3

    #
    # Allowed time to wait for a byte from the serial port
    #
    SERIAL_PORT_TIMEOUT = .1


    # SETTLETIME is a delay the system gives the rotator controller before trying to send any more commands
    ROT_SETTLETIME_GET = 0.0
    ROT_SETTLETIME_SET = 0.75

    # Time interval at which position is attempted to be set again
    SET_DT = 10

    # Maximum time interval at which position is polled (if smaller than _POLL_DT, _POLL_DT will win)
    GET_DT  = 0

    # set to false to only set position when set_azel is called explicitly.
    SET_REGULARLY = True


    ############
    #
    # Private config parameters
    #
    ############

    # Max time to wait for serial port to become available before
    # writing to it
    _WAIT_TIMEOUT = 1

    #: Tick sleep betwen successive attempts to poll the rotator
    _POLL_DT = .1


    ############
    #
    # Internal methods
    #
    ############

    # Initialise serial port
    def __init__(self, url_or_dev, name=None, serial_conf = {}, **kwargs):
        """

        Args:
            url_or_dev:  URL or device of serial port (TTY)
            serial_conf: Dictionary representing serial port configuration (see See https://pythonhosted.org/pyserial/url_handlers.html )
            **kwargs:    Any available configuration parameter (see above)
        """
        self._ser = self._serial_port(url_or_dev, **serial_conf)
        self._ser.next()  # <-- initialise generator
        self._cur_az = 0
        self._cur_el = 0
        self._last_get_t = 0
        self._set_now = True
        self._last_set_t = 0

        if name is not None:
            self.name = name

        # Parameters that store error states in the poller (if any)
        # ... could be queried with a monitor if necessary.
        self.err_set = None
        self.err_get = None
        self.err_stale = None


        # Allow for setting of other properties
        for k,v in kwargs.items():
            setattr(self, k, v)

        self._stopped = threading.Event()


        self.start()


    ############
    #
    # Private methods
    #
    ############

    def _serial_port(self, url_or_dev, tx_eol = '\r\n', rx_eol = '\r', **kwargs):
        """
        Create a serial port generator. Send commands to it by using
        the generator send() method. It will return whatever comes back
        or None if readline failsself.

        Note: we do it this way to avoid conflicting writes to the serial
        port from different threads. If that's attempted, a ValueError: generator is already executing
        Exception will happen.
        """

        if 'timeout' not in kwargs.keys():
            kwargs['timeout'] = 1.0

        try:
            _ser = serial.serial_for_url(url_or_dev, **kwargs)
        except AttributeError:
            _ser = serial.Serial(url_or_dev, **kwargs)


        if len(rx_eol) != 1:
            raise Error("rx_eol parameter can only be a single character long")

        def readline(_ser=_ser, rx_eol=rx_eol):
            data = ''
            while True:
                b = _ser.read(1)
                data += b
                if b == '' or b == rx_eol:
                    break

                # Make loop abortable by making the abort_all event raise an exception
                raise_if_aborted()

            return data

        outp = None
        exc = None
        # t0 = time.time()
        # t1 =t0
        while True:
            #print('BLAH. Time through loop = {:.2f}, time waiting for yield = {:.2f}'.format(time.time() - t0, t1-t0))
            # t0 = time.time()
            inp = yield (outp, exc)
            # t1 = time.time()
            try:
                _ser.write((inp.strip() + tx_eol).encode())

                outp = readline()

                if outp == '':
                    raise Exception('Timeout: No response')

                exc = None
            except Exception as e:
                outp = None
                exc = e

    def _parse_get_reply(self, s):
        """
        This method parses the string returned from the rotator controller when a position has been
        requested in order to return az and el (as floats). For rotator controllers that do not
        quite adhere to the GS232B standard the class can be subclassed and this method overloaded
        to properly parse the reply.
        """
        split_s = re.split(' +', s.strip())
        azeldict = {y.split('=')[0]: y.split('=')[1] for y in split_s[-2:]}
        az = float(azeldict['AZ'])
        el = float(azeldict['EL'])
        return az,el

    def _parse_set_reply(self, s):
        if s.strip() == '':
            return True
        else:
            return False

    def _pthr_update(self):
        while True:
            self._update_rotator()

            try:
                if not wait_loop(self._stopped, timeout = self._POLL_DT) is None:
                    log.debug("Exiting GS232B polling loop due to stop() being called")
                    break
            except:
                log.debug("Exiting GS232B polling loop due to global abort")
                break

    def _update_rotator(self):
        """
        This method syncs the position state between the rotator and this class by
        1) attempt to send cmd_az, cmd_el to the rotator
        2) read current az,el from rotator

        NOTE: This method is called in a thread through RegularCallback. It should therefore be acceptable to
        have it block and/or raise exceptions and it will not affect anything else.

        """

        SET_TIMEOUT = .3
        GET_TIMEOUT = .3



        #
        # Set position to cmd_az, cmd_el
        #
        if self._set_now or (self.SET_REGULARLY and (time.time() - self._last_set_t  > self.SET_DT)):
            try:
                self._set_azel(self.cmd_az, self.cmd_el, timeout = SET_TIMEOUT)
                if self.err_set:
                    log.debug("Setting azel now works again")
                    self.err_set = None
            except Exception as e:
                if not self.err_set:
                    log.error("Exception setting azel. (This error will only be shown once) {} : {}".format(e.__class__.__name__, e))
                    self.err_set = e

        self._set_now = False

        #
        # Get current position
        #
        if time.time() - self._last_get_t  > self.GET_DT:
            try:
                self._cur_az, self._cur_el = self._get_azel(timeout = GET_TIMEOUT)
                self._last_get_t = time.time()
                if self.err_get:
                    log.debug("Getting azel now works again")
                    self.err_get = None

            except Exception as e:
                if not self.err_get:
                    log.error("Exception getting azel (This error will only be shown once). {} : {}".format(e.__class__.__name__, e))
                    self.err_get = e


    def _send_ser_cmd(self, cmd, timeout=.5):
        ret = None
        exc = None
        t0 = time.time()
        while ret is None and exc is None:
            try:
                ret, exc = self._ser.send(cmd)
            except ValueError:
                if time.time() - t0 > timeout:
                    raise Error("Timeout waiting for serial port to be free")
                else:
                    wait_loop(timeout=.01)

        if exc is not None:
            raise exc

        return ret

    def _set_azel(self, az, el, timeout=.5):
        """
        This method sends the command to set the position to the rotator.
        If anything goes wrong it raises an exception
        """

        try:
            ret = self._send_ser_cmd('W{:03.0f} {:03.0f}'.format(az, el), timeout=timeout)
        except:
            raise #<--- timeout

        if not self._parse_set_reply(ret):
            estr = "Unexpected response when setting azel: '{}'".format(ret.encode('string_escape'))
            raise Error(estr)

        #Allow the controller time to settle
        wait_loop(timeout=self.ROT_SETTLETIME_SET)


    def _get_azel(self, timeout=.5):
        """
        This method sends the command to get the position to the rotator.
        If anything goes wrong it raises an exception
        """

        try:
            ret = self._send_ser_cmd('C2', timeout=timeout)
        except:
            raise #<-- timeout

        try:
            az, el = self._parse_get_reply(ret)
        except:
            estr = "Unexpected response when getting azel: '{}'".format(ret.encode('string_escape'))
            raise Error(estr)


        #Allow the controller time to settle
        wait_loop(timeout=self.ROT_SETTLETIME_GET)


        return az, el


    ############
    #
    # Public methods
    #
    ############


    ##### OVERLOADED ########
    def get_azel(self):
        if time.time() - self._last_get_t > self.STALE_TIME:
            if not self.err_stale:
                log.error("get_azel() - data is stale (no update in STALE_TIME = {} sec). Returning 0,0. (This error will only be shown once)".format(self.STALE_TIME))
            self.err_stale = Exception('get_azel: No update in STALE_TIME = {} sec). Returning 0,0'.format(self.STALE_TIME))
            return 0.0, 0.0
        else:
            self.err_stale = None
            return self._cur_az, self._cur_el

    @RotatorBase._assure_azel_in_range
    def set_azel(self, az, el, block=False):
        self.set_now = True

        if block:
            try:
                self._wait_for_in_pos()
            except Exception as e:
                log.error("Error waiting for antenna to position itself. {}: {}".format(e.__class__.__name__, e))

    ###### OTHER #########
    def start(self):

        # Start polling thread (will run forever)

        self._pthr = threading.Thread(target = self._pthr_update)
        self._pthr.daemon = True
        self._pthr.start()

        # stow on startup if we are setting regularly (otherwise the default is 0,0 which may not be good)
        if self.SET_REGULARLY:
            self.stow(block=False)

    def stop(self):
        self._stopped.set()



class RotCtld(RotatorBase):
    """
       Interface to hamlib rotators using Rotctld

       This class will continously poll hamlibs rotctld over TCP and
       store the position. Requests  to get_azel will return this stored position rather than trigger a
       request to hamlib. This makes the class thread-safe.

       .. note::

          For rotators that support the GS232B protocol, use the GS232B class instead of RotCtld. It does not depend
          on hamlib and is more actively maintained than this class.

    """



    #: Update interval for position values
    _POLL_DT =  0.2

    #: Max age of position values before an exception is raised for staleness
    _POS_STALE_DT = 10*_POLL_DT


    def __str__(self):
        s = "hamlib rotctld@{}:{}".format(self.addr, self.port)
        return s

    def __repr__(self):
        return self.__str__()


    def __init__(self, addr, port, name = None, persist=True, **kwargs):
        self.addr = addr
        self.port = port
        self._persist = persist
        self._locked =  False
        #self._get_position_failures = 0

        if name is None:
            self._name = '{}:{}'.format(addr, port)
        else:
            self._name = name

        if self._persist is True:
            try:
                self._connect()
            except:
                log.error("Failed to connect to hamlib. {}: {}".format(e.__class__.__name__, e))

        self._last_az = 0.0
        self._last_el = 0.0



        self._last_update =  time.time()
        self._pos_poller = RegularCallback(self._poll_azel, self._POLL_DT)
        self._pos_poller.start()

        #: Commanded azimuth position
        self.cmd_az = 0

        #: Commanded elevation
        self.cmd_el = 0


        # start by moving antenna to stowed position
        # TODO: Maybe re-implement. Disabled now to permit system to start despite errors
        # try:
        #     self.stow(block=False)
        # except Error, e:
        #     log.error('Error initialising Rotator at %s:%s - "%s"'%(addr, port, e))
        # except:
        #     raise

        for k,v in kwargs.items():
            setattr(self, k, v)



    def _connect(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.settimeout(1)
            self._sock.connect((self.addr, self.port))
        except:
            del self._sock
            raise


    def _close(self):
        self._sock.close()
        del(self._sock)

    def _lock(self):

        t0 = time.time()

        LOCK_TIMEOUT = 2

        while(self._locked):
            time.sleep(0.025)

            if time.time() - t0 > LOCK_TIMEOUT:
                raise Error("TIMEOUT while waiting for Rotctld communication lock")


        self._locked = True


    def _unlock(self):
        self._locked = False

    def _poll_azel(self):
        """
            Get the current AZ,EL by querying hamlib.

            This function is not thread-safe and not intended to be run
            outside this class. Use get_azel() instead.

            Returns:
                azimuth, elevation
        """

        self._lock()

        try:

            if self._persist is False or not hasattr(self, '_sock'):
                self._connect()

            self._sock.sendall("p")
            resp = self._recv_all()

            if resp[0:4] == 'RPRT':
                s = 'Got invalid az/el information from hamlib'
                log.error(s)
                self._unlock()
                raise Error(s)


            try:
                az, el = resp.split('\n')[0:2]
                self._last_az = float(az)
                self._last_el = float(el)

            except Exception, e:
                s= "Error converting hamlib data '%s' to az/el. Error: '%s'"%(resp, e)
                log.error(s)
                self._unlock()
                raise Error(s)


            self._last_update = time.time()

            if self._persist is False:
                self._close()
        finally:
            self._unlock()


    def get_azel(self):
        """
            Return the most current AZ,EL.

            Returns:
                azimuth, elevation

        """
        

        if time.time() - self._last_update > self._POS_STALE_DT :
            msg = "AZ/EL are stale. Not receiving updates from hamlib?"
            log.error(msg)
            raise Error(msg)


        return self._last_az, self._last_el



    def _recv_all(self):

        timeout = self._sock.gettimeout()

        s = ''
        while True:
            try:
                s+=self._sock.recv(1024)
                self._sock.settimeout(0)
            except:
                break;

        self._sock.settimeout(timeout)
        return s

    @RotatorBase._assure_azel_in_range
    def set_azel(self, az, el, block=True, debug=False, callback=None):
        """
            Set the AZ, EL

            Args:
                az (float): Azimuth in degrees
                el (float): Elevation in degrees
                block (bool, optional): True will halt execution until pointing has been achieved
        """


        self._lock()



        if self._persist is False:
            self._connect()


        self._sock.sendall('P %.2f %.2f\n'%(az, el))



        # TODO: This function should really block for a bit (the get_position should not)
        resp = self._recv_all()#self._sock.recv(1024)[:6]

        try:
            r = resp.rstrip().split('\n')[0].split(' ')

            rets = r[0]
            retc = r[1]

        except:
            s = ("Invalid response from hamlib '%s' when setting az/el "%(resp))
            self._unlock()
            raise Error(s)



        if rets != 'RPRT' :
            s = ("Invalid response from hamlib '%s' when setting az/el "%(resp))
            self._unlock()
            raise Error(s)

        # if command wasn successful try again
        if int(retc) != 0:
            self.set_azel(az, el, block, debug, callback)
            log.warn('Invalid response from hamlib (error code %d) while trying to set az/el, trying again'%(retc))





        if self._persist is False:
            self._close()

        #: Commanded azimuth position
        self.cmd_az = az

        #: Commanded elevation
        self.cmd_el = el

        self._unlock()



        if block is True:
            self._wait_for_in_pos()





# For now we have made Rotator an alias for RotCtld
# TODO: Remove. This is for backwards compatability only
class Rotator(RotCtld):
    pass



class RadioBase(object):
    """
    Base class for Radio object.
    """
    
    _fftsize = 1024

    # Exceptions that happen during range rate setting /getting will not be raised.
    # but they will be stored here so that a monitor can poll them if desired.
    err_range_rate_set = None
    err_range_rate_get = None

    # Instance counter (for unnamed radios)
    _instance_name_cntr = 0


    #####
    #
    # Properties for getting/setting the radio name. If no name is supplied, none is generated based
    # on the isntance counter
    #
    #####
    @property
    def name(self):
        if not hasattr(self, '_name'):
            self._name = 'Radio{:03d}'.format(RadioBase._instance_name_cntr)
            RadioBase._instance_name_cntr += 1
        return  self._name

    @name.setter
    def name(self, name):
        self._name = name




    ##############################################
    #
    # Interface methods (to be overloaded)
    #
    ##############################################
    
    def send_bytes(self):
        """
        send_bytes should send a byte sequence to the radio for modulation
        and transmission
        """
        raise Error("Radio.send_bytes has not been implemented")
        
    def set_recv_callback(self, callable):
        """
        det_recv_callback should set a callable to be invoked when radio 
        receives a packet.
        """
        raise Error("set_recv_callback has not been implemented")


    def get_spectrum(self, old=False):
        raise Error("Radio.get_spectrum was called but has not been implemented")
        
    def get_range_rate(self):
        """
        get_range_rate shoudl return the currently set range_rate
        """
        raise Error("Radio.get_range_rate was called but has not been implemented")

    def set_range_rate(self, range_rate):
        """
        set_range_rate should set frequency adjustment for a specific range_rate
        """
        raise Error("Radio.set_range_rate was called but has not been implemented")


    ###########
    #
    # Also define some property for easy access for those who prefer that
    #
    ###########
    @property
    def range_rate(self):
        try:
            rr =  self.get_range_rate()
            self.err_range_rate_get = None
            return rr
        except Exception as e:
            self.err_range_rate_get = e
            raise

    @range_rate.setter
    def range_rate(self, range_rate):
        try:
            self.set_range_rate(range_rate)
            self.err_range_rate_set = None
        except Exception as e:
            self.err_range_rate_set = e
            raise

    ###################
    #
    # Other methods
    #
    ###################
    def record_spectrum(self, dt = 1, N = 100, fdec = 1, add_zeroes = False):
            """
            Record N spectra then return them. This method returns a future.
            
            To get the result call the future.result(). To stop it call
            future.abort() #<--- note non-standard future call
            
            Args:
               dt = rate at which to record the spectra
            """
            
            abort = threading.Event()
            
            def _pthr_record():
                spec = [None]*N
                ok_idx = [False] * N
                tvec   = [0.0] * N
                fvec = []
                abort.clear()
                
                t0 = time.time()
                
                last_spec = None
                for n in range(N):
                    try:

                        t0 = time.time()                            
                        tvec[n] = t0


                        dt1 = (dt - (time.time() - t0))
                        if dt1 > 2.0:
                            if abort in wait_loop([abort], timeout=dt1):
                                break
                        else:
                            time.sleep(dt1)
                            if abort.is_set():
                                break
                        
                        
                        try:
                            ret = self.get_spectrum()
                        except:
                            continue
                        

                        if len(ret) != 2:
                            raise Error("get_spectrum did not return valid freq, spec")

                        fv, sp = ret[0][::fdec], ret[1][::fdec]
                        
                        # Check if there is something new, if not skip
                        if last_spec is not None and all(sp[i] == last_spec[i] for i in range(len(sp))):
                            continue

                        last_spec = sp[:]

                        fvec, spec[n] = fv, sp 
                        ok_idx[n] = True

                        

                    except Exception as e:
                        log.error("Error {} while recording spectrum. Ignoring and continuing: {}".format(e.__class__.__name__, e))
               
                spec = [[0.0]*len(fvec) if x is None else list(x) for x in spec]

                lens = [len(s) for s in spec]
                if not all([l == lens[0] for l in lens]):
                    raise Error("Unexpected error recording spectra. Not all spectra are same length")
                    

                if len(fvec) == 0:
                    raise Error("No data recorded")

                # Trim data that wasnt filled (in case abort wwas called)
                spec = spec[:(n+1)]
                tvec = tvec[:(n+1)]
                ok_idx = ok_idx[:(n+1)]

                spec = np.array(spec)
                # Get rid of bad data unless zeroes are requested
                if not add_zeroes:                    
                    spec = spec[ok_idx, :]
                    tvec = [tvec[k] for k,ok in enumerate(ok_idx) if ok]
                    
                dvec = [conv_time(t, to="datetime", float_t="unix") for t in tvec]
                return fvec, dvec, spec
            
            _executor = ThreadPoolExecutor(1)
            future = _executor.submit(_pthr_record)
            #future = self._executor.submit(_pthr_record) #<--- using external executor makes the thread not exit when calling aboort
            future.abort = abort.set
            return future



class GR_XMLRPCRadio(RadioBase):
    """
    Class for driving radios over RPC (mainly Gnu radio flowgraphs that
    include an XMLRPC block)
    
    GNU radio flowgraphs with an XMLRPC block will expose all variables through
    get_<varname> and set_<varname> rpc calls.
    
    This class uses those calls to set/get spectrum parameters and set/get
    the range_rate.
    
    The flowgraph therefore needs to include variables for
      * range rate (in m/s)
      * centre frequency (in Hz)
      * bandwidth (in Hz)
    
    They can be called anything as the variable names can be mapped using
    the rpc_varmap parameter.
    
    Additionally, the flowgraph needs to publish the raw IQ samples (complex64 type)
    on a ZMQ port, which can be mapped using this class's stream parameter 
    """

    def __init__(self,
                 name,
                 stream,
                 rpcaddr,
                 rpc_varmap = {},
                 iqbufflen = 1024,
                 connect=True):
        """
        Args:
            name (string)    : A descriptive name for the radio
            stream (string)  : The IP:PORT on which to listen for published IQ samples
            rpcaddr (string) : The RPC address (in format http://ip:port) to connect the XMLRPC proxy to
            rpc_varmap       : A dict mapping between freq, sample_rate and range_rate to whatever
                               those variables are called in the Gnu Radio flowgraph.
        """
                 
        
        self.name = name
        self.stream = stream
        self._rpcaddr = rpcaddr
        self._iqbuff = deque(maxlen=iqbufflen)
        self._fftsize = 1024
        try:
            self._iqaddr, self._iqport = stream.split(':')
        except Exception as e:
            log.error("Did not understand stream address {}".format(stream))
            raise

        self._iqport = int(self._iqport)
        self._last_sample_rate = 100e3
        self._last_freq = 0
        self._iqrxcnt = 0
        self._lastiqrxcnt = 0

        # Store errors (if any)
        self.err_sample_rate = None
        self.err_freq = None

        #
        # Set a default RPC map
        #
        self._callback_map = {
            'freq':        'freq',
            'sample_rate': 'sample_rate',
            'range_rate':  'range_rage'}
                 
        for k,v in rpc_varmap.items():
            if k not in self._callback_map:
                raise Error("Unknown key %s in variable map"%(k))
            else:
                self._callback_map[k] = v

        #self._server = xmlrpclib.ServerProxy(self._rpcaddr)
        #self._server = XMLRPCTimeoutServerProxy(self._rpcaddr, timeout=.25)
        
        if connect:
            self.connect()
                
                
    def _rpc_get(self, var):
        if var in self._callback_map.keys():
            var = self._callback_map[var]

        _server = XMLRPCTimeoutServerProxy(self._rpcaddr, timeout=.25)
        return eval('_server.get_{}()'.format(var))
        
    def _rpc_set(self, var, val):      
        if var in self._callback_map.keys():
            var = self._callback_map[var]

        _server = XMLRPCTimeoutServerProxy(self._rpcaddr, timeout=.25)
        return eval('_server.set_{}({})'.format(var, val))


    def _recv_iq_thread(self):

        poller = zmq.Poller()
        poller.register(self._sock_iq, zmq.POLLIN)

        self._iqrxcnt = 0

        while True:
            sock = poller.poll(1.0)
            
            for s, event in sock:
                data = s.recv()
                data_vals = list(np.frombuffer(data, dtype=np.complex64))
                self._iqbuff += data_vals
                self._iqrxcnt += len(data_vals)                    
                    

            # Dont like this but it is one way to check the abort flag and at the same time
            # trigger on the global abort event.
            try:
                if wait_loop(lambda: self._stop, timeout = 0.0001) is not None:
                    log.debug("recv_iq_thread aborted")
                    break
            except AbortAllException:
                log.debug("abort all exception caught, cancelling _recv_iq_thread")
                break

    def _get_IQ(self, old=False):
        """
        Return the array of IQ data. 
        
        old = True will get the last buffer regardless of whether
        it has been read before.
        """
        
        if (not old) and (self._iqrxcnt < self._lastiqrxcnt + self._iqbuff.maxlen):
            raise Exception("get_IQ: No new data")#data = [np.complex64(np.complex(0,0))]* self._iqbuff.maxlen
        else:
            data = list(self._iqbuff)
            self._lastiqrxcnt = self._iqrxcnt
        
            
        return(data)

    ###############################
    #
    # Interface methods
    #
    ###############################

        
    def get_spectrum(self, old=True):
        """
        get_spectrum should return the latest spectrum from the radio as well
        as an associated frequency vecgor
        
        fvec, famp = get_spectrum()
        
        """
        y = self._get_IQ(old)[-self._fftsize:]

        if len(y) < self._fftsize:
            raise Error("Expected at least {} samples to do fft on".format(self._fftsize)) #<--- could change this to do padding instead
            
        y = 20*np.log10(abs(np.fft.fftshift(np.fft.fft(y, n=self._fftsize))))
            
        x = np.fft.fftfreq(len(y), d = 1.0/self._sample_rate)
        x = (np.fft.fftshift(x) + self._freq)/1e6
        
        return x, y
    
    def set_range_rate(self, range_rate):
        log.debug("Setting range_rate for radio %s to %.0f"%(self.name, range_rate))
        return self._rpc_set('range_rate', range_rate)
    
    def get_range_rate(self):
        return self._rpc_get('range_rate')


    @property
    def _sample_rate(self):

        updated = False
        try:
            self._last_sample_rate = self._rpc_get('sample_rate')

            if self.err_sample_rate is not None:
                log.debug("Successfully reading sample rate again")

            self.err_sample_rate = None
        except Exception as e:
            if self.err_sample_rate is None:
                log.debug("Failed to read sample rate. Using last value (only showing this message once). {}: {}".format(e.__class__.__name__, e))

            self.err_sample_rate = e
        
        return self._last_sample_rate
    
    @property
    def _freq(self):
        try:
            self._last_freq = self._rpc_get('freq')

            if self.err_freq is not None:
                log.debug("Successfully reading frequency again")

            self.err_freq = None
        except Exception as e:
            if self.err_freq is None:
                log.debug("Failed to read frequency. Using last value (only showing this message once). {}:{}".format(e.__class__.__name__, e))

            self.err_freq = e

        
        return self._last_freq
        


    ###############################
    #
    # Other methods
    #
    ###############################
    
    def __str__(self):

        failed = False
        for k,v in self._callback_map.items():
            try:
                self._rpc_get(k)
            except:
                failed = True

        s = "%s <%s>"%(self.name, 'RPC ok' if not failed else 'RPC not ok')
        return s

    def __repr__(self):
        s = "Radio: %s\n"%(self.name)
        s += "  RPC connected: {}\n".format(self._rpcaddr)
        for k,v in self._callback_map.items():
            try:
                self._rpc_get(k)
                state = 'OK'
            except:
                state = 'NOT OK'

            s += "    {:30s}-->{:30s}: {}\n".format(k,v, state)
        s += "  Stream:        {}\n".format(self.stream)
        return s
    

    def connect(self):
        self._context = zmq.Context()
        self._sock_iq = self._context.socket(zmq.SUB)
        self._sock_iq.connect('tcp://{}:{}'.format(self._iqaddr, self._iqport))
        self._sock_iq.setsockopt(zmq.SUBSCRIBE, '')

        self._stop = False
        self._pthr_iq = threading.Thread(target = self._recv_iq_thread)
        self._pthr_iq.daemon = True
        self._pthr_iq.start()

    def disconnect(self):
        self._stop = True
        if hasattr(self, '_pthr_iq'):
            self._pthr_iq.join()


if __name__ == '__main__':
    pass

