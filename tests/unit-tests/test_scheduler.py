# -*- coding: utf-8 -*-
"""
Created on Fri Aug 11 17:13:45 2017

py.test module to test the "scheduler" module


.. todo::
    Also implement integration test that tests the schedule executing


@author: kjetil
"""


import sys, os
from os.path import dirname


#
# Make sure the files one path level up are importable
#
#_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
#sys.path.insert(0, _root_dir)
sys.path.insert(0, '../../src')

#_adfags_path = dirname(dirname(dirname(os.path.realpath(__file__)))) + '/src/adfagslib/'
#sys.path.insert(0, _adfags_path) 

from libgs.utils import Error
from libgs.scheduler import Communication, CommsPass, Schedule, Scheduler, Action
from libgs.propagator import Propagator, TLEDb
import pandas as pd

import pytest



######################################################
#
# Communication class
#
######################################################

@pytest.mark.parametrize("data,retries", [
    ('CD-EF-00-01', 0),
    (bytearray('\xcd\xef\x00\x01'),3),
])
def test_Communication(data, retries):
    c = Communication(data, retries=retries)
    assert (c['retries'] == retries and c['barray'] == '\xcd\xef\x00\x01' and c['hexstr'] == 'CD-EF-00-01')

@pytest.mark.parametrize('args, kwargs, desc, retries', [
    ((1,2,3), None, "test1", None),
    (("Hello", 2, [1,2, {'a':1}]), None, "test2", None ),
    ((1,), dict(blah=1,blahblah=2),None ,None)
])
def test_Action(args, kwargs, desc, retries):

    kwargs1 = {}
    if kwargs is not None:
        kwargs1['kwargs'] = kwargs

    if desc is not None:
        kwargs1['desc'] = desc

    if retries is not None:
        kwargs1['retries'] = retries

    Action(args,**kwargs1)


def test_Action_invalid_input():
    with pytest.raises(Error):
        Action((bytearray([1,2,3]),))

@pytest.mark.parametrize("data,retries", [
    ('CD--EF-00-01',  0),
    ('Hello', 1),
    ('CD-EF-00-01', -1)

])
def test_Communication_invalid_input(data, retries):
    with pytest.raises(Error):
        Communication(data, retries=retries)

@pytest.fixture
def propagator():
    tles = \
        """
        0 50 SAT
        1 39436U 13066W   17171.25287563 +.00017336 +00000-0 +47683-3 0  9997
        2 39436 097.7085 277.3534 0011641 077.3604 282.8940 15.37193831195979
        0 ISS (ZARYA)
        1 25544U 98067A   17171.52596809 +.00002365 +00000-0 +43059-4 0  9992
        2 25544 051.6433 021.6866 0004512 302.1660 156.7879 15.54064579062279
        0 ENVISAT
        1 27386U 02009A   17171.58727911 -.00000004 +00000-0 +12431-4 0  9994
        2 27386 098.2301 216.7243 0001096 086.9501 273.1814 14.37897545801560
        0 METOP-A
        1 29499U 06044A   17171.61998142 -.00000002 +00000-0 +18759-4 0  9991
        2 29499 098.6779 231.1827 0001777 129.8022 026.9623 14.21502538553441
        0 METOP-B
        1 38771U 12049A   17171.57781494 -.00000010 +00000-0 +15202-4 0  9990
        2 38771 098.6784 231.6932 0000980 147.6833 318.9176 14.21502060246766
        """.strip()

    p = Propagator(tles=tles)
    return p

######################################################
#
# CommsPass class
#
######################################################


def test_CommsPass_str(propagator):
    p1,x = propagator.compute_pass(29499, when='2017/08/07 10:00', dt=10.0)
    c2 = CommsPass(p1, desc= 'Test pass 2')
    c2.add_communication('DC-02-01-AF')
    c2.add_communication(bytearray('hello'))
    expected=\
"""Communication Pass:
  Norad ID:       29499
  Description:    Test pass 2
  Visib. horizon: 10
  Pass start:     2017/8/7 10:39:32
  Pass end:       2017/8/7 10:46:22
  Scheduled comms:
     0 ( 3 retries) : DC-02-01-AF
     1 ( 3 retries) : 68-65-6C-6C-6F
"""

    print("Expecting\n%s"%(expected))
    print("Got:\n%s")%(c2.__str__())
    assert(c2.__str__() == expected)


@pytest.fixture
def commspass(propagator):
    p1,x = propagator.compute_pass(29499, when='2017/08/07 10:00')
    c1 = CommsPass(p1, desc= 'Test pass 2')
    c1.add_communication('DC-02-01-AF', retries=2, wait = True)
    c1.add_communication('68-65-6C-6C-6F', retries=3, wait = False)
    return c1


def test_Commspass_dict_conversion(commspass):
    d = commspass.to_dict()
    c2 = CommsPass.from_dict(d)
    assert(commspass == c2)


def test_Commspass_json_conversion(commspass):
    j = commspass.to_json()
    c2 = CommsPass.from_json(j)
    assert(commspass == c2)


