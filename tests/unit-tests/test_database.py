# -*- coding: utf-8 -*-
"""
Created on Fri Jan 12 14:12:37 2018

@author: kjetil
"""

import sys
from os.path import dirname
import os
import pytest
import pandas as pd
from StringIO import StringIO

_libgs_path = dirname(dirname(dirname(os.path.realpath(__file__)))) + '/src/libgs/'
sys.path.insert(0, _libgs_path)

from database import CommsLog, PassDb, MonitorDb, KVDb
from scheduler import CommsPass, Action
from datetime import datetime

import pickle
import time
import shutil

#
# Asserts are in place for py.test to do its thing
# if running methods manually you can disable the asserts
# by setting _NO_ASSERTS = True
#
_NO_ASSERTS = False


#@pytest.fixture
#def pass_data():
#    csv = ',norad_id,tstamp_str,orbit_no,az,el,range,range_rate,altitude,lat,long,eclipsed\n42953.1394907,25544,2017/8/7 15:20:52,6975.990085135262,354.48157233837924,-0.01319284972355348,2373499.25,-5842.78076171875,407274.8125,-14.71053870793518,147.17231268793418,True\n42953.1396065,25544,2017/8/7 15:21:02,6975.991883821086,355.4584806349878,0.4245506316253881,2315375.25,-5781.18017578125,407449.34375,-15.206948319075245,147.56089581019452,True\n42953.1397222,25544,2017/8/7 15:21:12,6975.993682506909,356.48595965221114,0.8846125906844361,2257894.25,-5714.044921875,407625.9375,-15.702519524494688,147.95150066844923,True\n42953.139838,25544,2017/8/7 15:21:22,6975.995481192733,357.56758840917433,1.364703812680282,2201114.75,-5640.87841796875,407804.5,-16.197218173247666,148.34420922496827,True\n42953.1399537,25544,2017/8/7 15:21:32,6975.997279878557,358.7071371702993,1.8625513920840457,2145099.0,-5561.1376953125,407985.0,-16.69101352948291,148.73907612126504,True\n42953.1400694,25544,2017/8/7 15:21:42,6975.9990785643795,359.9086220868179,2.376082153039216,2089916.0,-5474.22998046875,408167.34375,-17.183871442254564,149.13621064036627,True\n42953.1401852,25544,2017/8/7 15:21:52,6976.000877250203,1.1763140686015192,2.90345877465906,2035640.625,-5379.509765625,408351.5,-17.675756053069495,149.5356674237853,True\n42953.1403009,25544,2017/8/7 15:22:02,6976.002675936026,2.5147712785704406,3.443037529231132,1982354.375,-5276.27880859375,408537.40625,-18.166636626076436,149.93752843379218,True\n42953.1404167,25544,2017/8/7 15:22:12,6976.00447462185,3.9287423129510826,3.993288027494526,1930146.125,-5163.78369140625,408725.0,-18.656475595234948,150.34187563265692,True\n42953.1405324,25544,2017/8/7 15:22:22,6976.006273307674,5.423194533539043,4.55268052051857,1879112.5,-5041.21826171875,408914.25,-19.145237102051887,150.7487909826496,True\n42953.1406481,25544,2017/8/7 15:22:32,6976.008071993498,7.003261894712643,5.119698065977287,1829358.375,-4907.72705078125,409105.0625,-19.632886995581412,151.1583701064186,True\n42953.1407639,25544,2017/8/7 15:22:42,6976.009870679321,8.674188274207161,5.6925780481779915,1780997.5,-4762.41162109375,409297.375,-20.119386002235785,151.57068130585557,True\n42953.1408796,25544,2017/8/7 15:22:52,6976.011669365144,10.441242736080438,6.269352945752895,1734152.875,-4604.3408203125,409491.125,-20.604698263521875,151.98580654323064,True\n42953.1409954,25544,2017/8/7 15:23:02,6976.013468050967,12.309612809007099,6.847732937782752,1688956.625,-4432.56787109375,409686.28125,-21.088786213399235,152.40384144119207,True\n42953.1411111,25544,2017/8/7 15:23:12,6976.015266736791,14.284265748061038,7.425028637281868,1645550.5,-4246.150390625,409882.75,-21.571608870732852,152.82486796201002,True\n42953.1412269,25544,2017/8/7 15:23:22,6976.017065422615,16.369762412060528,7.998080654872293,1604085.625,-4044.1806640625,410080.5,-22.053126961934993,153.24896806795445,True\n42953.1413426,25544,2017/8/7 15:23:32,6976.018864108438,18.570048089024898,8.563196846420807,1564721.625,-3825.821533203125,410279.40625,-22.533299505870644,153.6762510420521,True\n42953.1414583,25544,2017/8/7 15:23:42,6976.020662794262,20.88818868011784,9.116109197469802,1527626.375,-3590.352783203125,410479.46875,-23.012085521404785,154.10678518619466,True\n42953.1415741,25544,2017/8/7 15:23:52,6976.022461480085,23.326071025097566,9.651952052009289,1492973.625,-3337.2236328125,410680.5625,-23.489444027402392,154.54066612303058,True\n42953.1416898,25544,2017/8/7 15:24:02,6976.024260165908,25.884082737199474,10.165274065307951,1460942.0,-3066.1142578125,410882.65625,-23.96533062763386,154.97798947520815,True\n42953.1418056,25544,2017/8/7 15:24:12,6976.026058851732,28.560767278583068,10.650090284105564,1431711.5,-2776.99951171875,411085.65625,-24.439700925869584,155.4188508653758,True\n42953.1419213,25544,2017/8/7 15:24:22,6976.027857537556,31.35249440370447,11.099995698507952,1405461.0,-2470.2138671875,411289.53125,-24.912510525879966,155.86333225580353,True\n42953.142037,25544,2017/8/7 15:24:32,6976.029656223379,34.25316304608758,11.50832575143247,1382363.75,-2146.509765625,411494.1875,-25.38371503143539,156.3115429295181,True\n42953.1421528,25544,2017/8/7 15:24:42,6976.031454909203,37.25398958245976,11.868385149945215,1362583.25,-1807.1019287109375,411699.5625,-25.853264923664376,156.7635785091679,True\n42953.1422685,25544,2017/8/7 15:24:52,6976.0332535950265,40.34341733274534,12.173727903016989,1346268.375,-1453.691162109375,411905.5625,-26.321114098790034,157.21953461740128,True\n42953.1423843,25544,2017/8/7 15:25:02,6976.035052280849,43.50716095629525,12.418471510225118,1333548.875,-1088.4591064453125,412112.15625,-26.78721303794087,157.67952053724494,True\n42953.1425,25544,2017/8/7 15:25:12,6976.036850966673,46.72846941417002,12.597629933475492,1324529.875,-714.0286865234375,412319.25,-27.251512222245413,158.14361823096897,True\n42953.1426157,25544,2017/8/7 15:25:22,6976.038649652497,49.98852895030086,12.707414125326045,1319289.0,-333.3888244628906,412526.75,-27.71395871773759,158.61193698160008,True\n42953.1427315,25544,2017/8/7 15:25:32,6976.04044833832,53.26709488398785,12.745485599759695,1317872.0,50.21289825439453,412734.625,-28.17450471309321,159.0845724117866,True\n42953.1428472,25544,2017/8/7 15:25:42,6976.042247024144,56.54319853447906,12.711113526535252,1320291.75,433.40264892578125,412942.78125,-28.63309215170433,159.56164746493366,True\n42953.142963,25544,2017/8/7 15:25:52,6976.044045709967,59.79596342857632,12.605227665153484,1326527.375,812.82470703125,413151.125,-29.089669807152173,160.0432577636896,True\n42953.1430787,25544,2017/8/7 15:26:02,6976.0458443957905,63.00539418748444,12.430345794097185,1336524.875,1185.2845458984375,413359.625,-29.544181330376084,160.5294989307028,True\n42953.1431944,25544,2017/8/7 15:26:12,6976.047643081614,66.15307320610647,12.19040039478099,1350200.0,1547.875244140625,413568.1875,-29.99656524967354,161.0205075697567,True\n42953.1433102,25544,2017/8/7 15:26:22,6976.049441767437,69.22274463421779,11.89047568926833,1367440.875,1898.07861328125,413776.75,-30.44677033862576,161.51635198274292,True\n42953.1434259,25544,2017/8/7 15:26:32,6976.051240453261,72.20069345196501,11.536499427985126,1388113.125,2233.830078125,413985.21875,-30.894735125530215,162.01718243382328,True\n42953.1435417,25544,2017/8/7 15:26:42,6976.053039139085,75.07595720573026,11.134914186865995,1412063.875,2553.550537109375,414193.53125,-31.340394723589792,162.5230808852678,True\n42953.1436574,25544,2017/8/7 15:26:52,6976.054837824908,77.8403464986987,10.692366593747005,1439126.75,2856.14306640625,414401.625,-31.783691076196547,163.0341702804815,True\n42953.1437731,25544,2017/8/7 15:27:02,6976.056636510732,80.48830155688592,10.215439243440755,1469127.125,3140.963623046875,414609.375,-32.22455588145878,163.55055990249113,True\n42953.1438889,25544,2017/8/7 15:27:12,6976.058435196555,83.0166873234629,9.710432985456585,1501885.75,3407.77294921875,414816.78125,-32.66292766767395,164.07235903432343,True\n42953.1440046,25544,2017/8/7 15:27:22,6976.060233882378,85.42447243986497,9.183212390970592,1537222.625,3656.674560546875,415023.71875,-33.09874154804495,164.5997042797618,True\n42953.1441204,25544,2017/8/7 15:27:32,6976.062032568202,87.71239456652248,8.639106715082683,1574960.5,3888.051025390625,415230.125,-33.53192239049092,165.13267760107624,True\n42953.1442361,25544,2017/8/7 15:27:42,6976.063831254026,89.88261204321316,8.082862939266015,1614927.0,4102.49951171875,415435.90625,-33.96240872330931,165.67141560205016,True\n42953.1443519,25544,2017/8/7 15:27:52,6976.065629939849,91.9384101909278,7.518635526083248,1656956.375,4300.7734375,415641.03125,-34.39012199932468,166.21604122608863,True\n42953.1444676,25544,2017/8/7 15:28:02,6976.067428625673,93.88388712316836,6.950013739943223,1700891.125,4483.72998046875,415845.40625,-34.81499391664532,166.76665009584002,True\n42953.1445833,25544,2017/8/7 15:28:12,6976.069227311496,95.72370102894885,6.380065189556924,1746582.625,4652.28857421875,416048.9375,-35.23694934319037,167.32336515470942,True\n42953.1446991,25544,2017/8/7 15:28:22,6976.071025997319,97.46287892749837,5.811396018979534,1793891.75,4807.392578125,416251.59375,-35.65590973178436,167.88630934610188,True\n42953.1448148,25544,2017/8/7 15:28:32,6976.072824683143,99.10663908334281,5.246219209502135,1842688.5,4949.98779296875,416453.25,-36.07179995034644,168.45560561342245,True\n42953.1449306,25544,2017/8/7 15:28:42,6976.074623368966,100.66024757233225,4.6864297117325835,1892852.5,5080.99609375,416653.875,-36.48453803660656,169.03136323969784,True\n42953.1450463,25544,2017/8/7 15:28:52,6976.07642205479,102.12894314956009,4.133713728622227,1944272.375,5201.3056640625,416853.375,-36.89404202829467,169.61369150795477,True\n42953.145162,25544,2017/8/7 15:29:02,6976.078220740614,103.51781430595798,3.5895115763122907,1996845.5,5311.759765625,417051.65625,-37.300233378235326,170.20272702197667,True\n42953.1452778,25544,2017/8/7 15:29:12,6976.0800194264375,104.83179243810672,3.055258021415301,2050477.125,5413.150390625,417248.6875,-37.70302329396932,170.79856540441193,True\n42953.1453935,25544,2017/8/7 15:29:22,6976.08181811226,106.07559037653354,2.5323696878538016,2105080.5,5506.2177734375,417444.375,-38.10232639813202,171.4013432590439,True\n42953.1455093,25544,2017/8/7 15:29:32,6976.083616798084,107.25368189514485,2.022352845783191,2160575.75,5591.6455078125,417638.65625,-38.498053898264224,172.01114254814263,True\n42953.145625,25544,2017/8/7 15:29:42,6976.085415483907,108.37028805084769,1.5268804646632996,2216889.5,5670.0654296875,417831.46875,-38.89011700190671,172.62811353586986,True\n42953.1457407,25544,2017/8/7 15:29:52,6976.087214169731,109.42939767411738,1.0478478152670998,2273955.25,5742.05712890625,418022.71875,-39.2784200864111,173.252351844874,True\n42953.1458565,25544,2017/8/7 15:30:02,6976.089012855555,110.4347263878624,0.5873688945035637,2331710.75,5808.15185546875,418212.34375,-39.662870944223606,173.88395309780344,True\n42953.1459722,25544,2017/8/7 15:30:12,6976.090811541378,111.38975758855942,0.1476608057896611,2390099.75,5868.833984375,418400.28125,-40.04337395269585,174.52305389844153,True\n'
#
#    return pd.read_csv(StringIO(csv))
#    
#
#@pytest.fixture
#def comms_pass(pass_data):
#    cp  = CommsPass(pass_data)
#    cp.add_communication('DC-00-00-00-05-01-00-00-00-00-AF-ED')
#    cp.add_communication('DC-00-00-00-13-01-00-00-00-00-CA-7A')
#    cp.add_communication(Action('some_action', ('some_arg',), {'some_kwarg':23}))

