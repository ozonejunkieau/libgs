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


Created on Thu Nov 30 14:40:58 2017

@author: kjetil
"""

import logging
import threading

log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())




####################################################################
# TODO: Import this from utils instead
#
class Error(Exception):
    """Generic Error for this module"""

    def __init__(self, msg, original_Error=None):
        if original_Error is not None:
            super(Error, self).__init__(msg + (": %s" % original_Error))
            self.original_Error = original_Error
        else:
            super(Error, self).__init__(msg)


def bytes2hex(data):
    """
    Helper function that takes a bytearray and converts it into a string of hexadecimal bytes AB-CD-00-01-... as
    is appropriate for the callback function
    """
    data =bytearray(data)
    return('-'.join(["%02X"%(x) for x in data]))

#
# End TODO
#####################################################################




class ProtocolBase(object):
    """
    Base class for protocols. Defines the primary interface that is used
    by the scheduler. Any protocol used by the library must implement
    the following methods:

    - send_bytes(self, bytes) : Send a sequence of bytes to the satellite
    - do_action(self, *args, **kwargs) : Ask the protocol to do something. The do_action should take different
          actions, depending on the arguments, but there are no further requirements on what those arguments
          should be.
    - set_handler(self, func) : Set callback for when data is received back from satellite, this is invoked
          by the ground-station class upon creation. The groundstation will expect the callback function to be called
          every time data is received from the satellite. It is the responsibility of the Protocol to ensure that
          happens.


    The following class attribute shall also be overloaded:

    - name: The name of the protocol

    Additionally a protocol *may* implement the following methods:

    - init_rx(self):  This method will be called by the scheduler before starting a listening pass. It should contain
                      any initialisation routines required.
    - init_rxtx(self):This method will be called by the scheduler before starting a transmitting pass. It should contain
                      any initialisation routines required (power on amplifiers etc...)
    - terminate(self):This method will be called by the scheduler as soon as a pass has finished. It should contain
                      any clean-up routines required (power off amplifiers etc...), and most importantly ensure that
                      any threads or loops initiated by the Protocolclass are immediately terminated in a clean and
                      controlled manner.


    When the scheduler starts a pass it will also set an attribute on the protocol class called sch_metadata. This
    attribute contains all the metadata stored in the Schedule (see libgs.scheduling), and is available to the Protocol
    class to refer to as needed.

    .. warning Warning 1::

        This class should avoid blocking functions at all cost, and need to respond to the global abort_all event to allow
        libgs to shut down cleanly. A method is provided in libgs.utils called wait_loop that can be used as a
        replacement for time.sleep and/or waiting for events to occur. wait_loop will automatically handle the global
        abort_all event.

    .. warning Warning 2::

        It is imperative that the terminate() method immediately stops any and all running processes or threads
        spawned by the Protocol class.


    """
    



    ###############################
    #
    # Properties. 
    #
    ###############################


    #: The name of the protocol. may be queriedby loggers and similar, so should be overloaded with a descriptive name in subclasses.
    name = 'undefined protocol'
    
    #: The scheduler will update this property with any metadata the operator has attached to the schedule, thereby allowing him/her
    #: to pass information to the protocol class
    sch_metadata = {}


    ###############################
    #
    # Interface. Shall be overloaded
    #
    ###############################


    def send_bytes(self, data, wait=False):
        """
            Send a sequence of bytes to the satellite.

            The bytes are exactly as entered by the operator when creating the schedule. It is the expectation
            that any handshaking or protocol-headers are added in this class and not left for the operator to do
            manually.

            However, there are no requirements as the bytes are passed through directly from the schedule to this method.

            The method shall raise an exception upon failure.

        Args:
            data: The bytes to transmit
            wait: Whether or not to wait for the upload to complete.

        Returns:
            None

        """

        raise Error("Protocol.send_bytes interface not defined")

    def do_action(self, *args, **kwargs):
        """
        Request an action to be performed

        Actions can be arbitrary sequences of commands and/or other functionality that are too complex to be captured
        with a simple byte sequence transmission.

        The arguments are passed through from whatever the operator entered when creating the schedule, and there
        are no requirements, however it is good practivce to make the first argument the name of the action, and any
        subsequent argument and/or kwarg to be arguments that action requires.

        Upon any error, this method should raise an Exception.

        Args:
            *args: Any set of arguments (the first should be the action name)
            **kwargs: Any set of kwarguments

        Returns:
            None

        """
        raise Error("Protocol.do_action interface not defined")

    def set_handler(self, func):
        """
        Set a callback message handler for received data.

        This method is called by the groundstation class as it is set up, and it is expected that the protocol calls
        the callback function whenever it receives any data from the spacecraft. The groundstation will then take appropriate
        action to log the data in the mysql database.

        The callback function takes a single argument msg, which has to comply with the following requirements:
            - It shall be a string
            - It shall either be a series of hexadecimal values corresponding to the received bytes (e.g. 'AB-CD-00-01')
            - Or it shall be a string starting with the word 'FAILURE'. This shall be the case if any error occurs that means
              a byte sequence cannot be returned. It will be stored in the database and logged for posteriority.

        .. note::
            The bytes2hex function can be used to convert a bytearray into an appropriately formatted HEX-string.

        Args:
            func: The callback function

        Returns:
            None

        """
        raise Error("Protocol.set_handler interface not defined")
        

    ###############################
    #
    # Interface functions. May be overloaded
    #
    ###############################
        
    # In the recent update the protocols now have access to the
    # scheduler metadata (see above) which also includes listen flag
    # There is therefore not really any need for separating the init_rx and
    # init_rxtx methods, as the protocol could differentiate by checking that flag.
    # In the future the init_rx and init_rxtx should therefore be removed and replaced with a single init method.
    def init_rx(self):
        """
        Interface method that is called by the scheduler before starting a listening pass. It should contain
        any initialisation routines required.
        """
        log.debug("No RX initialisation implemented. Is this your intention?")

    def init_rxtx(self):
        """
        Interface method that is called by the scheduler before starting a transmitting pass. It should contain
        any initialisation routines required. (power on amplifiers etc...)
        """
        log.debug("No TX initialisation implemented. Is this your intention?")

    def terminate(self):
        """
        Interface method that is called by the scheduler as soon as a pass has finished. It should contain
        any clean-up routines required (power off amplifiers etc...), and most importantly ensure that
        any threads or loops initiated by the Protocolclass are immediately terminated in a clean and
        controlled manner.
        """
        log.debug("No termination implememnted. Is this your intention?" )






class ProtocolTest(ProtocolBase):
    """
    This protocol is implemented as a test only. It does not do anything,
    but can be included for testing purposes
    """
    
    name = "Test Protocol"

    def send_bytes(self, data):
        log.info("Protocol.send_bytes called with bytes %s"%bytes2hex(data))

    def do_action(self, *args, **kwargs):
        log.info("Protocol.do_action called with args = %s, and kwargs=%s"%(args, kwargs))

    def set_handler(self, func):
        log.info("Protocol.set_hanlder called with function %s"%(func.__name__))