def create_overlapping(propagator, overlap ):
    p1,x = propagator.compute_pass(29499, when='2017/08/07 10:00', dt=10.0)
    c1 = CommsPass(p1, desc= 'Test pass 2')

    p1,x = propagator.compute_pass(29499, when='2017/08/07 10:00', dt=10.0)
    c2 = CommsPass(p1, desc= 'Test pass 3')

    new_time = pd.Timestamp(c1.pass_data.tstamp_str.iloc[-1]) + pd.Timedelta(seconds=overlap)

    c2._change_time(new_time)

    return c1,c2


@pytest.mark.parametrize("overlap", [
    -10, 0, 119.0])
def test_Commspass_overlap(propagator, overlap):
    c1, c2 = create_overlapping(propagator, overlap)
    assert( c1.overlaps(c2, buffertime=120.0) == True)

@pytest.mark.parametrize("overlap", [
    -10, 0, 119.0])
def test_Commspass_overlap_inverse(propagator, overlap):
    c1, c2 = create_overlapping(propagator, overlap)
    assert( c2.overlaps(c1, buffertime=120.0) == True)


def test_Commspass_no_overlap(propagator):
    c1, c2 = create_overlapping(propagator, 130.0)
    assert( c1.overlaps(c2, buffertime=120.0) == False)

def test_Commspass_no_overlap_inverse(propagator):
    c1, c2 = create_overlapping(propagator, 130.0)
    assert( c2.overlaps(c1, buffertime=120.0) == False)

######################################################
#
# Schedule class
#
######################################################

@pytest.fixture
def schedule(propagator):
    p1,x = propagator.compute_pass(25544, when='2017/08/07 10:00', dt=10.0)
    c1 = CommsPass(p1, desc='Test pass')
    c1.add_communication('DC-00-00-00-05-01-00-00-00-00-AF-ED')
    c1.add_communication('DC-00-00-00-13-01-00-00-00-00-CA-7A')
    c1.add_communication(bytearray(b"\xdc\x00\x00\x00\x05\x12\x00\x00\x00\x00\'\x07"))
    c1.add_communication('DC-00-07-00-01-05-00-00-00-00-FF-FF-FF-FF-05-00-00-1E-AD')

    p2,x = propagator.compute_pass(29499, when='2017/08/07 10:00', dt=10.0)
    c2 = CommsPass(p2, desc= 'Test pass 2')
    c2.add_communication('DC-00-00-00-13-01-00-00-00-00-CA-7A')

    p3,x = propagator.compute_pass(38771, when='2017/8/10 21:47:40', dt=10.0)
    c3 = CommsPass(p3, desc='test pass 3')
    c3.add_communication('DC-00-00-00-05-01-00-00-00-00-AF-ED')

    s = Schedule()
    s.add_pass(c1)
    s.add_pass(c2)
    s.add_pass(c3)

    return(s)


def test_Schedule(schedule):

        expected = \
"""Schedule of communication passes:
  ---- -------- -------------------- -------------------- --------------
  #    Norad id Pass start (utc)     Pass end (utc)       Communications
  ---- -------- -------------------- -------------------- --------------
  0000 29499    2017/8/7 10:39:32    2017/8/7 10:46:22    1
  0001 25544    2017/8/7 15:24:02    2017/8/7 15:27:02    4
  0002 38771    2017/8/10 21:51:01   2017/8/10 21:58:01   1
  ---- -------- -------------------- -------------------- --------------
"""
        print("Expected:\n%s\nGot:\n%s"%(expected, str(schedule) ))

        assert(str(schedule) == expected)



def test_Schedule_pop(schedule):
    schedule.pop_pass(1)
    expected=\
"""Schedule of communication passes:
  ---- -------- -------------------- -------------------- --------------
  #    Norad id Pass start (utc)     Pass end (utc)       Communications
  ---- -------- -------------------- -------------------- --------------
  0000 29499    2017/8/7 10:39:32    2017/8/7 10:46:22    1
  0001 38771    2017/8/10 21:51:01   2017/8/10 21:58:01   1
  ---- -------- -------------------- -------------------- --------------
"""
    assert(str(schedule) == expected)


def test_Schedule_remove(schedule):
    schedule.remove_pass(schedule.passes[1])
    expected=\
"""Schedule of communication passes:
  ---- -------- -------------------- -------------------- --------------
  #    Norad id Pass start (utc)     Pass end (utc)       Communications
  ---- -------- -------------------- -------------------- --------------
  0000 29499    2017/8/7 10:39:32    2017/8/7 10:46:22    1
  0001 38771    2017/8/10 21:51:01   2017/8/10 21:58:01   1
  ---- -------- -------------------- -------------------- --------------
"""
    assert(str(schedule) == expected)


def test_Schedule_json_conversion(schedule):
    j = schedule.to_json()
    s = Schedule.from_json(j)
    assert(schedule == s)


#
#def test_Schedule_dict_conversion(schedule):
#    d = commspass.to_dict()
#    c2 = CommsPass.from_dict(d)
#    assert(commspass == c2)
#
#
#def test_Schedule_json_conversion(schedule):
#    d = commspass.to_dict()
#    c2 = CommsPass.from_dict(d)
#    assert(commspass == c2)