def test_CommsLog():
    
    try:
        os.remove('test_CommsLog.db')
    except:
        pass
    
    cl = CommsLog(db='sqlite:///test_CommsLog.db')

    # a valid entry
    cl.put(100000, 123456, "Sat", "GS", "Hello my friend")
    
    # another valid entry
    cl.put(100000, 123456, "GS", "Protocol", "Hello protocol")

    # an invalid entry (?)
    with pytest.raises(Exception):
        cl.put(10000, 123456, "Invalid", "Sat", "This should raise an exception")


    # Get the full log
    df = cl.get()
    
    # try some other get queries
    return df


def test_MonitorDb():
    try:
        os.remove('test_MonitorDb.db')
    except:
        pass    
    
    db = MonitorDb(db='sqlite:///test_MonitorDb.db')
    
    pass_id = 1234
    db.put(pass_id, 'telem_val1_int', int(1))
    db.put(pass_id, 'telem_val2_float', float(3.14), 'RED')
    db.put(pass_id, 'telem_val3_string', 'a string')
    db.put(pass_id, 'telem_val4_list', [1, 2, 3, 4])
    db.put(2222, ['a', 'b', 'c', 'd', 'e'], [12, 'a', dict(a=2,b='a'), 12.23, 1])
    
    df = db.get()
    return df
    


