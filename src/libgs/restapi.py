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

REST API interface
-------------------


This API currently only allows access to download data from the telemetry
database. It could be extended to provide more full control of the ground station
if necessary.

.. todo:: authentication

@author: kjetil
"""

from flask import Flask, current_app, request, g, redirect
from threading import Thread, Event
from utils import Defaults, hex2bytes, bytes2hex, conv_time
from database import TSTAMP_LBL
# from pandas import to_datetime
# from urllib import unquote
from utils import XMLRPCTimeoutServerProxy, wait_loop
import json
from base64 import b64encode, encodestring
import sys
import logging
ags_log = logging.getLogger('libgs-log')
ags_log.addHandler(logging.NullHandler())

app = Flask(__name__)
app.use_reloader = False


#
# DEBUG mode. Will show more explicit exceptions if enabled
#
DEBUG = Defaults.RESTAPI_DEBUG_MODE

#
# Limit returned table sizes by default to prevent overloading the processor
# trying to fetch an entire giant table. The user will  have to
# add N= specifically to request larger tables.
#
DEFAULT_TABLE_LIMIT = Defaults.RESTAPI_TABLE_LIMIT

#
# This  module allows the user to assign RPC apis to any endpoint
# In order to avoid conflict with the internally implemented endpoints
# below, it checks PROTECTED_ENDPOINTS and raises an exception if
# the user tries to use one of those. Must be updated if a new endpoint
# is added in this module
#
#
_PROTECTED_ENDPOINTS = ['mon', 'comms', 'passes']

#
# The timestamp label is special in the way it is handled in the database. It can be remapped
# to other names using the below constant.
#
_RETURNED_TSTAMP_LBL = 'tstamp'

#
# Default table styles applied to pd.style
#
_TABLE_ATTRIBUTES='style="border-collapse:collapse"'
_TABLE_STYLES = [
    dict(selector="tr:nth-child(even)", props=[("background-color", "whitesmoke")]),
    dict(selector="tr:hover", props=[("background-color", "lightyellow")]),
    dict(selector="th", props=[("text-align", "left"),
                               ("position", "sticky"),
                               ("top", "0"),
                               ("left", "0"),
                               ("background-color", "#e2e2e2"),
                               ("color", "#565656"),
                               # ('border-bottom' '"1px solid #ddd"')
                               ]),
                               #("border-color", "#c1bece")]),
    dict(selector="td", props=[("padding", "5px"),
                               #('border-bottom' '"1px solid #ddd"'),
                               ('overflow','hidden'),
                               ('text-overflow','ellipsis'),
                               ('white-space', 'nowrap'),
                               ('max-width', '800px'),
                               ('color', '#565656'),
                               ('border-left', '2px solid white'),
                               ('border-right', '2px solid white')
                               ])
]


#
# Template to apply when returning html pages.
#
_PAGE_TEMPLATE =  """<!DOCTYPE html>
    <html>
    <head>      
    <style>
        body {
            display: flex;
	        flex-direction: column;          
	        height:100vh;
	        //width:100%;  
            margin-top: 0px; 
            margin-bottom: 0px; 
            margin-left: 5px; 
            margin-right: 5px;
            padding: 0;
            }
            
        pre {
         width: 90%;
         background: #e2e2e2;
         border: 2px solid #565656;
         border-radius:5px;   
         overflow:scroll;
         padding: 1em;        
        }


        .content {
          flex: 1 1 auto;
          width: 100%;
          min-width: 400px;
          overflow: scroll; #<--- makes table sticky not work for some reason
        }
        
        .main-header {
          flex: 0 0 auto;
          width:100%;
          background:#e2e2e2;
          color: #565656;
          margin-top: 0;
          margin-bottom: 0;
          margin-right: 0;
          margin-left: 0;            
          
        }
        
        
        .helptext-overlay {
            position: fixed;
             width: 80vw; /*optional*/
             height: 80vh;
              margin-top: 10vh;
              margin-bottom: 10vh;
              margin-right: 10vw;
              margin-left: 10vw;            
             visibility:hidden;  
        }
        
        .helptext {
             background: whitesmoke;//#e2e2e2;   
             color: #565656;
             border: 5px solid #565656;
             border-radius:10px;   

        }

        .footer {
          flex: 0 0 auto;
          background-color: blue;
          width: 100%;
          height:100px;
        }      
        
         a {
           color: #617bcc;
           // font-family: helvetica; 
           text-decoration: none;
           
         } 
        
         a:hover {
           text-decoration: underline;
         }
        
         a:active {
           color: black;
         }
        
         a:visited {
           color: ;
         }         
         
         a.tablelink:visited {
            color: #565656;
         }          
        
        .button  {
           background-color: whitesmoke;
           border: none;
           color: #565656;
           padding:2px 4px;// 16px 32px;
           text-align: center;
           font-size: 16px;
           margin: 4px 2px;
           opacity: 1;
           transition: 0.3s;
           display: inline-block;
           text-decoration: none;
           cursor: pointer;
         }

         .button:hover {opacity: 0.2;}# text-decoration: underline;}
         

        
    </style>


        <meta charset="UTF-8">
        <title>##TITLE##</title>
    </head>

    <body>
        <div class="main-header">
            <div style="font-size: 50px;">        
            ##TITLE##
            </div>
            <div>
                ##BUTTONS##
            </div>
        </div>
        ##ERROR_MSG##

        <div class="content">        
        ##MAIN##
        </div>
             
    ##HELPTEXTS##                

    </body>
    </html>
