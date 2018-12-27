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


Created on Mon Sep 18 09:22:40 2017
"""

import time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import multiprocessing
import logging
import threading


########
#
# Logging
#
########
log = logging.getLogger('libgs-log')
log.addHandler(logging.NullHandler())


############################################
#
# Alert class and
# specific derived alert types.
# A user can specify others if she wishes.
#
############################################
class Alert(object):

    def __init__(self, val):
        self.val = val

    def __str__(self):
        if not hasattr(self, 'alertstr'):
            return "'{}' Unknown Alert".format(self.val)
        else:
            return "'{}' ( {} alert<{}> )".format(self.val.__str__(), self.alertstr if self.alertstr else "NO", self.alertcode)

    def __repr__(self):
        return self.__str__()

class CriticalAlert(Alert):
    alertstr="CRITICAL"
    alertcode=100

class RedAlert(Alert):
    alertstr="RED"
    alertcode = 30

class OrangeAlert(Alert):
    alertstr="ORANGE"
    alertcode = 20

class GreenAlert(Alert):
    alertstr="GREEN"
    alertcode = 10

class NoAlert(Alert):
    alertstr  = None
    alertcode = 0



class MonitorItem(tuple):
    _fields = ('name', 'value', 'alert', 'parent', 'age')

    def __new__(cls, item):

        tuplelist = []

        for f in cls._fields:
            try:
                tuplelist += [item[f]]
            except:
                tuplelist += [None]


        return super (MonitorItem, cls).__new__(cls, tuplelist)


    def __str__(self):
        return '(' + ', '.join( "'{}': {}".format(k, "'{}'".format(v) if isinstance(v, basestring) else str(v)) for k,v in self.items() ) + ')'

    def __repr__(self):
        return self.__str__()

    def keys(self):
        return self._fields

    def items(self):
        for k, f in enumerate(self._fields):
            yield self._fields[k], self[f]

    def __getitem__(self, item):
        if item in self._fields:
            idx = self._fields.index(item)
        else:
            idx = item

        return super(MonitorItem, self).__getitem__(idx)



############################################
#
# The monitor magic
#
############################################

class Monitor(object):
    """
    Class to provide functionality for monitoring
    """


    def __init__(self,
                 workers=10,
                 tick=0.5,
                 tick_cb = lambda x: None, #TODO: Perhaps get rid of tick callbacks.
                 default_dt = 10):
        """
        Args:
            workers:    Maximum number of simultaneouse threads to spawn in the ThreadPool
            tick:       The delay between successive runs of the monitor loop. Should be fairly small (< 1 sec).
            tick_cb:    A callback that can be invoked at the end of every tick.
            default_dt: Default dt to apply to monitor generators (if dt not specified explicitly)
        """

        # Defaults
        self.default_dt   = default_dt

        # Callback
        self.tick_cb = tick_cb
        self._callbacks = [] #<-- added with add_callback

        # Set up the executor
        self._executor = ThreadPoolExecutor(workers) #<-- max threads we permit at a time

        # This is the tick
        self._tick = tick

        # A dictionary to hold the parent headings
        self._parents = {}

        # The exec map keeps track of all the monitored values and their execution status and times
        self._exec_map = pd.DataFrame(
                columns=['exec_t',       'next_exec_t',   'name',  'parent', 'dt', 'gen',
                         'loglvl_values','loglvl_alerts','logthr_alerts','dependents', 'value', 'alert'])


        # A dictionary to map alert values to human readable strings
        self._alertstr_map = {}

        # The monitoring loop runs in a separate thread
        self._pthr = None
        self._abort = threading.Event()



    def _get_alertstr(self, key):
        if key not in self._alertstr_map.keys():
            return ""
        else:
            return self._alertstr_map[key]



    def __del__(self):
        self.stop()
        self._executor.shutdown(wait=False)


    @property
    def alertcode(self):
        return max(self._exec_map.alert)


    def register_parent(self,
                        name,
                        parent=None):
        """
        A parent monitor is not really a monitor. It is merely the product
        of its children and exists for visualisation purposes only.

        Its alert status will always be the worst of its children

        """

        # If parent hadnt been explicitly defined already, define it at the top level
        if parent is not None and parent not in self._parents.keys():
            self.register_parent(parent)

        self._parents[name] = dict(parent=parent)

    def add_callback(self, callable):
        """
        Add a callable to be invoked every N times a value is polled.

        .. note::

           The callback will be executed in the same sub-thread that does the polling

        The prototype of the callable should be
            some_function(point_name, tstamp, exc, ret)

        where
            * point_name is the name of the monitor point that has been polled
            * tstamp is the unix timestamp at which the monitor function returned a value (obtained wiht time.time()),
            * exc is None if no exception happened, otherwise it is set to the exception that occurred.
            * ret are the return values. Will always be an Alert object.

        Args:
            callable: The callable

        Returns:

        """
        self._callbacks.append(callable)


    def to_gen_in_executor(self, fn, point_names, *args, **kwargs):
        """
        This decorator will take any function and turn it into a generator
        that always returns immediately after calls to next().

        The call to fn is being delegated to an executor, and while it is not
        done, calls to next() will return None, otherwise it will return a tuple containging
            * the timestamp the data the return
        value of fn

        Args:
            fn:

        Returns:

        """

        assert isinstance(point_names, tuple)
        numvals = len(point_names)

        #
        # Further wrap the call to catch any exceptions and timestamp
        # the output
        #
        def exc_wrapped(*args, **kwargs):
            try:
                res = fn(*args, **kwargs)

                if not (numvals == 1 or (numvals == len(res) and isinstance(res, tuple))):
                    lres = len(res) if isinstance(res, tuple) else 1
                    raise Exception("Unexpected number of returned values from monitor function. expected {} value(s), got {} value(s)".format(numvals, lres))

                exc = None
            except Exception as e:
                exc = e
                res = None


            if res is not None and numvals > 1:
                res = tuple(r if isinstance(r, Alert) else NoAlert(r) for r in res)
            else:
                if not isinstance(res, Alert):
                    res = NoAlert(res)

            ret = time.time(), exc, res

            # Invoke callbacks
            for cb in self._callbacks:
                try:
                    if not isinstance(res, tuple):
                        res2 = (res,)*len(point_names)
                    else:
                        res2 = res

                    for k, p in enumerate(point_names):
                        cb(p, time.time(), exc, res2[k])

                except Exception as e:
                    log.error("Error invoking callback function {}. {}: {}".format(cb.__name__, e.__class__.__name__, e))


            return ret



        def generator(*args, **kwargs):
            while True:
                future = self._executor.submit(exc_wrapped, *args, **kwargs)

                # Ensure a call returns immediately, and returns None if not ready
                while not future.done():
                    yield None

                yield future.result()

        return generator()


    #############
    #
    # Convenience decorators
    #
    #############
    def callback(self):
        """
        Decorator to convert a function definition to an IntervalCallback instance and add it to the
        monitor's callback list.
        """


        # Otherwise convert it to an IntervalCallback instance
        def decorator(fn):
            self.add_callback(fn)
            return fn

        return decorator

    def monitor(self, point = None, *args, **kwargs):
        """
        Creates a decorator that can be applied to any function to add it to be monitored.

        It will do two things:
            1) convert the function to a generator in which the function call is run in an executor, so that
               any call to the generators next() function will return immeditately and not hold up execution. If
               the function has not finished the generator will return None. If it has completed, it will return
               the value as well as a timestamp and any potential exception in the format required for the monitoring
               loop.
            2) add the function to the Monitor class  polling schedule.

        Args:
            point:           The name of the monitor point. If omitted it will use the function name
            *args, **kwargs: Also accepts all the arguments of register_monitor()

        Returns:
            Decorator

        """

        def decorator(fn):

            if point is None:
                point_names = (fn.__name__,)
            elif not isinstance(point, tuple):
                point_names = (point,)
            else:
                point_names = point

            def decorated(*args2, **kwargs2):
                f = self.to_gen_in_executor(fn=fn, point_names=point_names,*args2, **kwargs2)
                return f

            self.register_monitor(name=point_names[0], gen=decorated(), dependents = point_names[1:], *args, **kwargs)
            for p in point_names[1:]:
                self.register_monitor(name=p, gen=None,  *args, **kwargs)


            return decorated
        return decorator


    def register_monitor(self,
                         name,
                         gen,
                         dt    = -1,
                         parent=None,
                         loglvl_values = None,
                         loglvl_alerts = logging.DEBUG,
                         logthr_alerts = RedAlert.alertcode,
                         dependents = tuple(),
                         alert_exc = NoAlert):
        """
        This is a low level function to register a monitor generator with the monitor class.

        The format of the generator is quite specific, and it should therefore ideally have been created from
        a callable using the to_gen_in_executor() method. Using this method will ensure the generator returns
        values in the right format for the monitor class, and that it never blocks.


        Args:
            name:           The name of the monitor point
            gen:            The monitor generator (* see description above)
            dt:             The time interval in which to poll the monitored (dt = None -> one shot)
            parent:         Assign a parent to the monitored (For grouping purposes only,
            loglvl_values:  If not None, any change in value will be logged with the logging level specified.
            loglvl_alerts:  If not None, a change in alert level may be logged with the logging level specified
            logthr_alerts:  The threshold for the alertcode above by which to log. Default = RedAlert.alertcode
            dependents:     Other monitors to update from same generator
            alert_exc:      Alert to set in case an exception is raised in monitor function. Default = NoAlert

        """

        if dt is None:
            dt = 1e11 #<-- large number to prevent it from running again

        # One-shot can be enabled by setting dt == None. Negative dt = unset, and defaults will be applied
        # Continous running (ie every tick) is enabled by setting dt = 0
        elif dt < 0:
            dt = self.default_dt


        log.debug("Adding monitor point '{}'".format(name))

        # If parent hadnt been explicitly defined already, define it at the top level
        if parent is not None and parent not in self._parents.keys():
            self.register_parent(parent)

        if name in self._exec_map['name']:
            raise Error("{} already exists. Names must be unique".format(name))


        self._exec_map = self._exec_map.append(dict(
            exec_t=None,
            next_exec_t = time.time(),
            name=name,
            dt=dt,
            gen=gen,
            parent=parent,
            dependents=dependents,
            loglvl_values = loglvl_values,
            loglvl_alerts = loglvl_alerts,
            logthr_alerts = logthr_alerts,
            alert_exc=alert_exc),
            ignore_index=True)

        # Make sure value is of dtype=object so it can
        # accept values of different types
        if self._exec_map.value.dtype != 'object':
            self._exec_map.value = self._exec_map.value.astype('object')

        if self._exec_map.alert.dtype != 'object':
            self._exec_map.alert = self._exec_map.alert.astype('object')

        self._exec_map.sort_values('exec_t', inplace=True)


    def start(self, subprocess = False):
        if self._pthr is not None:
            return

        if subprocess:
            self._pthr = multiprocessing.Process(target=self._polling_loop)
            self._pthr.daemon = True
        else:
            self._pthr = threading.Thread(target=self._polling_loop)
            self._pthr.daemon = True

        self._pthr.start()

    def stop(self):
        if self._pthr is None:
            return

        self._abort.set()
        self._pthr.join()
        self._pthr = None


    def _polling_loop(self):

        while not self._abort.is_set():
            self._poll_due()

            # TODO: Generalise this to be able to call add_cb and add any number of callbacks at different rates
            try:
                self.tick_cb(self)
            except Exception as e:
                log.error("Error invoking tick callbak. {}: {}".format(e.__class__.__name__, e))

            # TICK
            time.sleep(self._tick)


    def _poll_due(self):
        """
        Poll whatever is due
        """
        #
        # Get the variables that are due for polling and loop through them
        # to poll.
        #
        to_exec = self._exec_map[(~pd.isnull(self._exec_map.gen)) &
                                 (time.time() > self._exec_map.next_exec_t)].sort_values('next_exec_t')


        # Try to get values for everything that is due
        for k, item in to_exec.iterrows():
            val = item.gen.next()

            # No value means the poller hasnt returned yet so just leave it to try again at the next tick
            if val is None:
                continue

            tstamp, exc, ret = val

            dependents = self._exec_map.at[k, 'dependents']

            if exc is not None:
                if ret.val is not None:
                    raise Exception("Unexpected. It should not be possible to get an exception and return value at the same time. ret='{}', exc='{}'".format(ret, exc))

                alertclass = self._exec_map.at[k, 'alert_exc']
                ret =  (alertclass("ERROR {}: {}".format(exc.__class__.__name__, exc)),) * (len(dependents) + 1)

            else:
                # Ensure that the result is always a tuple so that iteration works properly
                if len(dependents) == 0:
                    ret= (ret,)

            # populate dependents
            for k1, dep in enumerate((item['name'],) + dependents):

                # Look up the index of the dependent
                dep_k = self._exec_map[self._exec_map['name'] == dep].index
                assert len(dep_k) == 1
                dep_k = dep_k[0]

                self._log_value(k, ret[k1].val)        #<-- TODO: Could be implmented using the generalised callback functionality we have
                self._log_alert(k, ret[k1].alertcode)  #<-- TODO: Could be implmented using the generalised callback functionality we have

                # Update the dependent
                self._exec_map.at[dep_k, 'value']  = ret[k1].val
                self._exec_map.at[dep_k, 'alert']  = ret[k1].alertcode
                self._exec_map.at[dep_k, 'exec_t'] = tstamp
                self._exec_map.at[dep_k, 'next_exec_t'] = None if self._exec_map.at[k, 'dt'] is None else tstamp + self._exec_map.at[k, 'dt']

                if not ret[k1].alertcode in self._alertstr_map.keys():
                    self._alertstr_map[ret[k1].alertcode] = ret[k1].alertstr if ret[k1].alertstr is not None else ''



    def _log_value(self, k, val):
        #
        # Log a change in value if requested and as requested
        #
        item = self._exec_map.loc[k]
        if (item['value'] != val) and (item['loglvl_values'] is not None):
            log.log(int(item['loglvl_values']), 'Monitor: value "{}" --> {}'.format(item['name'], val))

    def _log_alert(self, k, alertcode):
        #
        # Log a change in alert if requested and as requested
        #
        item = self._exec_map.loc[k]
        if ((item['alert'] != alertcode) and
            (item['loglvl_alerts'] is not None) and
            (item['logthr_alerts'] <= alertcode or item['alert'] >= item['logthr_alerts'] )):

            log.log(int(item['loglvl_alerts']), 'Monitor: alert "{}" --> {}'.format(item['name'], alertcode))


    def __getitem__(self, item):
        """
        Note: Returns a copy of the entry so changing variables will not change it in the monitor

        Args:
            item:

        Returns:

        """

        if item in self._parents.keys():
            it = MonitorItem({'name':item, 'parent': self._parents[item]['parent']})
        else:
            it = self._exec_map[self._exec_map['name'] == item]

            if len(it) > 1:
                raise Exception("Monitor name is not unique. This should not be possible")

            if len(it) < 1:
                raise Exception("Monitor name does not exist")


            itd = it.iloc[0].to_dict()
            itd['age'] = time.time() - itd['exec_t'] if itd['exec_t'] else None

            it = MonitorItem(itd)

        return it #<-- TODO: Decide if we should return all fields or a subset

    def __iter__(self):
        for k,r in self._exec_map.iterrows():
            yield r['name'], r['value'], r['alert'], time.time() - r['exec_t']

    def __str__(self):
        s = ""
        s += " Monitor "
        if self.alertcode > 0:
            s += "({}) ".format(self._get_alertstr(self.alertcode))

        s += "--- running\n" if hasattr(self, '_pthr') else '--- not running\n'
        s += " {:<30s}{:<40s}{:<10s}{:<15s}\n".format("Name", "Value", "Alert", "Last polled")
        s += " "+ "-" * 29 + " " + "-" * 39 + " " + "-" * 9 + " " + "-" * 15 + "\n"
        for item in self.itertree():
            parent = item['parent']
            level = 0
            while parent is not None:
                parent = self[parent]['parent']
                level += 1

            t0 = time.time()
            s += " {:30.29s}{:40.39s}{:10.9s}{:s}\n".format(
                '.' * (level + 1) + item['name'],
                '' if item['value'] is None else str(item['value']),
                '' if item['alert'] is None else self._get_alertstr(item['alert']),
                '{:.2f}'.format(item['age']) if item['age'] else '')

        return s

    def __repr__(self):
        return self.__str__()


    def itertree(self, parent=None):
        if parent is None:
            top = self._exec_map['name'][pd.isnull(self._exec_map.parent)].tolist()
            top += [k for k, v in self._parents.items() if v['parent'] is None]
        else:
            top = self._exec_map['name'][self._exec_map.parent == parent].tolist()
            top += [k for k, v in self._parents.items() if v['parent'] == parent]

        if len(top) == 0:
            raise StopIteration

        top.sort()

        for k in top:
            yield(self[k])
            for it in self.itertree(parent=self[k]['name']):
                yield it




    def keys(self):
        """
        Just include this since dicts etc all use keys to describe the access keys. Although in this class
        names is more descriptive. This method is the same as .names()

        Returns:

        """
        return list(self._exec_map['name'])

    def names(self):
        return self.keys()


if __name__ == '__main__':
    from utils import setup_logger
    import random
    setup_logger(log, cons_loglvl=logging.DEBUG)
    from database  import MonitorDb

    db = MonitorDb(db='sqlite:///mondbtest.db')

    mon = Monitor(workers=2,default_dt=2)

    #
    # @mon.monitor(parent="test", dt=5, dtdb=5)
    # # @alert_a
    # def blah1():
    #     time.sleep(2)
    #     return 'a'
    #
    # @mon.monitor("b", dt=2, dtdb=5)
    # def blah2():
    #     #time.sleep(2)
    #     return 'b'
    #
    #
    # @mon.monitor("c", dt=10)
    # def blah3():
    #     time.sleep(2)
    #     return RedAlert('c')
    #
    #
    # @mon.monitor(dt=30)
    # # @alert_a
    # def fail():
    #     time.sleep(1)
    #     1/0
    #     return("done")
    #
    #
    # @mon.monitor(("test1","test2", "test3", "test4", "test5"), parent='test_many_ret')
    # def test():
    #     time.sleep(2)
    #     return 1,CriticalAlert(2),GreenAlert(3),RedAlert(4),5
    #

    from datetime import datetime

    import psutil
    #from libgs.monitoring import Monitor

    #mon = Monitor(default_dt=5)

    count = dict(a=1,b=1,c=1,d=1,e=1,f=1,current_time=1,cpu_usage=1)

    @mon.monitor(point=("a","b","c","d","e","f"))
    def randmon():
        #time.sleep(1)

        for k,v in count.items():
            count[k] += 1

        return random.random(),random.random(),random.random(),random.random(),random.random(),random.random()

    @mon.monitor(parent='grandchild')
    def current_time(x=2):
        count['current_time'] +=1
        return datetime.utcnow()


    @mon.monitor(parent='parent')
    def cpu_usage():
        count['cpu_usage'] +=1
        usage = psutil.cpu_percent(interval=1)

        if usage > 50:
            return RedAlert(usage)
        else:
            return GreenAlert(usage)






    # last_t = {}
    # dt = 10
    # @mon.callback()
    # def save( name, tstamp, exc, res):
    #     if name in last_t.keys() and time.time()  <  last_t[name] + dt:
    #         # print('NOT saving {}'.format(name))
    #         return
    #
    #     last_t[name] = time.time()
    #     # print('saving {}'.format(name))
    #     #db.put(0, args[0], args[3].val)


    #mon.register_parent('parent')
    # mon.register_parent('child', parent='parent')
    # mon.register_parent('grandchild', parent='child')


    mon.start()