def test_PassDb():
    try:
        os.remove('test_PassDb.db')
    except:
        pass    
    
    try:
        shutil.rmtree('test_PassDb_disk')
    except:
        pass    
    
    os.mkdir('test_PassDb_disk')
    os.mkdir('test_PassDb_disk/passes')
    
    db = PassDb(db='sqlite:///test_PassDb.db', disk_threshold=50, disk_path='./test_PassDb_disk/', get_from_disk=True)
    
    pass_id = 1234
    module  = 'groundstation'
    db.put(module,pass_id, 'telem_val1_int', int(1))
    db.put(module,pass_id, 'telem_val2_float', float(3.14))
    db.put(module,pass_id, 'telem_val3_string', 'a string')
    db.put(module,pass_id, 'telem_val4_list', [1, 2, 3, 4])
    db.put(module, pass_id, 'datetime_test', pd.to_datetime('2018-01-01 10:00:01').to_pydatetime())
    db.put(module, pass_id, 'Timestamp_test', pd.to_datetime('2018-01-01 10:00:01').to_pydatetime())
    db.put('scheduler', 2222, ['a', 'b', 'c', 'd', 'e'], [12, 'a', dict(a=2,b='a'), 12.23, 1])
    db.put('other', 1234, 'data',bytearray([1,2,3,4,5,6,7,8,9,0,0,0,0,0,1]))
    db.put("other", 1234, 'disk_bytes', bytearray([0]*60))
    db.put("other", 1234, 'disk_string', "Hello -"*10)

    df = db.get()        

    return df



