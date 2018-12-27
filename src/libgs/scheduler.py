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


Created on Sun Aug  6 17:36:19 2017

@author: kjetil
"""


#
# Import everything from libgs_obs.scheduling into this namespace
# for backwards compatability when this was the module  it all lived in
#
from libgs_ops.scheduling import *

from utils import Error
import pandas as pd
import numpy as np
from utils import Defaults, bytes2prettyhex, hex2bytes, bytes2hex, wait_loop
import time
from threading import Timer
from functools import wraps
from multiprocessing.pool import ThreadPool

import logging
log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())


# TODO: Make sure only a single scheduler can be used with a ground station
#        (Multiple ones are a recipe for disaster)
class Scheduler(object):
    """
    This is the main scheduler class.

    It is responsible for executing the schedule on the ground station. As such
    it needs access to both the ground station instance
    and the schedule instance.

    ..note::
        A schedule is assumed immutable after being added to the scheduler
    """


    #
    # The scheduler states.
    #
    # IDLE:      Never before executed
    # STOPPED:   Has executed and finished
    # EXECUTING: Is currently executing
    #
    class States:
        IDLE        = 'idle'
        STOPPED     = 'stopped'
        EXECUTING   = 'executing'

    def __init__(self, gs, schedule, track_full_pass=False, compute_ant_points=True, enforce_signoffs=None):
        """

        Args:
            gs (Groundstation): Instance of Grounstation class
            schedule (Schedule): The schedule to execute
            track_full_pass (bool (optional)): If this flag is true the scheduler will not complete
                 a pass before the satellite is no longer in view, regardless of whether there
                 are any remaining communications. (Useful for debugging)
        """

        if hasattr(gs, 'scheduler') and gs.scheduler is not None and gs.scheduler.state == Scheduler.States.EXECUTING:
            log.error("The ground station already has a running scheduler. You cannot create a new schedule before it has been completed or stopped")
            log.error(
                "An attempt was made to create a scheduler while another is running on the ground station. Raising exception.")
            raise Error("Another scheduler is already executing a schedule on that groundstation. Stop it first")


        # These two variables determine the state
        self._stop = False
        self._continue = 0

        self.schedule = schedule

        self.gs = gs
        self.gs.set_schedule_msg(unicode(schedule.__str__()))  # TODO: Maybe store the entire schedule in the state ?
        self.timer = None
        self.tstamps = [pd.to_datetime(p.pass_data.tstamp_str.iloc[0]) for p in schedule.passes]

        self.track_full_pass = track_full_pass
        self.compute_ant_points = compute_ant_points
        self.enforce_signoffs = enforce_signoffs

    #
    # Use properties for the timer in order to ensure that the State is updated
    # appropriately whenever the timer changes
    #
    @property
    def timer(self):
        return self._timer

    @timer.setter
    def timer(self, t):
        self._timer = t
        self.gs.set_schedule_msg(unicode(self.__str__()))

    @property
    def state(self):
        if self._stop:
            return Scheduler.States.STOPPED
        elif self._continue > 0:
            return Scheduler.States.EXECUTING
        else:
            return Scheduler.States.IDLE


    def __str__(self):
        s = 'Schedule of communication passes:\n'
        s += '  -- ---- -------- -------------------- -------------------- --------------\n'
        s += '     #    Norad id Pass start (utc)     Pass end (utc)       Communications\n'
        s += '  -- ---- -------- -------------------- -------------------- --------------\n'
        state = [' '] * len(self.schedule.passes)
        if self.timer is not None:
            state[self.timer[0]] = self.timer[1]

        for i, p in enumerate(self.schedule.passes):
            s += '  %s  %04d %-8s %-20s %-20s %d\n' % (
                state[i],
                i,
                str(p.nid),
                p.pass_data.tstamp_str.iloc[0],
                p.pass_data.tstamp_str.iloc[-1],
                len(p.comms))

        s += '  -- ---- -------- -------------------- -------------------- --------------\n'
        s += '  %s' % (self.state)

        return (s)

    def __repr__(self):
        return self.__str__()


    # Allow the disabling of the scheduler. Main reason is to allow the disabling of the scheduler
    # when testing to prevent remote connections via rpc
    @property
    def disabled(self):
        if hasattr(self, '_disabled'):
            return self._disabled
        else:
            return False

    @disabled.setter
    def disabled(self, val):
        if val not in [True, False]:
            raise Exception("Scheduler: Disabled can only be True or False")

        # Stop ground station if disabling
        if val == True:
            self.stop()

        self._disabled = val

    def disable(self):
        self.disabled = True

    def enable(self):
        self.disabled = False

    # a wrapper to disable funciton calls if class disabled.
    def _if_not_disabled(fn):
        @wraps(fn)
        def wrapped_fn(self, *args, **kwargs):
            if self.disabled:
                raise Exception("{} called, but Scheduler is disabled. Call enable() first.".format(fn.__name__))
            else:
                ret = fn(self, *args, **kwargs)

            return ret

        return wrapped_fn

    def _next_pass(self):
        now = pd.Timestamp(pd.datetime.utcnow())
        next_idx = [t > now for t in self.tstamps].index(True)
        return next_idx

    def _schedule_pass(self, i):
        """
        Function to add a timer and schedule a specific pass
        """

        if self.timer is not None:
            raise Error("Pass %d has already been scheduled" % (i))

        if not self._stop:

            tstart = self.tstamps[i] - pd.Timedelta(seconds=self.schedule.buffertime)
            now = pd.Timestamp(pd.datetime.utcnow())

            if tstart <= now:
                self.stop()  # <-- Added 2018-06-14. Seems like a sensible thing to sensure timers etc are reset. To be checked
                raise Error("Can't schedule a pass that is less than %d sconds in the future. Scheduler stopped." % (
                    self.schedule.buffertime))
            sleeptime = (tstart - now) / np.timedelta64(1, 's')

            self.timer = (i, 'S', tstart, Timer(sleeptime, self._callback, args=(i,)))
            self.timer[-1].daemon = True
            self.timer[-1].start()

    @_if_not_disabled
    def execute(self, N=None):
        """
        Execute the schedule.

        Args:
            N (int, optional): Number of passes to execute. If N is omitted
               or None, execute the entire schedule.
        """

        #
        # In order to execute, the current schedule must be in the idle state (i.e. NEVER before executed)
        # *and* there must be no schedule running on the ground station.
        #

        if self.state !=  Scheduler.States.IDLE:
            log.error("An attempt was made to execute a scheduler that was in the incorrect state, '{}'. A scheduler can only"+
                      "be executed while in the 'idle' state. I.e. never before executed. Raising exception.".format(self.state))
            raise Error("A scheduler can only be executed while in the 'idle' state (i.e. never before executed). The current state is '{}'".format(self.state))

        if hasattr(self.gs, 'scheduler') and self.gs.scheduler is not None and self.gs.scheduler.state ==  Scheduler.States.EXECUTING:
            raise Error("Unexpected error: This error should not be possible. Indicates that a different scheduler may be running on the ground station.")


        self.gs.scheduler = self

        log.info("Executing schedule:\n%s" % (self.schedule))

        if N is None:
            self._continue = len(self.schedule.passes)
        else:
            self._continue = N

        try:
            np = self._next_pass()
        except ValueError:
            raise Error("No future passes in schedule")

        self._schedule_pass(np)

    @_if_not_disabled
    def stop(self):

        log.info("Stopping scheduler")

        if self._stop:
            log.debug("Already stopped. Not doing anything")
            return

        self._stop = True

        # Update schedule message to reflect state change
        self.gs.set_schedule_msg(unicode(self.__str__()))

        if self.timer is not None:
            if self.timer[1] == 'R':
                log.warn("Pass is currently executing, the scheduler may not exit properly until it is done")

            if self.timer[-1] is not None and self.timer[-1].is_alive():
                self.timer[-1].cancel()

            self.timer = (self.timer[0], 'X', None, None)
        else:
            log.debug("BLAH: timer is none on call to stop()")

    def _callback(self, i):

        if not self._stop:

            self.timer = (self.timer[0], 'R', None, None)
            log.info("Executing %s" % (self.schedule.passes[i]))

            self.execute_pass(i)  # <-- this one traps all its own errors so should never fail
            log.info("Completed pass execution")

            self._continue -= 1
            self.timer = None

            if self._stop:
                log.debug("Scheduler was aborted mid-pass, will not continue")
                return

            if (self._continue > 0) and (( i + 1) < len(self.schedule.passes)):
                self._schedule_pass(i + 1)
            else:
                log.info("Scheduler has finished executing schedule")
                self._continue = 0 #<-- this is probably not necessary, but set it to 0 just in case.
                self.stop() #<-- Added 2018-09-14 Make sure the schedule is marked as stopped regardless of the reason for finishing (This prevents attempts to restart it)

    @_if_not_disabled
    def execute_pass(self, i):
        """
        Method to execute a pass on the ground station.

        Will initiate tracking of the satellite and perform all the communications
        that have been defined.

        For each communication, it will wait for a reply before continuing. If
        no reply is received it will retry as many times as specified in the schedule.

        If no reply is expected, the schedule should specify retries=0

        Args:
            i (int): Pass number from the schedule
        """

        # Wrap everything in try/except/finally to make sure that
        # if anything bad happens during a pass
        # it does not make everything fall over.
        try:
            stop = lambda: self._stop
            not_tracking = lambda: self.gs.state.state != self.gs.state.TRACKING

            metadata = self.schedule.passes[i].metadata
            p = self.schedule.passes[i].pass_data
            p.nid = self.schedule.passes[i].nid


            if self.enforce_signoffs and p.nid <= 0:
                log.warning("The schedule does not have enough signoffs, but NID = {} is not a real satellite so allowing scheduler to continue anyway".format(p.nid))
            elif self.enforce_signoffs:
                if not 'signoffs' in metadata.keys() or len(metadata['signoffs']) < self.enforce_signoffs:
                    log.error("The schedule does not have enough signoffs. At least {} are required.".format(self.enforce_signoffs))
                    return


            #
            # 2) Slew to start and wait for satellite to come into view
            #
            self.gs.start_track(p, compute_ant_points=self.compute_ant_points)

            #
            # Give the GS a second to initiate the pass_id variable, then save schedule
            # to log.
            #
            time.sleep(1.0)
            log.debug("Storing schedule in database. pass_id = {}".format(self.gs.state.pass_id[1]))

            try:
                self.gs._passlog.put(module=__name__, pass_id=self.gs.state.pass_id[1], key="schedule",
                                     value=self.schedule.passes[i].to_json())
            except Exception as e:
                log.exception("Exception trying to insert schedule in database: {}: {}")


            if 'signoffs' in metadata.keys():
                log.info("The pass has been signed by {}".format(metadata['signoffs']))

                try:
                    self.gs._passlog.put(module=__name__, pass_id=self.gs.state.pass_id[1], key="signoffs",
                                         value=metadata['signoffs'])
                except Exception as e:
                    log.exception("Exception trying to insert signoffs in database: {}: {}")

            log.info("Waiting for pass")
            if stop in wait_loop([stop, lambda: self.gs.state.state == self.gs.state.TRACKING], timeout=None, dt=.5):
                log.debug("execute_pass aborted with stop event")
                return

            #
            # Set the protocol to use
            #
            if len(self.gs.protocols) == 0:
                raise Error("No protocol installed")

            # TODO: Logic to go here to choose the right protocol based on the schedule
            if 'protocol' in metadata.keys():
                try:
                    self.gs.protocol = metadata['protocol']
                except Exception as e:
                    raise Error("Unknown protocol {} requested, pass cannot continue".format(metadata['protocol']))
            else:
                log.info("No protocol has been specified, using default {}".format(self.gs.protocols[0].name))
                try:
                    self.gs.protocol = self.gs.protocols[0]
                except Exception as e:
                    raise Error("Could not set default protocol. This error should really not be possible. {}: {}".format(e.__class__.__name__, e))


            # Make the pass metadata available to the protocol
            self.gs.protocol.sch_metadata = metadata

            #
            # Initialise
            #
            if self.schedule.passes[i].listen:
                log.debug("Listening pass, calling protocol.init_rx initiator")
                self.gs.protocol.init_rx()
            else:
                log.debug("Non-listening pass, calling protocol.init_rxtx initiator")
                self.gs.protocol.init_rxtx()



            #
            # This is a bit tricky but needs to be done this way so
            # that the action/transmit can be aborted.
            # What happens is that the method is run in a threadpool
            # and while we are waiting for the result we also monitor
            # for whether the station has stopped tracking or the _stop
            # flag has been set
            #
            #
            def action_thread(desc, *args, **kwargs):
                # this little wrapper function is just to make sure we log exceptions properly
                try:
                    self.gs.do_action(desc, *args, **kwargs)
                except Exception as e:
                    log.exception(
                        "{} performing action {}, {}, {}: '{}'".format(e.__class__.__name__, desc, args, kwargs,
                                                                       e))
                    raise

            pool = ThreadPool(processes=1)


            #
            # Send all communications/actions
            #
            for comm in self.schedule.passes[i].comms:

                retry_cnt = -1
                while (retry_cnt < comm['retries']):

                    # This flag gets set if someone calls stop()
                    if self._stop:
                        return

                    # Make it possible to cancel schedule half-way through track
                    elif (not_tracking()):
                        log.error("Pass ended before comms finished")
                        return


                    if isinstance(comm, Action):

                        ret = pool.apply_async(lambda: action_thread(comm['desc'], *comm['args'], **comm['kwargs']))
                        ret2 = wait_loop([ret.ready, not_tracking, stop])

                        if not_tracking in ret2 or stop in ret2:
                            log.error("do_action aborted")
                            return  # <--- the do_action may still be running, but will be dealt with by  the "finally" at the end of this function
                        elif not ret.successful():
                            log.error("Error performing action: %s. Trying again" % (comm))
                            retry_cnt += 1
                            continue

                    else:

                        wait = -1 if comm['wait'] is False else Defaults.TX_REPLY_TIMEOUT

                        log.info("Transmitting %s" % (comm['hexstr']))

                        ret = pool.apply_async(lambda: self.gs.transmit(comm['barray'], wait=wait))
                        ret2 = wait_loop([ret.ready, not_tracking, stop])

                        if not_tracking in ret2 or stop in ret2:
                            log.error("transmit aborted")
                            return  # <--- the do_action may still be running, but will be dealt with by  the "finally" at the end of this function
                        elif not ret.successful():
                            sleept = 10
                            log.error("Caught exception while transmitting. Waiting another %d sec, then continuing" % (
                                sleept))
                            wait_loop(timeout=sleept) #<-- safe way to sleep. will terminate on global abort (but not for a normal stop, ok since its just a few seocncds)
                            retry_cnt += 1
                            continue

                    # if ok, break retry loop
                    break

            #
            # 4) End track,
            # (unless scheduler has been configured to follow track till its end)
            #
            if self.track_full_pass:
                log.info("Waiting for pass to finish")
                wait_loop([stop, lambda: self.gs.state.state != self.gs.state.TRACKING], timeout=None, dt=.5)
                return


            else:
                # Keep tracking for a bit since sometimes it seems data keeps coming
                log.info("Waiting up to %s before ending tracking" % (self.schedule.buffertime))

                wait_loop([stop, lambda: self.gs.state.state != self.gs.state.TRACKING],
                          timeout=self.schedule.buffertime, dt=.5)
                return

        except Exception as e:
            log.error("Unhandled exception while executing pass: {}: {}".format(e.__class__.__name__, e))
        finally:
            #
            # Turn off protocol/radio
            #
            try:
                self.gs.protocol.terminate()
                log.debug("execute_pass.finally reached and protocol.terminate() called successfully")
            except Exception as e:
                log.error(
                    "execute_pass.finally reached but with error calling terminate: {}:{}".format(e.__class__.__name__, e))

            #
            # Stop tracking if its still doing so
            #
            try:
                self.gs.stop_track(block=True)
                log.debug("execute_pass.finally reached and groundstatio.stop_track() called successfully")
            except Exception as e:
                log.error("execute_pass.finally reached but error calling groundstatio.stop_track(). {}: {}".format(e.__class__.__name__, e))




if __name__ == '__main__':
    pass


