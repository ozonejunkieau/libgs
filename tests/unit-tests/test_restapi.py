# -*- coding: utf-8 -*-
"""
Created on Mon Jan 29 13:24:32 2018

@author: kjetil
"""

import sys
from os.path import dirname
import os
import pytest
import pandas as pd
from StringIO import StringIO

#_adfags_path = dirname(dirname(dirname(os.path.realpath(__file__)))) + '/src/adfagslib/'
#sys.path.insert(0, _adfags_path)
sys.path.insert(0, '../../src')


import logging
log = logging.getLogger('adfags-log')
from libgs.utils import setup_logger
setup_logger(log)

from libgs.database import CommsLog
import libgs.restapi
libgs.restapi.DEFAULT_TABLE_LIMIT=2
from libgs.restapi import RESTAPI
import requests


def create_commslog():
    DBNAME = 'test_restapi.db'
        
    try:
        os.remove(DBNAME)
    except:
        pass
    
    cl = CommsLog(db='sqlite:///%s'%(DBNAME))
    
    # add some entries to comms log
    cl.put(100000, 123456, "Sat", "GS", "Hello my friend")
    cl.put(100000, 123456, "GS", "Protocol", "Hello protocol")
    cl.put(200000, 123456, "Sat", "GS", "Another sat ID and pass ID")
    cl.put(200000, 123456, "Sat", "GS", "Same sat ID but another pass ID")
    cl.put(200000, 123456, "GS", "Sat", "And again")

    return cl
    
def start_api(cl):
    #global api
    ports_to_try = range(8080,8090)
    
    for p in ports_to_try:
        try:
            api = RESTAPI(cl, host='localhost', port=8080)
            api.start()
            print("Succesfully started api on port %d"%(p))
            return(p)
        except Exception, e:
            print("Failed to open api on port %d, trying another port: %s"%(p, e))
            
    
    raise Exception("Could not start API")
    
#
# Initialise teh api
#
COMMSLOG = create_commslog()
API_PORT = start_api(COMMSLOG)
    
def test_restapi_getcomms_default():
    resp = requests.get('http://localhost:%d/api/comms'%(API_PORT))
    resp.raise_for_status()
    
    table = pd.read_json(resp.content).sort_index(axis=1)
    comp_table = COMMSLOG.get().sort_index(axis=1)
    
    print(table.sort_index(axis=1))
    #print(comp_table)
    
    
    
#    requests.get('http://localhost:8080/)
    
    