@pytest.mark.parametrize("get_from_disk", [True, False])
def test_KVDb_save_to_disk(get_from_disk):

    try:
        os.remove('test_KVDb_disk.db')
    except:
        pass    
    
    try:
        shutil.rmtree('test_KVdb_disk')
    except:
        pass
    
    os.mkdir('test_KVdb_disk')
    
    db = KVDb(table='test1', db='sqlite:///test_KVDb_disk.db', 
              disk_threshold = 10, disk_path = './test_KVdb_disk/', get_from_disk = get_from_disk)    

    db.put('long key will be stored to disk', int(1)) #<-- this will encode the key
    time.sleep(0.01)
    db.put('int', int(1))
    time.sleep(0.01)
    db.put('barray', bytearray([1,2,3,4,5,6,7,8,9,0,0,0,0,0,1])) #<--- should save to disk with .bin ext
    time.sleep(0.01)
    db.put('str', "a string that should be saved") #<-- should save to disk with .txt extension
    time.sleep(0.01)
    db.put('str2', 'string') #<-- should not save

    df = db.get()
    
    if not _NO_ASSERTS: 
        if get_from_disk:
            truth = pickle.loads("ccopy_reg\n_reconstructor\np0\n(cpandas.core.frame\nDataFrame\np1\nc__builtin__\nobject\np2\nNtp3\nRp4\n(dp5\nS'_metadata'\np6\n(lp7\nsS'_typ'\np8\nS'dataframe'\np9\nsS'_data'\np10\ng0\n(cpandas.core.internals\nBlockManager\np11\ng2\nNtp12\nRp13\n((lp14\ncpandas.core.indexes.base\n_new_Index\np15\n(cpandas.core.indexes.base\nIndex\np16\n(dp17\nS'data'\np18\ncnumpy.core.multiarray\n_reconstruct\np19\n(cnumpy\nndarray\np20\n(I0\ntp21\nS'b'\np22\ntp23\nRp24\n(I1\n(I3\ntp25\ncnumpy\ndtype\np26\n(S'O8'\np27\nI0\nI1\ntp28\nRp29\n(I3\nS'|'\np30\nNNNI-1\nI-1\nI63\ntp31\nbI00\n(lp32\nVtstamp\np33\naVkey\np34\naVvalue\np35\natp36\nbsS'name'\np37\nNstp38\nRp39\nag15\n(cpandas.core.indexes.range\nRangeIndex\np40\n(dp41\nS'start'\np42\nI0\nsS'step'\np43\nI1\nsS'stop'\np44\nI5\nsg37\nNstp45\nRp46\na(lp47\ng19\n(g20\n(I0\ntp48\ng22\ntp49\nRp50\n(I1\n(I1\nI5\ntp51\ng26\n(S'M8'\np52\nI0\nI1\ntp53\nRp54\n(I4\nS'<'\np55\nNNNI-1\nI-1\nI0\n((dp56\n(S'ns'\np57\nI1\nI1\nI1\ntp58\ntp59\ntp60\nbI00\nS'\\x00$|\\xaf5\\xd64\\x15\\x00l/\\xa55\\xd64\\x15\\x00\\x10\\t\\xa05\\xd64\\x15\\x00\\xb4\\xe2\\x9a5\\xd64\\x15\\x00\\xfc\\x95\\x905\\xd64\\x15'\np61\ntp62\nbag19\n(g20\n(I0\ntp63\ng22\ntp64\nRp65\n(I1\n(I2\nI5\ntp66\ng29\nI00\n(lp67\nVstr2\np68\naVstr\np69\naVbarray\np70\naVint\np71\naS'long key will be stored to disk'\np72\naVstring\np73\naVa string that should be saved\np74\nac__builtin__\nbytearray\np75\n(V\x01\x02\x03\x04\x05\x06\x07\x08\t\x00\x00\x00\x00\x00\x01\np76\nS'latin-1'\np77\ntp78\nRp79\naI1\naI1\natp80\nba(lp81\ng15\n(g16\n(dp82\ng18\ng19\n(g20\n(I0\ntp83\ng22\ntp84\nRp85\n(I1\n(I1\ntp86\ng29\nI00\n(lp87\ng33\natp88\nbsg37\nNstp89\nRp90\nag15\n(g16\n(dp91\ng18\ng19\n(g20\n(I0\ntp92\ng22\ntp93\nRp94\n(I1\n(I2\ntp95\ng29\nI00\n(lp96\ng34\nag35\natp97\nbsg37\nNstp98\nRp99\na(dp100\nS'0.14.1'\np101\n(dp102\nS'axes'\np103\ng14\nsS'blocks'\np104\n(lp105\n(dp106\nS'mgr_locs'\np107\nc__builtin__\nslice\np108\n(I0\nI1\nI1\ntp109\nRp110\nsS'values'\np111\ng50\nsa(dp112\ng107\ng108\n(I1\nI3\nI1\ntp113\nRp114\nsg111\ng65\nsasstp115\nbsb.")
            assert df[['key', 'value']].equals(truth[['key', 'value']])
            print("Test OK")
        else:
            # cant do an assert here because the input will be different (some things are saved to file), so just check that it runs without
            # crashing

            print("Test OK")
    
    
    return df    


