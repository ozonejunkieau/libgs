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


:date: Created on Wed Jun 14 12:32:08 2017

This module implements emulation routines - mostly against hardware -
for testing the libgs library whennot connected
to the hardware

@author: kjetil
"""




import socket
import select
import sys
import threading
import signal
import time
import zmq
import random
from math import pi, cos, sin
import numpy as np
from SimpleXMLRPCServer import SimpleXMLRPCServer


#
# Configure logging with the name libgs-log, and add the NullHandler. That
# means that log messages will be dropped unless the application using this
# library configures logging.
#
import logging
log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())



#
# Class for catching signals
#
class Killer(object):

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit)
        signal.signal(signal.SIGTERM, self.exit)
        self.kill_now = False

    def exit(self, *argv):
        self.kill_now = True


class Server(object):
    """
        Generic TCPIP Server. Opens on a port
        Will accept predefined commands and
        return predefined answers.
    """


    def __init__(
            self,
            port=8000,
            persist=False,
            resp=None):

        #
        # Port
        #
        self.PORT=port

        #: Leave client connections open
        self._persistant_connections = persist

        #: response dictionary
        self.responses = resp


    def _close_connection(self, s):
        self._inputs.remove(s)
        s.close()

    def _thread_server(self):
        self._server_id = threading.current_thread()

        HOST, PORT = '', self.PORT

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(0)#settimeout(1)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)


        #listen_socket.settimeout(1)

        self._inputs = [server]
        inputs = self._inputs
        outputs = []




        # Outgoing message queues (socket:Queue)
        #message_queues = {}

        while inputs:
            if self._server is False:
                for s in inputs:
                    s.close()
                break

            readable, writable, exceptional = select.select(inputs, outputs, inputs, 1.0)

            # Handle inputs
            for s in readable:

                if s is server:
                    # A "readable" server socket is ready to accept a connection
                    connection, client_address = s.accept()
                    #print(('new connection from %s',(client_address)), file=sys.stderr)
                    connection.settimeout(1)
                    inputs.append(connection)

                else:
                    data = s.recv(1024)
                    if data:
                        # A readable client socket has data
                        #print ( 'received "%s" from %s' % (data, s.getpeername()), file=sys.stderr)
                        response = self._respond(data)

                        try:
                            s.sendall(response)
                        except:
                            print('Socket error when sending:', sys.exc_info()[0] )

                    if self._persistant_connections is False:
                        self._close_connection(s)

        self._server_id = None

    def _respond(self, data):
        """
            Respond by simple echo

        """

        self.last_data = data
        resp = ''
        if self.responses is None:
            return data
        else:
            cmds = data.replace('\r', '')
            cmds = cmds.split('\n')

            for cmd in cmds:
                if cmd == '':
                    continue

                if cmd in self.responses.keys():
                    resp = self.responses[cmd]
                elif 'DEFAULT' in self.responses.keys():
                    resp = self.responses['DEFAULT']
                else:
                    resp = ""


                resp += "\n"

        return resp



    def start(self):
        print('Starting server...')

        self._server = True
        p = threading.Thread(target=self._thread_server)
        p.daemon = True
        p.start()

        print('    Server running')

    def stop(self):
        print('Stopping server...')

        self._server = False

        thr = self._server_id
        if thr is not None:
            print('    waiting')
            thr.join()

        print('    server stopped')


    def close_all(self):
        for s in self._inputs[1:]:
            self._close_connection(s)



class SpaceTrack(Server):
    """
    Emulate space-track.org server

    :todo: Implement SpaceTrack class
    """
    pass

class Rotctld(Server):
    """
    Emulate hamlib rotctld daemon responses

    Simple response.
    Allows for the commands p (get position) and P (set position)

    Will also implement a simple slewing from one to the other over
    a set amount of time.


    """

    def __init__(self):

        super(Rotctld, self).__init__(port=4533, persist=True)

        self._cur_pos = (125, 24)
        self._cmd_pos = (125, 24)
        self._cmd_t   = 0

        #: time to slew to new position
        self.slew_t  = 4


    def _respond(self, data):
        data = data.rstrip()
        if data == 'p':
            dt = min(self.slew_t, time.time() - self._cmd_t)

            if dt >= self.slew_t:
                self._cur_pos = self._cmd_pos
                resp = "%.6f\n%.6f\n"%(self._cur_pos)
            else:

                d_az = dt*(self._cmd_pos[0] - self._cur_pos[0])/self.slew_t
                d_el = dt*(self._cmd_pos[1] - self._cur_pos[1])/self.slew_t


                resp = "%.6f\n%.6f\n"%(self._cur_pos[0] + d_az, self._cur_pos[1] + d_el)
        elif data[0] == 'P':
            self._cmd_pos = (float(data.split(' ')[1]), float(data.split(' ')[2]))
            resp = 'RPRT 0\n'
            self._cmd_t = time.time()
        else:
            resp = "Command '%s' not found!\n"%(data.rstrip())

        return resp



class Radio(object):
    """
    This class emulates a GNU Radio frontend by providing the xmlrpc
    and zmq interfaces expected in a adfa-gs frontend, and provide a random
    IQ stream.
    """

    def __init__(
            self, 
            addr = '127.0.0.1', 
            port=8051, 
            ifvars = {'freq':449e6, 'samp_rate':74e3, 'rangeRate':1000},
            iqport = 5560):
            
        self._addr = addr
        self._port = port
        self._ifvars = ifvars
        self._iq_port = iqport
        self._stop = False
        
        if 'samp_rate' in ifvars.keys():
            self._sample_rate = ifvars['samp_rate']
        else:
            self._sample_rate = 74e3

        # Set up XMLRPC server on port 8051
        self._rpcserver = SimpleXMLRPCServer((self._addr, self._port), allow_none = True, logRequests=False)

        # Register the functions

        def make_func(v):
            def _get_func():
                #log.debug("Radio: %s was called"%(_get_func.__name__))
                return getattr(self, v)

            def _set_func(val):
                log.debug("Radio: %s was called with arg %.0f"%(_set_func.__name__, val))
                setattr(self, v, val)

            return _get_func, _set_func

        for v,val in self._ifvars.items():
            get_func, set_func = make_func(v)
            get_func.__name__ = 'get_%s'%(v)
            set_func.__name__ = 'set_%s'%(v)
            setattr(self, 'get_%s'%(v), get_func)
            setattr(self, 'set_%s'%(v), set_func)

            self._rpcserver.register_function(eval('self.get_%s'%(v)))
            self._rpcserver.register_function(eval('self.set_%s'%(v)))

            set_func(val)

        self._rpcserver.register_introspection_functions()
        
        
        
    def _start_iq_server(self):

        def _pthr_serve_iq():
            N = 64
            while True:
                # Generate IQ
                data = self._generate_iq(N)
                
                # Dump over zmq
                self._sock.send(data.tobytes())
                
                # Sleep a tiny bit to simulate the sample rate
                # sleep time = N/samp_rate
                time.sleep(float(N)/self._sample_rate)
                
                if self._stop:
                    return

        self._context = zmq.Context()
        self._sock = self._context.socket(zmq.PUB)
        self._sock.bind("tcp://*:{}".format(self._iq_port))
        
        self._pthr_iq = threading.Thread(target = _pthr_serve_iq)
        self._pthr_iq.daemon = True
        self._pthr_iq.start()
        


    def _generate_iq(self, N):
        """
        Generate IQ values. These have amplitude with mean=0.0025, std=0.0076 and random phase angles
        """
        x = [np.complex(a*cos(b), a*sin(b)) for a, b in zip([random.gauss(0.0025, 0.0076) for i in range(N)], [random.uniform(-pi,pi) for i in range(N)])]
        npx = np.array(x, dtype=np.complex64)
        return npx


    def start(self):
        # self.stop()
        self._pthr = threading.Thread(target = self._rpcserver.serve_forever)
        self._pthr.daemon = True
        self._pthr.start()

        
        self._start_iq_server()
        
    def stop(self):
        self._stop = True
        
        if hasattr(self, '_pthr'):
            self._rpcserver.shutdown()
            self._rpcserver.server_close()            
            self._pthr.join()
        
        if hasattr(self, '_pthr_iq'):
            self._pthr_iq.join()
        



if __name__ == '__main__':
    pass
    r = Radio()
    from xmlrpclib import ServerProxy
    s = ServerProxy('http://localhost:8051')

    #s2 = Rotctld()
    #s2.start()

    #sat =  BuccaneerSpacelink()