"""



#
# Help texts
#

def _format_argument_table(urlargs, qargs, examples):

    html = '<table style="padding:1px;">'
    FIRST_COLUMN_W = '15em'

    if len(urlargs) > 0:
        html += '<tr><th style="text-align:left;width:{};vertical-align: top;"> URL Arguments </th></tr>\n'.format(FIRST_COLUMN_W)
        for k,v in urlargs:
            html += '<tr><td style="font-style:italic;vertical-align: top;">{}</td><td style="vertical-align: top;">{}</td></tr>\n'.format(k,v)

    if len(qargs) > 0:
        html += '<tr><th style="text-align:left;vertical-align: top;"> Query Arguments</th></tr>\n'
        for k,v in qargs:
            html += '<tr><td style="font-style:italic;vertical-align: top;">{}</td><td style="vertical-align: top;">{}</td></tr>\n'.format(k,v)

    if len(examples) > 0:
        html += '<tr><th style="text-align:left;vertical-align: top;"> Examples </th></tr>\n'
        for k,v in examples:
            html += '<tr><td style="word-wrap:break-word;vertical-align: top;"><a href="{}">{}</a></td><td style="vertical-align: top;">{}</td></tr>\n'.format(k,k,v)

    html += '</table>'

    return html

_HELP_COMMS = """<h3> Comms DB API </h3>
Syntax: <pre> /api/comms/[pass id]?[format=html,json,csv][&N=N][&tstamp=tstamp filter][&dest=dest][&orig=orig][&nid=nid]</pre>
<br/>
{}
""".format(_format_argument_table(
    [('pass_id', 'The pass ID')],
    [('format',  'Format to return data in. Valid values are html, json and csv'),
     ('tstamp',  'Comma-separated list of timestamp filters. Each filter consists of a comparator + a timestamp. eg. ">2018-12-01T02:12:00"'),
     ('nid, orig and dest', 'Filter by columns norad_id, orig or dest')],
    [('/api/comms?format=html', 'Get all communications (N is limited by default, increase explicitly to get more values)'),
     ('/api/comms?format=html&N=1000', 'Get all communications up to max 1000 rows')]
))

_HELP_MON = """<h3> Monitor DB API </h3>
Syntax: <pre> /api/mon[/pass id]?[format=html,htmlraw,json,csv][&N=N]&[keys=keypattern,keypattern,...]</pre>
{}
""".format(_format_argument_table(
    [('pass_id', 'The pass ID')],
    [('format',  'Format to return data in. Valid values are html, htmlraw, json and csv<br/>Format "html" attempts to pivot the results on timestamp'),
     ('tstamp',  'Comma-separated list of timestamp filters. Each filter consists of a comparator + a timestamp. eg. ">2018-12-01T02:12:00"'),
     ('keys',    'Comma-separated list of keypattern filters. Can be the name of a key, or use the wildchar %. <br/>E.g. %Temp% matches anything with Temp in it. Careful to URL encode: % == %25')],
    [('/api/mon?format=htmlraw', 'Get all monitoring data - unpivoted (N limited by default, set N=explicitly to increase)'),
     ('/api/mon/20180831135300?format=htmlraw', 'Get all monitoring data for pass 20180831135300'),
     ('/api/mon?keys=%RACK%,%5V%&format=htmlraw', 'Get all RACK and 5V telemetry points, pivoted')]
))


_HELP_PASSES = """<h3> Passes DB API </h3>
Syntax: <pre> /api/passes[/pass_id]?[format=html,htmlraw,json,csv][&N=N]</pre>
{}
""".format(_format_argument_table(
    [('pass_id', 'The pass ID')],
    [('format',  'Format to return data in. Valid values are html, htmlraw, json and csv<br/>Format "html" attempts to pivot the results on pass_id'),
     ('tstamp',  'Comma-separated list of timestamp filters. Each filter consists of a comparator + a timestamp. eg. ">2018-12-01T02:12:00"')],
    [('/api/mon?format=htmlraw', 'Get all monitoring data - unpivoted (N limited by default, set N=explicitly to increase)')]
))


_HELP_RPC =  """
        <h3> Auto-APIs (generated from XMLRPC APIs) </h3>
        
        Syntax: <pre>/api/[endpoint]/[method]/[pos_arg_1/pos_arg_2/...]?[key1=val1][&key2=val2][&...]</pre>    
        
        <br/>
        The Auto-API can map any XMLRPC API that advertises its methods (in python, use register_introspection_functions
        to acheive this in your xmlrpc API). The APIs are specified on the command-line to libgs-restapi. For help:
        <br/>
        <pre> $libgs-restapi --help </pre>
        <br/>
    """

_HELP_FILES = """
    <h3> File retrieval API </h3>    
    Syntax: <pre> /api/file/[dbname]/[fname]</pre>
    <br/>
    The file retrieval API can be used to retrieve data that has been stored in the filesystem with only a file:// reference
    in the database.    

    {}