def test_KVDb():
    try:
        os.remove('test_KVDb.db')
    except:
        pass


    db = KVDb(table='test', db='sqlite:///test_KVDb.db', disk_threshold = None)


    kvs = [
        ('telem_val1_int', int(1)),
        ('telem_val2_float', float(3.14)),
        ('telem_val3_string', 'a string'),
        ('telem_val4_list', [1, 2, 3, 4]),
        ('datetime_test', pd.to_datetime('2018-01-01 10:00:01').to_pydatetime()),
        ('Timestamp_test', pd.to_datetime('2018-01-01 10:00:01').to_pydatetime()),
        (['a', 'b', 'c', 'd', 'e'], [18, 'a', dict(a=2, b='a'), 12.23, 1]),
        ('data', bytearray([1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 0, 0, 0, 0, 1]))]

    for k,v in kvs:
        db.put(k,v)
        time.sleep(.01)
    #
    # db.put('telem_val1_int', int(1))
    # time.sleep(0.01)
    # db.put('telem_val2_float', float(3.14))
    # time.sleep(0.01)
    # db.put('telem_val3_string', 'a string')
    # time.sleep(0.01)
    # db.put('telem_val4_list', [1, 2, 3, 4])
    # time.sleep(0.01)
    # db.put('datetime_test', pd.to_datetime('2018-01-01 10:00:01').to_pydatetime())
    # time.sleep(0.01)
    # db.put('Timestamp_test', pd.to_datetime('2018-01-01 10:00:01').to_pydatetime())
    # time.sleep(0.01)
    # db.put(['a', 'b', 'c', 'd', 'e'], [18, 'a', dict(a=2,b='a'), 12.23, 1])
    # time.sleep(0.01)
    # db.put('data',bytearray([1,2,3,4,5,6,7,8,9,0,0,0,0,0,1]))

    df = db.get()
    
    if not _NO_ASSERTS:
        truth = pickle.loads("ccopy_reg\n_reconstructor\np0\n(cpandas.core.frame\nDataFrame\np1\nc__builtin__\nobject\np2\nNtp3\nRp4\n(dp5\nS'_metadata'\np6\n(lp7\nsS'_typ'\np8\nS'dataframe'\np9\nsS'_data'\np10\ng0\n(cpandas.core.internals\nBlockManager\np11\ng2\nNtp12\nRp13\n((lp14\ncpandas.core.indexes.base\n_new_Index\np15\n(cpandas.core.indexes.base\nIndex\np16\n(dp17\nS'data'\np18\ncnumpy.core.multiarray\n_reconstruct\np19\n(cnumpy\nndarray\np20\n(I0\ntp21\nS'b'\np22\ntp23\nRp24\n(I1\n(I4\ntp25\ncnumpy\ndtype\np26\n(S'O8'\np27\nI0\nI1\ntp28\nRp29\n(I3\nS'|'\np30\nNNNI-1\nI-1\nI63\ntp31\nbI00\n(lp32\nVid\np33\naVtstamp\np34\naVkey\np35\naVvalue\np36\natp37\nbsS'name'\np38\nNstp39\nRp40\nag15\n(cpandas.core.indexes.range\nRangeIndex\np41\n(dp42\nS'start'\np43\nI0\nsS'step'\np44\nI1\nsS'stop'\np45\nI12\nsg38\nNstp46\nRp47\na(lp48\ng19\n(g20\n(I0\ntp49\ng22\ntp50\nRp51\n(I1\n(I1\nI12\ntp52\ng26\n(S'f8'\np53\nI0\nI1\ntp54\nRp55\n(I3\nS'<'\np56\nNNNI-1\nI-1\nI0\ntp57\nbI00\nS'7\\xf6s\\xeai\\xc1BA\\xf7\\xf3s\\xeai\\xc1BA\\xf7\\xf3s\\xeai\\xc1BA\\xf7\\xf3s\\xeai\\xc1BA\\xf7\\xf3s\\xeai\\xc1BA\\xf7\\xf3s\\xeai\\xc1BA\\x1c\\xf2s\\xeai\\xc1BA-\\xf0s\\xeai\\xc1BAF\\xees\\xeai\\xc1BA\\x1d\\xecs\\xeai\\xc1BA\\xcc\\xe9s\\xeai\\xc1BA\\xb6\\xe7s\\xeai\\xc1BA'\np58\ntp59\nbag19\n(g20\n(I0\ntp60\ng22\ntp61\nRp62\n(I1\n(I1\nI12\ntp63\ng26\n(S'i8'\np64\nI0\nI1\ntp65\nRp66\n(I3\nS'<'\np67\nNNNI-1\nI-1\nI0\ntp68\nbI00\nS'\\x0c\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x07\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x08\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\t\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\n\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x0b\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x06\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x05\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x04\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x03\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x02\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00'\np69\ntp70\nbag19\n(g20\n(I0\ntp71\ng22\ntp72\nRp73\n(I1\n(I2\nI12\ntp74\ng29\nI00\n(lp75\nVdata\np76\naVa\np77\naVb\np78\naVc\np79\naVd\np80\naVe\np81\naVTimestamp_test\np82\naVdatetime_test\np83\naVtelem_val4_list\np84\naVtelem_val3_string\np85\naVtelem_val2_float\np86\naVtelem_val1_int\np87\nac__builtin__\nbytearray\np88\n(V\x01\x02\x03\x04\x05\x06\x07\x08\t\x00\x00\x00\x00\x00\x01\np89\nS'latin-1'\np90\ntp91\nRp92\naI18\naVa\np93\na(dp94\ng93\nI2\nsVb\np95\ng93\nsaF12.23\naI1\nacpandas._libs.tslib\nTimestamp\np96\n(I1514800801000000000\nNNtp97\nRp98\nag96\n(I1514800801000000000\nNNtp99\nRp100\na(lp101\nI1\naI2\naI3\naI4\naaVa string\np102\naF3.14\naI1\natp103\nba(lp104\ng15\n(g16\n(dp105\ng18\ng19\n(g20\n(I0\ntp106\ng22\ntp107\nRp108\n(I1\n(I1\ntp109\ng29\nI00\n(lp110\ng34\natp111\nbsg38\nNstp112\nRp113\nag15\n(g16\n(dp114\ng18\ng19\n(g20\n(I0\ntp115\ng22\ntp116\nRp117\n(I1\n(I1\ntp118\ng29\nI00\n(lp119\ng33\natp120\nbsg38\nNstp121\nRp122\nag15\n(g16\n(dp123\ng18\ng19\n(g20\n(I0\ntp124\ng22\ntp125\nRp126\n(I1\n(I2\ntp127\ng29\nI00\n(lp128\ng35\nag36\natp129\nbsg38\nNstp130\nRp131\na(dp132\nS'0.14.1'\np133\n(dp134\nS'axes'\np135\ng14\nsS'blocks'\np136\n(lp137\n(dp138\nS'mgr_locs'\np139\nc__builtin__\nslice\np140\n(I1\nI2\nI1\ntp141\nRp142\nsS'values'\np143\ng51\nsa(dp144\ng139\ng140\n(I0\nI1\nI1\ntp145\nRp146\nsg143\ng62\nsa(dp147\ng139\ng140\n(I2\nI4\nI1\ntp148\nRp149\nsg143\ng73\nsasstp150\nbsb.")
        assert df[['key', 'value']].sort_values('key').equals(truth[['key', 'value']].sort_values('key'))
        print("Test ok")


    return df


