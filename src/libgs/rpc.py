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


Created on Tue Sep 19 16:29:54 2017

@author: kjetil
"""

from threading import Thread
from scheduler import Scheduler, Schedule
from utils import Defaults
import threading

from SimpleXMLRPCServer import SimpleXMLRPCServer

import logging
ags_log = logging.getLogger('libgs-log')
ags_log.addHandler(logging.NullHandler())


#
# TODO: Move into Scheduler class (in the same way the ground station RPC interface is in the groundstaiton class now)
#
class RPCSchedulerServer(object):
    """
    This class sets up an RPC server that can be contacted remotely in order
    to load and execute a schedule (it will create a local scheduler with that)
    schedule and execute it.
    """


    def __init__(self, gs, addr = Defaults.XMLRPC_SCH_SERVER_ADDR, port=Defaults.XMLRPC_SCH_SERVER_PORT, enforce_signoffs=None):

        self._addr = addr
        self._port = port
        self.gs = gs
        self._enforce_signoffs = enforce_signoffs
        self._disabled = False

        self.server = SimpleXMLRPCServer((self._addr, self._port), allow_none=True, logRequests=False)

        # Make RPC calls more usable by publishing functions
        self.server.register_introspection_functions()

        # Register the functions
        self.server.register_function(self.execute_schedule)
        self.server.register_function(self.scheduler_state)
        self.server.register_function(self.stop_schedule)
        self.server.register_function(self.disable)
        self.server.register_function(self.enable)

        ags_log.debug('XMLRPC Server started on %s:%d'%(self._addr, self._port))


    def execute_schedule(self, schedule, track_full_pass=False, compute_ant_points = True, N=None):
        if self._disabled: # Note, the scheduler itself is also enabled/disabled. But also want to prevent the creation of new schedules.
            raise Exception("RPCSchedulerServer: Currently disabled. Call enable() first")

        schedule = Schedule.from_json(schedule)
        self.scheduler = Scheduler(self.gs, schedule, track_full_pass=track_full_pass, compute_ant_points = compute_ant_points, enforce_signoffs=self._enforce_signoffs)
        self.scheduler.execute(N=N)

    def stop_schedule(self):
        if hasattr(self, 'scheduler'):
            self.scheduler.stop()

    def scheduler_state(self):
        if hasattr(self, 'scheduler'):
            return(self.scheduler.state)
        else:
            return('never started')

    def start(self):
        self._pthr = Thread(target = self.server.serve_forever)
        self._pthr.daemon = True
        self._pthr.start()

    def disable(self):
        self._disabled = True
        if hasattr(self, 'scheduler'):
            self.scheduler.disable()
        else:
            raise Exception("No scheduler to disable")

    def enable(self):
        self._disabled = False
        if hasattr(self, 'scheduler'):
            self.scheduler.enable()
        else:
            raise Exception("No scheduler to enable")


#
# for backwards comaptability import into this namespace
#
from libgs_ops.scheduling import RPCSchedulerClient



class RPCServer(SimpleXMLRPCServer):
    """
    Drop-in replacement for SimpleXMLRPCServer that supports kwargs.

    It also allows the address to be specified as a uri, http://hostname:port instead of (hostname,port), but
    the latter is also supported for full SimpleXMLRPCServer compatability.

    Finally, it allows you to call register_function in the same way as for SimpleXMLRPCServer, but it also
    allows you to use it as a decorator.

    So these two are equivalent:

    A)

    s = RPCServer()
    @s.register_function
    def blah()
        print("blah")

    B)
    s = RPCServer()
    def blah()
        print("blah")

    s.register_function(blah)


    """

    # This flag is added by the client to an argument dictionary to be treated as kwargs
    _KWARGS_FLAG = '__xmlrpc__kwargs__'

    def __init__(self,  uri, logRequests = False, allow_none=True, start=True):

        if isinstance(uri, basestring): # Allow http://domain.name:port definition
            if uri[:8] != 'https://' and uri[:7] != 'http://':
                raise Exception('url must start with http(s)://')

            netloc = uri.split('//')[1]
            if len(netloc.split('/')) != 1 or len(netloc.split(':')) != 2:
                raise Exception('Did not understand {}. Expected http(s)://domain.name.com:port')

            host, port = netloc.split(':')
            port = int(port)
            self.uri = uri
        else:
            host, port = uri # also allow SimpleXMLRPCServer-sytle (host,port) definition
            self.uri = 'http://{}:{}'.format(host,port)

        ags_log.info("Starting RPC Server on {}:{}".format(host, port))
        SimpleXMLRPCServer.__init__(self, (host, port), allow_none = allow_none, logRequests = logRequests)

        if start:
            self.start()


    @property
    def is_serving(self):
        if hasattr(self, '_serving') and self._serving:
            return True
        else:
            return False

    def start(self):
        if self.is_serving:
            ags_log.debug("RPCServer is already serving. Not starting again. Call shutdown() first")
        else:
            self._pthr = threading.Thread(target=self.serve_forever)
            self._pthr.daemon = True
            self._pthr.start()

    def stop(self):
        self.shutdown()
        self._pthr.join(self, 2)
        if self.is_serving:
            raise Exception("Failed to stop")
        else:
            del self._pthr


    def serve_forever(self, poll_interval=0.5):
        try:
            if self.is_serving:
                log.warning("RPCServer is already serving, ignoring your call to serve_forever")
            else:
                self._serving = True
                SimpleXMLRPCServer.serve_forever(self, poll_interval)
        finally:
            self._serving = False

    def register_function(self, function, name = None):
        def _function(*params):
            args = []
            kwargs = {}
            for p in params:
                if isinstance(p, dict) and self._KWARGS_FLAG in p.keys():
                    kwargs = p
                    del kwargs[self._KWARGS_FLAG]
                else:
                    args += [p]

            return function(*args, **kwargs)

        _function.__name__ = function.__name__
        SimpleXMLRPCServer.register_function(self, _function, name)
        return _function

    def register_instance(self, instance, allow_dotted_names=False):
        raise Exception('Not implemented')


if __name__ == '__main__':
    pass