""".format(_format_argument_table(
    [('dbname', 'The database the file is referred to from; mon, comms, or passes'),
     ('fname',  'The file reference')],
    [],
    [('/api/file/passes/20181212062954_FJPYwGtd.txt', 'Get the textual datafile referred to from the passes database'),
     ('/api/file/passes/20181212054731_z0Ag3wjY.bin', 'Get the binary datafile referred to from the passes database')]
))

class RESTAPI(object):
    """
    THE REST API class
    ------------------

    Will create a RESTFUL API interface to the Commslog database and start
    it on a specified port. The api will be started in a separate thread.

    The URI endpoints are:

    /api/comms
      Download the entire communications log

    /api/comms/<pass_id>
      Download a specific pass

    Valid parameters are:

    ======== =============================================
    format   output format: json / csv / html
    N        max number of entries to return. Omit for all
    ======== =============================================

    Usage:
      >>> api = RESTAPI()
      >>> api.start()



    """

    def __init__(self,
                 commslog = None,
                 monlog = None,
                 passdb = None,
                 host=Defaults.API_ADDR,
                 port=Defaults.API_PORT,
                 default_format='json',
                 rpcapi = None,
                 allowed=None,
                 retry_rpc_conn = True,
                 debug=True):
        """
        Args:
          commslog (CommsLog)     : Database end-point for comms log
          host     (str)          : Ip address to bind to
          port     (int)          : Port to bind to
          default_format (str)    : Format to provide if no argument given (default = json)
          allowed  (list(str))    : LIst of allowed URI patterns. Default is None, which actually means all
          debug    (bool)         : Set flask in Debug mode for extra verbosity


        """
        self.commslog = commslog #<--- comms db
        self.monlog   = monlog   #<--- monitoring db
        self.passdb   = passdb   #<--- pass db
        self.rpcapi = {}
        self._debug = debug
        self._host = host
        self._port = port
        self._default_format = default_format
        self._abort_event = Event()

        if allowed is not None and not isinstance(allowed, list):
            raise Exception("Invalid type for allowed, expected list, got %s"%(type(allowed)))

        self._allowed = allowed
        _rpcapi = {} if rpcapi is None else rpcapi
        self._rpc_unavailable = {}

        for uri,rpcaddr in _rpcapi.items():
            if uri.split('/')[0] in _PROTECTED_ENDPOINTS:
                raise Exception("{} is a protected endpoint and cannot be used as an rpcapi endpoint".format(uri))
            if uri[-1] == '/':
                uri = uri[:-1]

            try:
                self._try_rpc_connection(uri, rpcaddr)
            except Exception as e:
                self._rpc_unavailable[uri] = rpcaddr
                ags_log.error(
                    "Could not bind to RPC API {}. API not started: ({}: {})".format(uri, e.__class__.__name__, e))

        if retry_rpc_conn:
            self._pthr_connpoll = Thread(target=self._poll_for_rpcconnection)
            self._pthr_connpoll.daemon = True
            self._pthr_connpoll.start()



    def _try_rpc_connection(self, uri, rpcaddr):
        a = dict(addr=uri, server=XMLRPCTimeoutServerProxy(rpcaddr, allow_none=True))

        try:
            # get method from xmlrpc introspection but exclude anything with a . (system methods)
            a['methods'] = [m for m in a['server'].system.listMethods() if m.find('.') < 0]
            ags_log.debug("Bound to RPC API {}. Available methods: {}".format(a['addr'], a['methods']))
            self.rpcapi[uri] = a
        except Exception as e:
            raise



    def _poll_for_rpcconnection(self):

        # try to connect to api every minute
        while len(self._rpc_unavailable) > 0:
            _unavailable = {}
            sys.stdout.flush()
            for uri, rpcaddr in self._rpc_unavailable.items():
                try:
                    self._try_rpc_connection(uri, rpcaddr)
                except Exception as e:
                    _unavailable[uri] = rpcaddr

            self._rpc_unavailable= _unavailable
            if wait_loop(self._abort_event, timeout=60) is not None:
                break


    def _run_api(self):
        with app.app_context():
            current_app.config['API'] = self

        app.run(host=self._host, port=self._port, debug=self._debug, use_reloader=False)

    def start(self):
        self._pthr = Thread(target=self._run_api)
        self._pthr.daemon = True
        self._pthr.start()

        ags_log.info("Started REST API on %s:%d in thread %s"%(self._host, self._port, self._pthr))


    def stop(self):
        pass



# Just a helper funciton used a few places below
def nid_to_int_if_possible(nid):
    try:
        return int(nid)
    except:
        return nid



def handle_bytes(d, format):
    if not isinstance(d, bytearray):
        return d
        
    if format == 'hex':
        return bytes2hex(d)
    elif format == 'b64':
        return b64encode(d)
    elif format == 'b64string':
        return encodestring(d)
    else:
        raise Exception("Invalid format")

def is_allowed(fn):
    """
    This decorator checks if a resource is allowed
    """
    def wrapped(*args, **argv):
        api = current_app.config['API']
        #
        # Check if resource is allowed
        #
        allowed = False
        if api._allowed is not None:
            for c in api._allowed:
                if c == request.path[:len(c)]:
                    allowed = True
                    break

            if not allowed:
                return "Restricted resource", 403

        return fn(*args, **argv)

    wrapped.__name__ = fn.__name__
    return wrapped



def _style_html_page(ret, title, cur_format, cur_page="", helptexts=True, err_msg=""):
    """
    A helper function to format and style HTML pages
    """

    #url_root=request.url_root
    url_root='/' #<--- need to find a way to make this always work regardless of rproxies etc ... somehow. But its hard

    header_buttons = ""
    if cur_format in ('htmlraw', 'html'):
        for f, fstr in [('htmlraw', ' RAW '), ('html', ' PIVOTED ')]:
            argstr = "&".join(["{}={}".format(k,v) for k,v in request.args.items() if k != 'format'])
            if len(argstr) > 0:
                argstr = "&" + argstr

            if cur_format.lower() == f:
                header_buttons += '<span class="button" style="opacity: 0.2;">{}</span>'.format(fstr)
            else:
                header_buttons += '<a href="{}?format={}{}" class="button">{}</a>'.format(request.path, f, argstr, fstr)


    # Add in forms for filters
    if cur_page != "help":
        header_buttons += """
                    <span style="display:inline-block;"><a href="#" onclick="document.getElementById('_helptext_{}').style.visibility = 'visible';event.preventDefault();">Key filters</a>:
                    <form action="{}" method="get" style="display: inline;" >
                        <input style="display: inline; width:100px" type="input" name="keys"/>
                        {}
                        <input style="display: inline;" type="submit" class="button" value="go"/>
                    </form></span>
        """.format(cur_page, cur_page, ''.join(['<input type="hidden" name="{}" value="{}"/>'.format(k,v) for k,v in request.args.items() if k != 'keys']))

        header_buttons += """
                    <span style="display:inline-block;"><a href="#" onclick="document.getElementById('_helptext_{}').style.visibility = 'visible';event.preventDefault();">Timestamp filters</a>:
                    <form action="{}" method="get" style="display: inline;" >
                        <input style="display: inline; width:100px" type="input" name="tstamp"/>
                        {}
                        <input style="display: inline;" type="submit" class="button" value="go"/>
                    </form></span>
        """.format(cur_page, cur_page, ''.join(['<input type="hidden" name="{}" value="{}"/>'.format(k,v) for k,v in request.args.items() if k != 'tstamp']))

        header_buttons += """
                    <span style="display:inline-block;">Max rows to return:
                    <form action="{}" method="get" style="display: inline;" >
                        <input style="display: inline; width:30px" type="input" name="N"/>
                        {}
                        <input style="display: inline;" type="submit" class="button" value="go"/>
                    </form></span>
        """.format(cur_page, ''.join(['<input type="hidden" name="{}" value="{}"/>'.format(k,v) for k,v in request.args.items() if k != 'N']))


    if header_buttons != '':
        header_buttons += "<br/>"

    for f, fstr, cpage in [('', 'Help', 'help'), ('comms?format=html', 'Comms', 'comms'), ('mon?format=html', 'Monitor', 'mon'), ('passes?format=html', 'Passes', 'passes')]:
        if cpage.lower() == cur_page.lower():
            header_buttons += '<span class="button" style="opacity: 0.2;">{}</span>'.format(fstr)
        else:
            header_buttons += '<a href="{}api/{}" class="button">{}</a>'.format(url_root, f, fstr)


    html = _PAGE_TEMPLATE.replace('##TITLE##', title)
    html = html.replace('##BUTTONS##', header_buttons)
    html = html.replace('##ERROR_MSG##', err_msg)

    if not isinstance(ret, basestring):
        del ret.index.name

        if len(ret) > 0:
            html = html.replace('##MAIN##', ret.style.set_table_attributes(_TABLE_ATTRIBUTES).set_table_styles(_TABLE_STYLES).render())
        else:
            html = html.replace('##MAIN##', "NO DATA")
    else:
        html = html.replace('##MAIN##', ret) # in this case ret should be plain html


    if helptexts:
        helptext_html = ""
        for k, htext in [('comms', _HELP_COMMS), ('mon',  _HELP_MON), ('passes', _HELP_PASSES)]:
            helptext_html += """
            <div class="helptext helptext-overlay" id="_helptext_{}">
            <div style="height:50px;width:100%;margin:10px;">
            <button class="button" onclick="javascript:document.getElementById('_helptext_{}').style.visibility = 'hidden';">X CLOSE</button> 
            </div>
            <div style="width:100%;margin:10px;">
            {}
            </div>
            </div>""".format(k,k, htext)

        html = html.replace('##HELPTEXTS##', helptext_html)
    else:
        html = html.replace('##HELPTEXTS##', '')

    return html




@app.route("/api/comms")
@app.route("/api/comms/<pass_id>")
@is_allowed
def get_comms(pass_id=None):

    api = current_app.config['API']
    log = api.commslog

    if log is None:
        return "Resource not available", 403

    # Output format
    form = request.args.get('format')
    if form is None:
        form = api._default_format


    # Output format
    nid = request.args.get('nid')
    orig = request.args.get('orig')
    dest = request.args.get('dest')


    # timestamp filtering
    tstamps = request.args.get('tstamp')
    if tstamps is not None:
        tstamps = tstamps.split(',')

    #
    # is the result list going to be limited (N)
    #
    N = request.args.get('N', type=int)

    if N is None:
        ags_log.debug("No N specified, limiting to %d entries" % (DEFAULT_TABLE_LIMIT))
        N = DEFAULT_TABLE_LIMIT

    ret = log.get(pass_id=pass_id, nid = nid, orig=orig, dest=dest, tstamps=tstamps, limit=N)

    # Make norad ids proper integers if we can
    ret['nid'] = [nid_to_int_if_possible(nid) for nid in ret['nid']]


    # ensure table has columns in the right order
    ret = ret[[TSTAMP_LBL, 'nid', 'pass_id', 'orig', 'dest', 'msg']]

    retc = ret.columns.tolist()
    retc[retc.index(TSTAMP_LBL)] = _RETURNED_TSTAMP_LBL
    ret.columns = retc

    if form == 'html':
        ret  = ret.applymap(lambda x: handle_bytes(x, 'hex'))
        ret.pass_id = ['<a href="comms/{}?format=html">{}</a>'.format(r['pass_id'],r['pass_id']) for k,r in ret.iterrows()]
        return _style_html_page(ret, "Comms log", "", "comms")

    elif form == 'json':
        ret  = ret.applymap(lambda x: handle_bytes(x, 'b64'))

        rv = app.response_class(
            response=ret.to_json(),
            status=200,
            mimetype='application/json')

        rv.add_etag()
        return(rv)

    elif form == 'csv':
        ret  = ret.applymap(lambda x: handle_bytes(x, 'hex'))
        rv = app.response_class(
            response=ret.set_index(_RETURNED_TSTAMP_LBL).to_csv(),
            status=200,
            mimetype='text/csv')

        rv.add_etag()
        return(rv)


    else:
        return "Invalid format", 440






@app.route("/api/mon")
@app.route("/api/mon/<pass_id>")
@is_allowed
def get_mon(pass_id = None):
    api = current_app.config['API']
    monlog = api.monlog

    if monlog is None:
        return "Resource not available", 403


    # Output format
    form = request.args.get('format')
    if form is None:
        form =api._default_format


    # Keys
    keys = request.args.get('keys')
    if keys is not None:
        keys = keys.split(',')

    # timestamp filtering
    tstamps = request.args.get('tstamp')
    if tstamps is not None:
        tstamps = tstamps.split(',')

    #
    # is the result list going to be limited (N)
    #
    N = request.args.get('N', type=int)
        
    if N is None:
        ags_log.debug("No N specified, limiting to %d entries"%(DEFAULT_TABLE_LIMIT))
        N = DEFAULT_TABLE_LIMIT        

    if pass_id is not None:
        ret = monlog.get(pass_id = pass_id, keys=keys, tstamps=tstamps, limit=N)
    else:
        ret = monlog.get(keys=keys, tstamps=tstamps, limit=N)

    retc = ret.columns.tolist()
    retc[retc.index(TSTAMP_LBL)] = _RETURNED_TSTAMP_LBL
    ret.columns = retc

    pivoterr = ""
    if form == 'html':
        # pivot the table

        try:
            for k,v in ret['alert'].iteritems():
                if v == 'RED' or v == 'CRITICAL':
                    ret.loc[k, 'value'] = '<span style="color:red;">{}</span>'.format(ret.loc[k, 'value'])
                    # raise Exception(ret.loc[k, 'value'])

            ret1 = ret.copy()
            ret1 = ret1.pivot(index=_RETURNED_TSTAMP_LBL, columns='key', values='value')
            ret1 = ret1.applymap(lambda x: handle_bytes(x, format='b64'))
            ret1 = ret1.sort_index(ascending=False).fillna('')

            return _style_html_page(ret1, "Monitoring data", 'html', "mon")
        except Exception as e:
            pivoterr = "<span style='color:red;'>Error pivoting. Reverting to format=htmlraw. The error was '{}:{}'</span>".format(e.__class__.__name__, e)
            form = 'htmlraw'

    if form == 'htmlraw':
        ret.key = ret.key.apply(lambda v: '<a href="/api/mon?keys={}&format=html">{}</a>'.format(v,v))
        return _style_html_page(ret, "Monitoring data", 'htmlraw', "mon",  err_msg=pivoterr)


    elif form == 'json':
        rv = app.response_class(
            response=ret.to_json(),
            status=200,
            mimetype='application/json')

        rv.add_etag()
        return(rv)

    elif form == 'csv':
        rv = app.response_class(
            response=ret.set_index(_RETURNED_TSTAMP_LBL).to_csv(),
            status=200,
            mimetype='text/csv')

        rv.add_etag()
        return(rv)


    else:
        return "Invalid format", 440



@app.route("/api/passes")
@app.route("/api/passes/<pass_id>")
@is_allowed
def get_passes(pass_id = None):
    api = current_app.config['API']
    passlog = api.passdb
    commslog = api.commslog

    if passlog is None:
        return "Resource not available", 403


    # Output format
    form = request.args.get('format')
    if form is None:
        form =api._default_format


    # Keys
    keys = request.args.get('keys')
    if keys is not None:
        keys = keys.split(',')

    # timestamp filtering
    tstamps = request.args.get('tstamp')
    if tstamps is not None:
        tstamps = tstamps.split(',')

    #
    # is the result list going to be limited (N)
    #
    N = request.args.get('N', type=int)
        
    if N is None:
        ags_log.debug("No N specified, limiting to %d entries"%(DEFAULT_TABLE_LIMIT))
        N = DEFAULT_TABLE_LIMIT        

        
    if pass_id is not None:
        ret = passlog.get(pass_id = pass_id, keys=keys, tstamps=tstamps, limit=N)
    else:
        ret = passlog.get(keys=keys, tstamps=tstamps, limit=N)

    retc = ret.columns.tolist()
    retc[retc.index(TSTAMP_LBL)] = _RETURNED_TSTAMP_LBL
    ret.columns = retc

    pivoterr = ""
    if form == 'html':

        try:

            ret1 = ret.copy()


            # pivot the table
            ret1 = ret1.pivot(index='pass_id', columns='key', values='value')
            ret1 = ret1.applymap(lambda x: handle_bytes(x, format='b64'))
            ret1 = ret1.sort_index(ascending=False)
            cols = ['norad_id', 'start_t', 'start_track_t', 'end_track_t', 'stowed_t', 'max_el']
            cols = cols + [c for c in ret1.columns if c not in cols]
            for c in cols:
                if c not in ret1.columns:
                    ret1[c] = None

            ret1 = ret1[cols]

            if 'waterfall_jpeg' in cols:
                def add_link(s):
                    if not isinstance(s, basestring):
                        return s

                    if s[:7] == 'file://':
                        return ("<a class='tablelink' href='/api/file/passes/{}?format=jpeg'>download</a>".format(s[7:]))
                    else:
                        return ("<a class='tablelink' href='data:image/jpeg;base64,{}'>download</a>".format(s))

                ret1.waterfall_jpeg = ret1.waterfall_jpeg.apply(add_link)

            if 'schedule' in cols:
                def add_link(s):
                    if not isinstance(s, basestring):
                        return s

                    if s[:7] == 'file://':
                        return ("<a class='tablelink' href='/api/file/passes/{}'>download</a>".format(s[7:]))
                    else:
                        return ("<a class='tablelink' href='data:application/json,{}'>download</a>".format(s))

                ret1.schedule = ret1.schedule.apply(add_link)

            if 'signoffs' in cols:
                ret1.signoffs = [', '.join(s) if isinstance(s, list) else s for s in ret1.signoffs]

            ret1['norad_id'] = [nid_to_int_if_possible(nid) for nid in ret1['norad_id']]

            #
            # add some meta columns
            #
            ret1['comms'] = ["<a class='tablelink' href='/api/comms/{}?format=html'>go</a>".format(pid) for pid in ret1.index]
            ret1['monitoring'] = ["<a class='tablelink' href='/api/mon/{}?format=html'>go</a>".format(pid) for pid in ret1.index]

            def format_time(t):
                try:
                    return conv_time(t, to='datetime').strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return None

            ret1[['start_t', 'start_track_t', 'end_track_t', 'stowed_t']] = ret1[
                ['start_t', 'start_track_t', 'end_track_t', 'stowed_t']].applymap(format_time)

            return _style_html_page(ret1, "Passes", 'html', 'passes')
        except Exception as e:
            pivoterr = "<span style='color:red;'>Error pivoting. Reverting to format=htmlraw. The error was '{}:{}'</span>".format(e.__class__.__name__, e)
            form = 'htmlraw'


    if form == 'htmlraw':
        ret = ret.applymap(lambda x: handle_bytes(x, format='b64'))
        ret.pass_id = ret.pass_id.apply(lambda x: '<a href="/api/passes/{}?format=html">{}</a>'.format(x,x))
        # html = "<!DOCTYPE html><html><body>" + ret.style.set_table_styles(_TABLE_STYLES).render()
        # html += "</body></html>"
        # del ret.index.name
        return _style_html_page(ret, "Passes", 'htmlraw', 'passes', err_msg=pivoterr)
        # return html


    elif form == 'json':
        ret = ret.applymap(lambda x: handle_bytes(x, format='b64'))
        rv = app.response_class(
            response=ret.to_json(),
            status=200,
            mimetype='application/json')

        rv.add_etag()
        return(rv)

    elif form == 'csv':
        ret = ret.applymap(lambda x: handle_bytes(x, format='b64'))        
        rv = app.response_class(
            response=ret.set_index(_RETURNED_TSTAMP_LBL).to_csv(),
            status=200,
            mimetype='text/csv')

        rv.add_etag()
        return(rv)


    else:
        return "Invalid format", 440


@app.route("/api/file")
@app.route("/api/file/<dbname>")
@app.route("/api/file/<dbname>/<fname>")
@is_allowed
def get_file(dbname=None, fname=None):

    if dbname is None or fname is None:
        return "Invalid DB / FILE" , 403

    api = current_app.config['API']        
    
    if dbname == 'comms':
        db = api.commslog
    elif dbname == 'mon':
        db = api.monlog
    elif dbname == 'passes':
        db = api.passdb
    else:
        return "Invalid database", 403
        
        
    try:
        data = db.get_file(fname)
    except:
        return "Invalid file", 403
    

    form = request.args.get('format')
    
    if isinstance(data, basestring):

        # TODO: FIX THIS !!!
        # What's going on here is that the json is doubly encoded. In the past there wasnt much of a way around that
        # but lately we are prefixing json stuff with json:// so we should be able to get away from this.
        # Anyway, for now just hack it to remove the type indicator.
        #
        if data[:7] == 'json://':
            data = data[7:]

        rv = app.response_class(
            response=json.loads(data),
            status=200,
            mimetype='application/json')

        return rv

        
    if form == "jpg" or form == "jpeg":
        rv = app.response_class(
            response=data,
            status=200,
            mimetype='image/jpeg')

        return rv

    else:
        ret = handle_bytes(data, 'b64string')
        rv = app.response_class(
            response=json.dumps(ret),
            status=200,
            mimetype='application/json')

        return rv
        


@app.route("/api/<path:path>")
@is_allowed
def get_rpcapi(path):
    """
    Invoke a (user-defined) RPC API. 
    
    Usage:
       /api/<name>[/method]
      
    Args:
       name             : can have several levels; eg. "test/subtest/etc" or not "test"
       method (optional): The RPC method to call (if not supplied return available methods)
    
    """
    try:
        api = current_app.config['API']
        rpcapi = api.rpcapi


        def guess_arg_type(inp):
            try:
                out = float(inp)
            except:
                out = str(inp)

            return out

        name = None
        for apiname in rpcapi.keys():
            if path.find(apiname.strip()) == 0:
                name = apiname.strip()
                args = path[len(apiname)+1:].strip().split('/')
                method = args[0].strip()
                args = [guess_arg_type(a) for a in args[1:]]
                break

        status = 200

        if name is None:
            status = 403
            ret =  "Invalid resource {}"
        elif name not in rpcapi.keys():
            status = 403
            ret = "Invalid RPC API endpoint '{}'. Available are {}".format(name, rpcapi.keys())
        else:

            r = rpcapi[name]

            if method is None or method == '':
                ret = r['methods']

            elif method not in r['methods']:
                status = 403
                ret = "Method '{}' not available. Available: {} ".format(method, r['methods'])
            else:
                kwargs = {k:guess_arg_type(v) for k,v in request.args.items()}

                try:
                    ret = getattr(rpcapi[name]['server'], method)(*args, **kwargs)
                except Exception as e:
                    ret = dict(description="Exception while making RPC call. Most likely reason is that the RPC function does not return a marshallable type. (See https://docs.python.org/2/library/xmlrpclib.html), or passed arguments are invalid.",
                               exc_type = e.__class__.__name__,
                               exception = str(e))

                    status = 500

        # if method returned valid json, dont jsonify again, otherwise do so
        try:
            json.loads(ret)
            retj = ret
        except:
            try:
                retj = json.dumps(ret)
            except Exception as e:
                raise

    except Exception as e:
        retj = json.dumps(dict(exc_type=e.__class__.__name__, exception=str(e)))
        status = 500

    rv = app.response_class(
        response=retj,
        status=status,
        mimetype='application/json')
    
    return rv
    
    
    


@app.route("/api", strict_slashes=False)
@is_allowed
def get_help():
    api = current_app.config['API']
    rpcapi = api.rpcapi
    
#     html = """
# <h2> libgs api </h2>
# """
#
#     # TODO: Get helps from docstrings
    html = ""


    helptxt_html = ""
    for htext in [_HELP_COMMS, _HELP_MON, _HELP_PASSES, _HELP_FILES]:
        helptxt_html += "<p><div class='helptext'><div style='margin:10px;'>" + htext + "</div></div></p>"
    html += helptxt_html


    #
    # RPC help
    #
    htext = _HELP_RPC
    if len(rpcapi) > 0:
        htext += 'The currently mapped APIs are:'
        htext +=  '<table style="padding:1px;">'
        htext += '<tr><th style="width:15em;text-align:left;">Endpoint</th><th style="text-align:left;">Available methods</th></tr>'
        for k,v in rpcapi.items():
            htext += '<tr><td style="vertical-align: center;"><a href="/api/{}">/api/{}</a></td>\n'.format(k,k)
            htext += '<td style="vertical-align: center"><pre>{}</pre></td></tr>\n'.format('<br/>'.join(m for m in v['methods']))
        htext += '</table>'
    else:
        htext += 'No APIs are currently mapped. Do so by calling libgs-restapi with the -r / --rpcapi parameter'

    html += "<p><div class='helptext'><div style='margin:10px;'>" + htext + "</div></div></p>"

    
    return _style_html_page(html, "libgs REST API", None, "help"), 200



if __name__=='__main__':
    pass