#def test_KVDb_invalid_data():
#    #TODO 
#    return


import ephem
from libgs.database import Database

@pytest.mark.parametrize("binary_fmt", ['hex', 'b64'])
def test_encoding(binary_fmt):
    try:
        os.remove('test_encoding.db')
    except:
        pass


    db = Database(db='sqlite:///test_encoding.db', disk_threshold = None, binary_fmt=binary_fmt)

    ts = datetime(year=2018, month=5, day=1, hour=10, minute=20, second=30, microsecond=123000) #<--- microseconds are not saved atm so not having them set to zero will make test fail.

    blah1 = ['datetime', 'pandas Timestamp', 'ephem.Date', 'Just a string', 'bytearray']
    blah2 = [ts, pd.to_datetime(ts), ephem.Date(ts), 'hello', bytearray([1,2,3,4,5,6,7,8])] #<-- all of these will be encoded as strings
    db.put_df(table='test', df = pd.DataFrame(dict(blah1=blah1, blah2=blah2)))
    df = db.get_df(table='test')

    if not _NO_ASSERTS:
        for k in range(len(blah1)):
            assert(blah1[k] == df.blah1.iloc[k])
            assert(blah2[k] == df.blah2.iloc[k])

    print(df)

    return df



import json
def test_KVDb_ncols():

    try:
        os.remove('test_KVDb.db')
    except:
        pass    
    
    db = KVDb(table='test1', db='sqlite:///test_KVDb.db',ncols=['ncol1', 'ncol2', 'ncol3'])    

    db.put('telem_val1_int', int(1), ncol1='a', ncol2=2)
    db.put('telem_val2_float', float(3.14), ncol3=json.dumps([1,2,3,4]))
    db.put('telem_val3_string', 'a string')
    db.put('telem_val4_list', [1, 2, 3, 4], ncol1='b',ncol2=3, ncol3='howdy')
    db.put(['a', 'b', 'c', 'd', 'e'], [12, 'a', dict(a=2,b='a'), 12.23, 1])

    df = db.get()

    print(df)
    return df
    
  

if __name__ == '__main__':
    import logging
    from utils import setup_logger
    log = logging.getLogger('adfags-log')
    setup_logger(log, cons_loglvl = logging.DEBUG)
    #test_CommsLog()
    #test_MonitorDb()
    test_KVDb()
    #test_encoding()
