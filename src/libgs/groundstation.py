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


Created on Thu May 25 14:08:34 2017

@author: kjetil
"""

import ephem
from datetime import datetime
import time
from math import pi
import pandas as pd
from pandas import DataFrame
import threading
import angles
import sys
from rpc import RPCServer


from utils import Error, RegularCallback, Defaults, wait_loop, conv_time, UTCLogFormatterHTML, AbortAllException, safe_sleep
from monitoring import Monitor
from protocols.protocolbase import  ProtocolBase
from propagator import Propagator
from hardware import RotatorBase, RadioBase, DummyRotator
from database import CommsLog, PassDb




#
# Configure logging
#
import logging
log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())


try:
    #### For plotting
    import matplotlib.pyplot as plt
    import numpy as np
    import io
    _HAS_MPL = True
except:
    _HAS_MPL = False




def _mpl_make_waterfall_jpg(radios, recordings):
    """
    Helper function to create a waterfall plot to store in the databases
    """
    #
    # Convert recorded spectra to images.
    #
    if not _HAS_MPL:
        log.debug("Cannot create waterfall - missing packages. Install matplot + pillow to make this work")
        return None        

    dpi = Defaults.WFALL_JPG_DPI
    fig_h = Defaults.WFALL_JPG_HEIGHT
    fig_w = Defaults.WFALL_JPG_WIDTH_EXTRA + Defaults.WFALL_JPG_WIDTH*len(recordings)
    plt.figure(figsize=(fig_w/dpi, fig_h/dpi), dpi=dpi)
    left_a = None
    dv = None
    for k,radrec in enumerate(recordings):
        a = plt.subplot(1,len(radios), k+1)
        a.set_title(radios[k])

        if k == 0:
            left_a = a

        try:
            fv,dv,sp = radrec.result()
        except:
            a.tick_params(axis='both', which='both', bottom=False, top=False, left=False, right=False,
                          labelbottom=False, labeltop=False, labelleft=False, labelright=False)

            continue
        
        # Get the bad specra (all zeroes)
        bad_spec = np.prod(sp,1) == 0
        minval = np.min(sp)
        sp[bad_spec, :] = minval

        f0 = np.mean(fv)
        a.imshow(sp, extent=((fv[0]-f0)*1000, (fv[-1]-f0)*1000, (dv[-1] - dv[0]).total_seconds(), 0), interpolation="none", cmap=Defaults.WFALL_JPG_COLORMAP)
        a.set_aspect("auto", adjustable="box")
        a.set_xlabel("Frequency (kHz + {:.0f})".format(f0*1000))

        log.info("Radio {}. {} spectra recorded".format(radios[k], sp.shape[0]))

    # Leftmost plot should have a ylabel indicating the start of the pass
    if left_a is not None and dv is not None:
        left_a.set_ylabel("Time (sec + {})".format(conv_time(dv[0], to="datetime").strftime('%Y-%m-%d %H:%M:%S Z')))

    buf = io.BytesIO()
    plt.savefig(buf, format="jpg", dpi=dpi/Defaults.WFALL_JPG_OUT_SCALE)
    image_data = bytearray(buf.getvalue())
    plt.close("all")
    buf.close()
    return image_data

def _compute_antenna_points(pdat, max_offp):

    ant_p = DataFrame(columns=pdat.columns)
    ant_p = ant_p.append(pdat.iloc[0])


    R2D = 180.0/pi
    D2R = pi/180.0

    for k,r in pdat.iterrows():
        s = angles.sep(ant_p.iloc[-1].az*D2R, ant_p.iloc[-1].el*D2R, r.az*D2R, r.el*D2R)*R2D

        if (s >= max_offp):
            ant_p = ant_p.append(r)



    if len(ant_p) > 1:
        t = ant_p.index[:-1:2]
        ant_p = ant_p.iloc[1::2]
        ant_p.index =t
    elif len(ant_p) == 0:
        raise Error("Failed to compute any antenna points")



    return ant_p






class GroundStationBase(object):
    """
    Base class for ground stations.
    
    It implements the necessary interface with exceptions being thrown. 
    By inheriting from this class when making new ground stations you guarantee
    that invalid implementation raises exceptions.
    """
    
    MONITOR_SAVE_DT_TRACK   = Defaults.MONITOR_SAVE_DT_TRACK
    MONITOR_SAVE_DT_NOTRACK = Defaults.MONITOR_SAVE_DT_NOTRACK

    
    ############################
    #
    # Properties
    #
    ############################
    _radios    = []
    _rotators  = []
    _protocol  = None
    _propagator= None
    

    def __del__(self):
        for r in self._radios:
            del r

        for r in self._rotators:
            del r

    @property
    def radios(self):
        return self._radios
    
    @radios.setter
    def radios(self, r):
        if not isinstance(r, list):
            raise Error("radios must be a list of Radio objects, got %s"%(type(r)))
        
        for rr in r:
            if not isinstance(rr, RadioBase):
                raise Error("radios must be a list of Radio objects, got a %s"%(type(rr)))
      
        self._radios = r      
      
    @property
    def rotators(self):
        return self._rotators
    
    @rotators.setter
    def rotators(self, r):
        if not isinstance(r, list):
            raise Error("rotators must be a list of Rotator objects, got %s"%(type(r)))
        
        for rr in r:
            if not isinstance(rr, RotatorBase):
                raise Error("rotators must be a list of Rotator objects, got a %s"%(type(rr)))          
        self._rotators = r
        
    @property
    def protocols(self):
        return self._protocols
        
    @protocols.setter
    def protocols(self, p):
        if not isinstance(p, list):
            raise Error("protocols must be a list of Protocol objects, got %s"%(type(p)))
        
        for pp in p:
            if not isinstance(pp, ProtocolBase):
                raise Error("protocol is of invalid type, got %s"%type(p))
            
        self._protocols = p

    @property
    def protocol(self):
        return self._protocol
        
    @protocol.setter
    def protocol(self, p):
        bad_input = True
        try:
            if (p is None) or isinstance(p, ProtocolBase):
                bad_input = False
                self._protocol = p
            elif isinstance(p, basestring):
                for p1 in self._protocols:
                    if p1.name == p:
                        bad_input = False
                        self._protocol = p1

            log.debug('Protocol has been set to {}'.format(self._protocol))
        finally:
            if bad_input:
                raise Error("protocol must be a valid Protocol class or a string in '%s'"%([pp.name for pp in self.protocols]))


        
    @property
    def propagator(self):
        return self._propagator
        
    @propagator.setter
    def propagator(self, p):
        if p is not None and not isinstance(p, Propagator):
            raise Error("propagator is of invalid type, got %s"%(type(p)))
        
        self._propagator = p

    @property
    def monitor(self):
        if hasattr(self, '_monitor'):
            return self._monitor
        else:
            return None
            
    @monitor.setter
    def monitor(self, m):
        if not isinstance(m, Monitor):
            raise Error("Error setting monitor, expected object of type Monitor, got {}".format(m))
        else:
            self._monitor = m
            # self._monitor_logger = IntervalCallback(self._monitor_logger_cb, dt = self.MONITOR_SAVE_DT_NOTRACK)
            self._monitor.add_callback(self._monitor_logger_cb)

    @property
    def rpcserver(self):
        if hasattr(self, '_rpcserver'):
            return self._rpcserver
        else:
            return None

    @rpcserver.setter
    def rpcserver(self, s):
        if s is None:
            return
        elif not isinstance(s, RPCServer):
            raise Error("Error setting rpcserver, expected object of type RPCServer, got {}".format(s))
        else:
            self._rpcserver = s
            self._rpcserver.register_function(lambda prot,self=self: setattr(self, 'protocol',  prot), "set_protocol")
            self._rpcserver.register_function(self.start_track)
            self._rpcserver.register_function(self.stop_track)
            self._rpcserver.register_function(self.do_action)
            self._rpcserver.register_function(self.set_azel)
            self._rpcserver.register_function(self.stow)
            self._rpcserver.register_function(self.transmit)
            self._rpcserver.register_function(self.init_rx)
            self._rpcserver.register_function(self.init_rxtx)
            self._rpcserver.register_function(self.terminate)
            self._rpcserver.register_function(self.get_azel)
            self._rpcserver.register_introspection_functions()
            log.info("Registered RPC interface to ground station on {}".format(s.uri))


    @property
    def scheduler(self):
        return self._scheduler if hasattr(self, '_scheduler') else None

    @scheduler.setter
    def scheduler(self, sch):
        if self.state.state != self.state.IDLE:
            raise Exception("groundstation.scheduler: Cannot attach a new scheduler to groundstation since the state is currently not IDLE. It is {}".format(self.state.state))

        self._scheduler = sch




    ######################
    #
    # Methods
    #
    ######################

    def start_track(self, nid_or_pdata, **kwargs):
        """
            Non-blocking tracking. The antenna will be pointed as
            required but returning control while doing so.

            It is implemented by spinning the track function off into a separate thread
        """

        self._pthr_track = threading.Thread(target=self.track, args=(nid_or_pdata,), kwargs=kwargs)
        self._pthr_track.start()

    def stop_track(self, block=False):
        """
            Stop tracking satellite.
        """
        if self._stop_track:
            log.debug("stop_track has already been called. Not doing anything.")
            return #<-- dont do it twice

        self._stop_track = True
        
        if block:
            self._pthr_track.join()
            

    def terminate(self):
        """
        Wrapper for protocol.terminate()
        """
        if not self.protocol:
            raise Error ("Error: groundstation.terminate. No protocol have been connected to Ground Station.")
        else:
            self.protocol.terminate()

    def init_rx(self):
        """
        Wrapper for protocol.init_rx()
        """

        if not self.protocol:
            raise Error("Error: groundstation.init_rx. No protocol have been connected to Ground Station.")
        else:
            self.protocol.init_rx()

    def init_rxtx(self):
        """
        Wrapper for protocol.init_rxtx()
        """

        if not self.protocol:
            raise Error ("Error: groundstation.init_rxtx. No protocol have been connected to Ground Station.")
        else:
            self.protocol.init_rxtx()

    def get_azel(self):
        result = []
        if len(self.rotators) == 0:
            raise Error ("Error: groundstation.get_azel. No rotators have been connected to Ground Station.")
        for r in self.rotators:
            result.extend([r.get_azel()])

        return result
            
    def set_azel(self, az, el, block=False):
        if self.rotators is None:
            raise Error("GroundStation.set_azel called but no rotators available")
        
        TIMEOUT = 60
        for r in self.rotators:
            r.set_azel(az,el, block=False)
            TIMEOUT = r.SLEW_TIMEOUT if r.SLEW_TIMEOUT > TIMEOUT else TIMEOUT
            
        if block:
            if wait_loop(lambda: all([r.in_pos(az, el) for r in self.rotators]), timeout=TIMEOUT) is None:
                    log.error("Timeout ({} sec) waiting for rotators to position themselves".format(TIMEOUT))


    def stow(self, block=False):
        if self.rotators is None:
            raise Error("GroundStation.stow called but no rotators available")
        
        TIMEOUT = 60
        
        for r in self.rotators:
            r.stow(block=False)
            
        if block:
            t0 = time.time()
            
            while not all([r.in_pos(r.STOWED_AZ, r.STOWED_EL) for r in self.rotators]):
                
                if time.time() - t0 > TIMEOUT:
                    log.error("Timeout waiting for rotators to position themselves")
                    break
            


    ############################
    #
    # Interface methods (shall be overloaded)
    #
    ############################
    
    def set_rangerate(self, range_rate):
        raise Error("GroundStation.set_rangerate interface not implemented")

    def transmit(self):
        raise Error("GroundStation.transmit interface not implemented")

    def track(self):
        raise Error("GroundStation.track interface not implemented")


    def do_action(self, desc, *args, **kwargs):
        raise Error("GroundStation.do_action interface")
        
        
    ##############################
    #
    # Interface methos (may be overloaded)
    #
    ##############################
    def power_up(self):
        log.debug("Nothing is being powered on by ground station since the power_up interface has not been defined")
    
    def power_down(self):
        log.debug("Nothing is being powered down by ground station since the power_down interface has not been defined")



class UILogHandler(logging.Handler):

    def __init__(self, gsstate):
        self._stateinstance = gsstate

        super(UILogHandler, self).__init__()


    def emit(self, record):

        self._stateinstance.libgs_log = self.format(record)


    def test(self, m):
        self._stateinstance.libgs_log = m
        
        
# TODO: Review GSState and which part of it to keep in libgs and which to
#       move to adfags. 
#       It also includes a bunch of stuff that isnt needed anymore which would
#       be good to get rid of
        
    

class GSState(object):
    """
    Class to hold ground station state variables.

    The ground station uses this class to store important state variables,
    (as its properties). The class does however have the ability to connect
    callbacks to those properites in order to, for example, update a UI.

    Makes use of python properties to ensure the callbacks.

    The state properties are:

    ======= ======================================= ========================
    prop    Description                             type
    ======= ======================================= ========================
    curpos  Current antenna position(s)             tuple or tuple-of-tuples
    cmdpos  Commanded antenna position(s)           tuple or tuple-of-tuples
    satpos  Current tracked satellite position(s)   tuple
    nid     Current tracked satellite Norad ID      int
    pdat    Current pass data                       DataFrame
    state   Current tracking state                  str
    ======= ======================================= ========================

    .. todo::
        Complete this table

    """
    #TODO Complete table

    #
    # Tracking states
    #
    IDLE = 'idle'
    SLEWING = 'slewing'
    WAITING = 'waiting'
    TRACKING = 'tracking'

    #: The logging handler that is used for adding log messages to ui
    uiloghandler = None


    def __init__(self, callbacks={}, callback_dt = {}, pollmap={}):

        # Initialise all the properties
        self._curpos = []
        self._cmdpos = []
        self._satpos = None
        self._nid    = None
        self._pdat   = None
        self._state  = None
        self._schedule = None
        self._track_msg = None
        self._libgs_log = []
        self._last_response = None
        self._POLL_INTERVAL = 10.0 #<--- seconds between each poll of polled state variables

        #
        # Initialise logging to the state variable
        #
        ch = UILogHandler(self)
        ch.setLevel(logging.INFO)
        cf = UTCLogFormatterHTML(Defaults.LOG_FORMAT)
        ch.setFormatter(cf)
        log.addHandler(ch)
        logging.getLogger('libgs_ops-log').addHandler(ch) #<-- also show libgs_ops output

        # Make available as a property so that it can be
        self.uiloghandler = ch

        #
        # The map of functions to poll to set state attributes
        # (in most cases teh ground station will set them directly and
        # therefore the poller is not necessary)
        # The state can be updated through polling for items that do not set
        # it directly. The polling functions are specified as a dict where
        # the key is the state attribute to update, and the value is the function
        # to call to update it.

        self.pollmap = pollmap

        # TODO: Replace this with a RegularCallback (or at least by a wait_loop)
        def _poller():
            while (True):
                for k,v in self.pollmap.items():
                    setattr(self, k, v())

                try:
                    wait_loop(timeout = self._POLL_INTERVAL)
                except AbortAllException:
                    log.debug("gsstate._poller aborted with global abort_all event")
                    return


        self._pthr_poll = threading.Thread(target = _poller)
        self._pthr_poll.daemon = True
        self._pthr_poll.start()


        # The name of the class that is permitted to change properties
        # Attempting to change from anywhere else will fail.
        # To permit mutation from anywhere, delte this property
        # To disable from anywhere, set it to None
        self._mutable = 'GroundStation'

        self.callbacks = dict()
        self._last_called = dict()
        self.callback_dt = dict()


        for k,v in callbacks.items():
            if str(k)[0:7] != 'update_':
                raise Exception('Callback keys must have the form update_funcname')

        for k,v in callback_dt.items():
            if str(k)[0:7] != 'update_':
                raise Exception('Callback keys must have the form update_funcname')

            self.callbacks[k] = v



    def _setter(dtype, muting_class=None):
        """
        This method generates a decorator that checks the input type
        when setting properties and calls the specified callback function,
        also specifying a maximum call frequency

        (specified with the callbacks property)
        """


        def decorator(func):
            def func_wrapper(self, value):
                # Check type (also allow None)
                if (dtype is not None) and not (value is None or (isinstance(value, dtype))):
                    raise Exception("Argument to %s must be %s, not %s"%(func.func_name, dtype, type(value)))

                # Only allow mutation if called from the allowed class
                # (the groundstation)

                if muting_class is None and hasattr(self, '_mutable'):
                    mutable = self._mutable
                else:
                    mutable = muting_class

                if mutable is not None:#hasattr(self, '_mutable'):
                    try:
                        calling_class = sys._getframe().f_back.f_locals['self'].__class__.__name__
                        if (calling_class != 'GSState') and (calling_class != mutable):#self._mutable:
                            raise Exception("Changing properties is not permitted")
                    except KeyError:
                        raise Exception("Changing properties is not permitted")
                    except:
                        raise



                func(self, value)
                key = 'update_'+func.func_name
                if key in self.callbacks.keys():

                    if (not (key in self.callback_dt.keys())) or\
                        (not (key in self._last_called.keys())) or\
                            (time.time() - self._last_called[key] > self.callback_dt[key]):

                        self.callbacks[key](value)
                        self._last_called[key] = time.time()

            return func_wrapper

        return decorator


    def tracking_info():
        """
        Return info about tracking state
        """
        pass

    def hardware_info():
        pass

    def antenna_info():
        pass

    def service_info():
        pass


    def __str__(self):
        """
        Format a basic string to describe the state

        .. todo::
            Complete with hardware power states and other stuff...

        """
        s =  "Ground Station state\n"
        s += "=======================\n"
        s += "\n"
        s += "Antenna\n"
        s += "-----------------------\n"
        s += "Current state: {}\n".format(self.state)
        s += "Commanded position(s):          {}\n".format(self.cmdpos)
        s += "Current position(s):            {}\n".format(self.curpos)
        s += "\n"
        if hasattr(self, 'pdu'):
            s += "PDU\n"
            s += "-----------------------\n"
            s += self.pdu


        return(s)

    def __repr__(self):
        return self.__str__()

    @property
    def curpos(self):
        return self._curpos

    @property
    def cmdpos(self):
        return self._cmdpos

    @property
    def satpos(self):
        return self._satpos

    @property
    def state(self):
        return self._state

    @property
    def pdat(self):
        return self._pdat

    @property
    def nid(self):
        return self._nid

    # TODO: Store entire schedule (not just text) in state and do not
    #       permit two scheduler to be started with same gs
    @property
    def schedule(self):
        return self._schedule

    @property
    def track_msg(self):
        return self._track_msg

    @property
    def libgs_log(self):
        return '\n'.join(self._libgs_log)

    @property
    def pdu(self):
        return self._pdu

    @property
    def last_response(self):
        return self._last_response

    @last_response.setter
    @_setter(basestring)
    def last_response(self, msg):
        self._last_response = msg

    @pdu.setter
    @_setter(basestring)
    def pdu(self, value):
        self._pdu = value

    @libgs_log.setter
    @_setter(basestring, 'UILogHandler')
    def libgs_log(self, msg):
        self._libgs_log += [msg]
        if len(self._libgs_log) > Defaults.UI_LOG_LEN:
            self._libgs_log = self._libgs_log[-Defaults.UI_LOG_LEN:]


    @track_msg.setter
    @_setter(basestring)
    def track_msg(self, msg):
        self._track_msg = msg


    @schedule.setter
    @_setter(basestring)
    def schedule(self, value):
        self._schedule = value

    @satpos.setter
    @_setter(tuple)
    def satpos(self, value):
        self._satpos = value

    @cmdpos.setter
    @_setter(list)
    def cmdpos(self, value):
        self._cmdpos = value

    @curpos.setter
    @_setter(list)
    def curpos(self, value):
        self._curpos = value

    @state.setter
    @_setter(basestring)
    def state(self, state):
        if state == 'idle':
            self._pdat = None
            self._nid = None

        self._state = state

    @pdat.setter
    @_setter(DataFrame)
    def pdat(self, pdat):
        self._pdat = pdat

    @nid.setter
    @_setter(int)
    def nid(self, nid):
        self._nid = nid



        
class GroundStation(GroundStationBase):
    """
        Main class for the ground station
    """
    
    
    RECORD_SPECTRA         = Defaults.RECORD_SPECTRA
    RECORD_SPECTRA_MAX_LEN = Defaults.RECORD_SPECTRA_MAX_LEN
    RECORD_SPECTRA_DT      = Defaults.RECORD_SPECTRA_DT
    MAX_TRACK_DT           = Defaults.MAX_TRACK_DT

    #############################################
    #
    # Interface methods
    #
    #############################################



    def set_rangerate(self, range_rate):

        def _set_rangerate_and_wait(radio, range_rate):

            t0 = time.time()

            while (int(radio.range_rate) != int(range_rate)):
                radio.range_rate = range_rate
                if time.time() > t0 + 1.0:
                    return False

                safe_sleep(0.1)

            return True

        succeeded = 0
        for r in self.radios:

            # if not r.controllable("range_rate"):
            #     log.debugv("range_rate on radio %s is not currently controllable"%(r.name))
            #     continue

            try:
                # dont change rate if already correct
                if int(r.range_rate) == int(range_rate):
                    succeeded += 1
                    continue
            except Exception as e:
               Error("Error reading range_rate: {} : {}".format(type(e).__name__, e.args))            


            # Set range rate otherwise
            try:
                ret = _set_rangerate_and_wait(r, range_rate)

                if ret == False:
                    raise Error("Timeout while trying to set range_rate on radio %s"%(r.name))

                succeeded += 1
            except Exception, e:
                log.debugv("Failed to set range_rate for radio %s. Error: %s"%(r.name, e))

        if succeeded == 0:
            log.debugv("Could not set range_rate on any radio")

        #log.info("Range rate set to %d m/s"%(range_rate))


    # TODO: deal with this wait. MAybe reomve? It conflicts wit conf.timeouts
    def transmit(self, msg, wait=Defaults.TX_REPLY_TIMEOUT):
        """
            Transmit something to a satellite
        """
        if not isinstance(msg, bytearray):
            raise Error("Msg to transmit must be of type bytearray")

        if self.protocol is None:
            raise Error("transmit requested, but no protocol has been assigned.")


        self.state.last_response = None

        try:
            self.protocol.send_bytes(msg, wait=wait)
        except Exception, e:
            self._log_comms("GS", "GS", "FAILURE: %s"%(e))
            raise
            
        logmsg =["%02X"%(x) for x in msg]#map(ord, msg)]
        self._log_comms("GS", "Sat", '-'.join(logmsg))
            

    def do_action(self, desc, *args, **kwargs):
        """
            Ask the protocol to do something (to presumably do something with
            the satellites) without any restrictions. The args and kwargs
            are anything implemented in the protocol.

            Note that when using this mode of transmission, logging is a bit
            trickier. This function will do the best it can but since it doesnt
            know much, that might not be very nice. Try to use the other
            function unless you have to do something fancy.

            The desc parameter is required in order to put SOMETHING in the log.
        """

        self._log_comms("GS", "Protocol", "`%s`<%s, %s>"%(desc, args, kwargs))

        if self.protocol is None:
            raise Error("do_action requested, but protocol not connected")
            
        self.protocol.do_action(*args, **kwargs)


    def track(self, nid_or_pdata, **kwargs):
        """
            Track satellite by Norad ID

            Track by moving in steps across the trajectory of the satellite
            
            Args:
                nid (int) or schedule (pdata) : Either the Norad ID or the schedule to track.
                             If Norad ID is provided and a propagator connected, then the
                             method will compute the pdata itself.
                
                nid_or_pdata (int/pdata) : Either a schedule file (pdata) or a norad ID to track.
                max_offp                 :  max offpointing to allow

            If x0 is the actual satellite position at time t0:
                1. point to x0 + max_offp,
                2. wait until x0 - max_offp
                3. move to x0 + max_offp again ... etc

            Since the antenna requires a finite amount of time to move, if
            max_offp is too small it will not have a chance to dwell at all.
            min_dwell defaults to 1 second. An exception will be raised if
            the antenna needs to move again before the minimum dwell time.

        """
        
        
        #
        # Get pass data and Norad ID depending on what is provided in arguments
        #
        if isinstance(nid_or_pdata, int):
            # compute pdata
            if self.propagator is None:
                raise Error("Cannot compute pass data; no propagator has been connected")
            else:
                pdat, psum = self.propagator.compute_pass(nid_or_pdata)
                log.info("Computed upcoming pass for NID %d to track: \n "%(nid_or_pdata) + str(psum[['tstamp_str', 'az', 'el']]).replace('\n', '\n    '))
        else:
            pdat = nid_or_pdata
            
            
        if hasattr(pdat, 'nid'):
            nid = pdat.nid
        else:
            nid = None
            
        nid_lbl = nid
        if nid <= 0: 
            nid = None

            
        try:
            rotators = kwargs['rotators']
        except:
            rotators = self.rotators
            
        # Check that the rotators are  connected
        if len(rotators) == 0:
            log.error('No rotator connected to ground station - "tracking" with a dummy')
            rotators = [DummyRotator()]

        try:
            compute_ant_points = kwargs['compute_ant_points']
        except:
            compute_ant_points = True


        # TODO: Remove. The current rotator class will never move antennas beyond its limits anyway, so it is not necessary to do so here
        # try:
        #     min_el = kwargs['min_el']
        # except:
        #     min_el = rotators[0].MIN_EL
        #     for r in rotators[1:]:
        #         if r.MIN_EL > min_el:
        #             min_el = r.MIN_EL

        #
        # Check that tracking is not already in progress
        #
        if self.state.state != self.state.IDLE:
            raise Error("Ground station is already tracking, abort current track first")

        #
        # Reset stop flag
        #
        self._stop_track= False


        pass_stats = {}


        #
        # Pass ID, for tracking communications
        #
        self.state.pass_id = ("%05d"%(nid_lbl),
                              pd.to_datetime(str(pdat.tstamp_str.iloc[-1])).strftime('%Y%m%d%H%M%S'))

        #
        # Increase monitoring rate for duration of pass
        #
        self._set_monitor_pass(True)


        # TODO: Remove. The current rotator never allows moving anenna beyond its limtis anyway so not necessary
        #       to do that check here.
        #
        # Crop pass data to only include data above the visibility horizon
        #
        # pdat = pdat[pdat.el >= min_el]
        #
        # if pdat.empty:
        #     raise Error("Pass does not ever become visible. Cannot track")




        # Save tracking data to state
        self.state.pdat = pdat



        s0 = ''
        if nid is not None:
            #
            # If we know which satellite we are tracking then
            # update state with its current position
            #
            self.state.nid = nid

            #
            # Get current satellite position
            #
            if self.propagator is not None:
                self.state.satpos = self.propagator.get_angles(nid)
    
                s0 = 'Tracking %05d'%(nid)
                log.info(s0)




        #
        # A small helper function to get current UTC time in pyephem format
        #
        now = lambda : ephem.Date(datetime.utcnow())


        def set_rangerate(rate):
            try:
                self.set_rangerate(rate)

            except Exception as e:
                log.debug("Error in set_rangerate: {0} : {1!r}".format(type(e).__name__, e.args))


        #
        # Calculate antenna pointings to use during track
        #
        if compute_ant_points:

            # require a 1 second time resolution and allow 10% margin, or otherwise interpolate
            if max(np.diff(pdat.index) * (24 * 60 * 60)) > self.MAX_TRACK_DT*1.1:
                log.debug("Track does not have fine enough resolution, interpolating to dt={}".format(self.MAX_TRACK_DT))
                t_i = np.arange(pdat.index[0], pdat.index[-1], 1.0 / (24 * 60 * 60))
                az_i = np.interp(t_i, pdat.index, pdat.az)
                el_i = np.interp(t_i, pdat.index, pdat.el)
                rr_i = np.interp(t_i, pdat.index, pdat.range_rate)
                pdat = DataFrame(index=t_i, data=dict(az=az_i, el=el_i, range_rate=rr_i))


            antangs = [r.azel_to_antenna_angles(pdat) for r in rotators]
        else:
            # This option tracks schedule directly. Should really never be
            # done unless you specify a very sparse schedule manually
            antangs = [pdat for r in rotators]


        # find next pointing (may not be the first if track has started)
        try:
            first_point = [list(aa.index > now()).index(True) for aa in antangs]
        except ValueError, e:
            raise Error("Pass is entirely in the past. Cannot track (%s)"%(e))



        pass_stats['start_t'] = now()

        #
        # Slew to start of track
        #
        self.state.state = self.state.SLEWING

        s = ('Slewing to start of track')
        log.info(s)

        # TODO: incorporate messages in state? not sure
        self.state.track_msg = s0 + '\n' + s

        for k,aa in enumerate(antangs):
            rotators[k].set_azel(aa.iloc[first_point[k]].az, aa.iloc[first_point[k]].el, block=False)


        #
        # 2) Wait for satellite to come into view
        #
        self.state.state = self.state.WAITING
        s="Waiting for satellite to become visible"
        log.info(s)
        self.state.track_msg = s0 + '\n' + s

        while (now() < pdat.index[0]) and not self._stop_track:
            if nid is not None and self.propagator is not None:
                self.state.satpos = self.propagator.get_angles(nid)
                s = ('Satellite is currently not visible (az=%5.2f, el=%5.2f)'%(self.state.satpos[0], self.state.satpos[1]))

                self.state.track_msg = s0 + '\n' + s


            time.sleep(1.0)


        #
        # Start recording radio
        #
        if self.RECORD_SPECTRA:
            radio_recordings = [r.record_spectrum(dt=self.RECORD_SPECTRA_DT, N=self.RECORD_SPECTRA_MAX_LEN, fdec=5, add_zeroes=True) for r in self.radios]
        else:
            radio_recordings = []


        #
        # 3) Track satellite
        #
        self.state.state = self.state.TRACKING
        cur_point = first_point
        num_points = [len(aa) for aa in antangs]


        pass_stats['start_track_t'] = now()
        pass_stats['max_el'] = -1

        log.info("Now tracking")
        while (now() <= pdat.index[-1]) and not self._stop_track:
            

            for k,aa in enumerate(antangs):
                if cur_point[k] < (num_points[k] -1) and (now() > aa.index[cur_point[k] + 1]):
                    cur_point[k] += 1
                    new_el = aa.iloc[cur_point[k]].el
                    rotators[k].set_azel(aa.iloc[cur_point[k]].az, new_el, block=False)

                    new_el_adj = 180 - new_el if new_el > 90 else new_el
    
                    if pass_stats['max_el'] < new_el_adj:
                        pass_stats['max_el'] = new_el_adj

            # It's not ideal to do this continuously, but since the radio might
            # reboot at any time it is important to keep the range rate updated
            # Note that: set_rangerate does not actually set the variable if it hasnt changed, however
            # It *does* issue an xmlrpc call to check if it has been set.


            range_rate = pdat.range_rate[pdat.index > now()]
            if len(range_rate) == 0:
                range_rate = pdat.range_rate.iloc[-1]
            else:
                range_rate = range_rate.iloc[0]

            set_rangerate(range_rate)


            s = "Tracking"
            if nid is not None and self.propagator is not None:
                s = ('Tracking satellite at (az=%5.2f, el=%5.2f)'%(self.state.satpos[0],self.state.satpos[1]))
                self.state.satpos = self.propagator.get_angles(nid)
            else:
                cur_az = pdat.az[pdat.index > now()]
                cur_el = pdat.el[pdat.index > now()]
                if len(cur_az) > 0 and len(cur_el) > 0:
                    self.state.satpos = (cur_az.iloc[0], cur_el.iloc[0])
                    s = ('Tracking (az=%5.2f, el=%5.2f)' % (self.state.satpos[0], self.state.satpos[1]))


            self.state.track_msg = s0 + '\n' + s

            time.sleep(0.1)

        # Mark the time of the end of track
        pass_stats['end_track_t'] = now()

        # Move the yellow dot (satellite position) out of the way so we dont see it on plot
        self.state.satpos = (0, -90)
        log.debug("Hiding satellite position. Current marked position: {}".format(self.state.satpos))


        #
        # Stop recording
        #
        for radrec in radio_recordings:
            radrec.abort()
            

        #
        # 4) Stow antenna
        #
        self.state.state = self.state.SLEWING
        s = "Stowing antenna"
        log.info(s)

        self.state.track_msg = s

        self.stow(block=True) #TODO: Should it be true or false? I.e. do we want it to wait until antennas are stowed or not

        pass_stats['stowed_t'] = now()


        try:
            s = "\n Track stats pass %s / %s:"%self.state.pass_id
            self._passlog.put(module=__name__, pass_id = self.state.pass_id[1], key='norad_id', value=self.state.pass_id[0])
            for k,v in pass_stats.items():
                v = conv_time(v, to='iso', ignore_ambig_types=True)
                self._passlog.put(module=__name__, pass_id = self.state.pass_id[1], key=k, value=v)
                s += "\n    %15s = %s"%(k,v)
    
    
            log.info(s)
            

            if self.RECORD_SPECTRA:
                image_data = _mpl_make_waterfall_jpg([r.name for r in self.radios], radio_recordings)
                self._passlog.put(module=__name__, pass_id = self.state.pass_id[1], key="waterfall_jpeg", value=image_data)
        
        except Exception as e:
            log.exception("Exception saving pass stats to db")


        #
        # 5) Return to idle
        #
        s = "Antenna/Rotator state is idle"
        log.info(s)
        self.state.track_msg = s
        self.state.state = self.state.IDLE
        self.state.pass_id = None
        
        


        #
        # Reduce monitoring save interval again
        #
        self._set_monitor_pass(False)
        
 

    #########################################################
    #
    # Non-interface private methods
    #
    ########################################################        



    def __init__(
                self,
                name,
                propagator = None,
                protocols  = [],
                radios     = [],
                rotators   = [],
                commslog   = CommsLog(),
                passlog    = PassDb(),
                monlog     = None,
                rpcserver  = None
            ):

        # initialise state
        self.state         = GSState()
        self.state.name    = name
        self.state.state   = self.state.IDLE
        self.state.pass_id = None

        # initialise connected hardware
        self.propagator    = propagator
        self.rotators      = rotators
        self.radios         = radios

        # initialise protocols
        self.protocols     = protocols


        # connect handlers
        for p in self.protocols:

            # Set the handler for received messages
            p.set_handler(self.receive)

        # assign first protocol (note this also connects the receive handler)
        self.protocol      = protocols[0] if len(protocols) > 0 else None

        # initialise RPC interface
        self.rpcserver     = rpcserver


        #
        # Communications database
        #
        self._commslog = commslog
        
        #
        # Pass database
        #
        self._passlog = passlog

        #
        # Monitoring database
        #
        self._monlog = monlog
        self._set_monitor_pass(False)
        self._monitor_logger_last_t = {}
        

        # Power up everything
        self.power_up()


        #
        # Initialise flags
        #
        self._stop_track = False


        #
        # Start regular polling of antenna positions.
        #
        def update_pos():
            self.state.curpos = [r.get_azel() for r in self.rotators]
            self.state.cmdpos = [(r.cmd_az, r.cmd_el) for r in self.rotators]


        if rotators is not None:
            self._pos_poller = RegularCallback(update_pos, Defaults.GS_ROTATOR_POLLING_INTERVAL)
            self._pos_poller.start()


        

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        # TODO: Clean up - keep state stuff in state class
        s =  "Ground Station {}\n".format(self.state.name)
        s +=  "  Propagator     : " + ("not connected" if self.propagator is None else self.propagator.__str__()) + '\n'
        s +=  "  Protocol       : " + ("not connected" if self.protocol is None else self.protocol.__str__()) + '\n'
        s +=  "  Protocols avail: {}\n".format([p.name for p in self.protocols])
        if len(self.radios) == 0:
            s += "  Radios         : not connected\n"
        else:
            for k,r in enumerate(self.radios):
                s += "  Radio[{:2}]      : {}\n".format(k, r.__str__()) 

        if len(self.rotators) == 0:
            s += "  Rotators       : not connected\n"
        else:
            for k,r in enumerate(self.rotators):
                s += "  Rotator[{:2}]    : {}\n".format(k, r.__str__()) 

        return s



    def _monitor_logger_cb(self, name, tstamp, exc, res):
        """
        Monitor callback that saves monitor data to database
        """

        # Ensure a minimum interval of  self._monitor_logger_dt happens before logging
        if name in self._monitor_logger_last_t.keys() and time.time() < self._monitor_logger_dt + self._monitor_logger_last_t[name]:
            return

        self._monitor_logger_last_t[name] = time.time()

        if self._monlog is not None:
            if exc is not None:
                ret = 'ERROR {}'.format(exc)
                alert = res.alertstr
            else:
                ret = res.val
                alert = res.alertstr

            if not hasattr(self.state, 'pass_id') or self.state.pass_id is None:
                pass_id = 'no pass'
            else:
                pass_id = self.state.pass_id[1]

            # TODO: Decide if we want alert string or alert code in database

            self._monlog.put(pass_id, name, ret, alert=alert)




    def _set_monitor_pass(self, passing):
        """
        Just a convenience function to update the interval at which _save_monitor_data is invoked for monitor data

        """
        # if not hasattr(self, '_monitor_logger'):
        #     log.debug("Cannot set/unset monitor pass as no monitor connected")
        #     return

        # if self._monitor_logger is not None:
        #     if passing:
        #         self._monitor_logger._dt = self.MONITOR_SAVE_DT_TRACK
        #         log.info("Decreased interval at which monitoring data is saved to {}".format(self._monitor_logger._dt))
        #     else:
        #         self._monitor_logger._dt = self.MONITOR_SAVE_DT_NOTRACK
        #         log.info("Increased interval at which monitoring data is saved to {}".format(self._monitor_logger._dt))


        if passing:
            self._monitor_logger_dt = self.MONITOR_SAVE_DT_TRACK
        else:
            self._monitor_logger_dt = self.MONITOR_SAVE_DT_NOTRACK


    def _log_comms(self, orig, dest , msg):
        """
            Add communication to log

            .. todo::
               Streamline how this is done. Should be saved to a sql database

        """
        if not hasattr(self.state, 'pass_id') or self.state.pass_id is None:
            pass_id = (0,'unknown')
        else:
            pass_id = self.state.pass_id

        # save message
        self._commslog.put(pass_id[0], pass_id[1], orig, dest, msg)

   
   
   ################################################
   #
   # Non-interface public methods
   #
   ###############################################



    #
    # Log entry for failed communication
    #
    FAILED_COMMUNICATION = 'Communication failed'


    def set_schedule_msg(self, msg):
        self.state.schedule = msg

     
#    def register_monitor(self, *args, **kwargs):
#        """
#        Just a wrapper for Monitor.register_monitor
#        """
#        self._monitor.register_monitor(*args, **kwargs)
   

    def receive(self, msg):
        msg = bytearray(msg)



        if msg[:7] != 'FAILURE':
            logmsg =["%02X"%(x) for x in msg]# map(ord, msg)]
            logmsg = '-'.join(logmsg)
            self._log_comms("Sat", "GS", logmsg)
        else:
            #
            # TODO: Record more details on comms failures by allowing
            #  FAILURE: <some message> to be sent from the protocol
            #
            logmsg = self.FAILED_COMMUNICATION
            self._log_comms( "Protocol", "GS", logmsg)

        self.state.last_response = logmsg








if __name__=="__main__":
    pass

