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




:date: Mon Jul 17 16:38:56 2017
:author: kjetil

Overview
-----------

This module contains wraps Bokeh code with the focus to provide the elements to build
web-apps for a libgs dashboards. It also contains the code necessary to create and runa bokeh server programatically.


.. note::

    While based on Bokeh, this module does not require the Bokeh server to run. Rather the
    Bokeh server is initiated from within this module. For that reason the syntax
    for "live" elements (Plots and Widgets) is slightly different to the most common
    examples in the Bokeh documentation.


The plots and elements in this module can be updated dynamically.

Implementation
----------------

Plot elements
^^^^^^^^^^^^^^

This module implements the following specialised plot elements:

* :class:`Markup`        : A simple text or html interface
* :class:`Waterfall`     : A waterfall plot (must be connected to a FrequencyPlot)
* :class:`FrequencyPlot` : Show a spectrum
* :class:`SatellitePass` : Plot the pass of a satellite

A user can make use of any of these, or make their own plots by deriving from the :class:`LivePlot` class.

All plots are derived from :class:`LivePlot` and shall implement the following method and attribute:

* :meth:`~LivePlot.create_fig`: Shall return a Bokeh figure.
* :attr:`~LivePlot.name`: A unique idenitifer for the figure

Additionally they may implement the following attributes if required:

* live_data (type: dict)
* live_props (type: dict)

Data registered in live_data will be passed onto the figure ColumnDataSource
using the same mapping. And properites in live_props will be updated
on the figures as well.



Dashboard Apps
^^^^^^^^^^^^^^

Apps are defined as independent web-apps, and are created by deriving from :class:`BokehDash`. Apps then need to be added
to a :class:`BokehServer` object, in order to make them available.

:class:`BokehDash` implmenents the Bokeh Server and keeps
track of the different plots that are added to it. When the web-page is
requested by a client, it will construct a document for each client using the
individual plots'get_fig function.

It will also create ColumnDataSources for those figures, and in a regular
callback loop, keep everything up to date with the live_data and live_props
dictionaries in the different plots.

With this implementation, it is possible to have multiple clients connect at
the same time and see the same data while not having to run bokeh as a separate
application.

The apps that are currently available in this module are:

* :class:`TextDash`:   A simple app that just shows text (or html) which is updatable via a live_prop property
* :class:`TrackDash`:  A full-fledged dashboard showing antenna tracking status as well as spectra/waterfall from the radios,
                       and the current schedule information.



Examples
---------

.. todo:

    Implement visualisation examples



Module reference
-----------------
"""

################################################################################
#
# Setup
#
################################################################################

# Create Tornado IOLoop
from tornado.ioloop import IOLoop
import threading

import bokeh
from bokeh.server.server import Server
from bokeh.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.plotting import Figure, ColumnDataSource
import bokeh.layouts as bl
import requests
from bokeh.models.widgets import PreText, Div, Paragraph
from numpy import sin, cos, pi
import numpy as np
from bokeh.models import LabelSet, Label#, HoverTool
import colorsys
import datetime
from utils import Defaults, RegularCallback, Error

# Configure logging with the name adfags-log, and add the NullHandler. That
# means that log messages will be dropped unless the application using this
# library configures logging.
import logging
log = logging.getLogger('adfags-log')
log.addHandler(logging.NullHandler())



#
# Prevent tornado for polluting the root handler.
# TODO: Configure tornados own logger (tornado.access) to ge the log messages
#
logging.getLogger().addHandler(logging.NullHandler())


################################################################################
#
# Functions
#
################################################################################


def linktext(links):
    """
    Convenience function to create a series of navigation links to use on the top
    of the different apps
    """

    if 1:
        linktxt = ''
        for link in links:
            if len(link) == 2:
                link = (link[0], link[1], None)

            if len(link) != 3:
                raise Error("Invalid link argument")

            if linktxt != '':
                linktxt += ' | '

            if link[2] is not None:
                linktxt += '<a href="%s" onclick="javascript:event.target.port=%d">%s</a>'%(link[1], link[2], link[0])
            else:
                linktxt += '<a href="%s">%s</a>'%(link[1], link[0])


    return linktxt

def azel2rect(az, el):
    """
    Helper-function to conver az,el (polar coordinates) to x,y
    for display on rectangular axes

    """
    if az is None or el is None:
        return None, None

    # Check if az and el are arrays or scalars
    # convert to arrays if scalar
    try:
        len(az)
    except TypeError:
        az = [az]

    try:
        len(el)
    except TypeError:
        el = [el]

    if len(az) != len(el):
        raise Error('az and el must be of same lenght')

    az = 360.0 - np.array(az)
    el = np.array(el)
    x = (90-el)*cos((az+90)/180.0*pi)
    y = (90-el)*sin((az+90)/180.0*pi)
    return x,y


################################################################################
#
# Plots
#
################################################################################


class LivePlot(object):
    """
    Base class for all the plots.

    All derived classes shall implent the following method and attribute

    * create_fig(self, sources): Shall return a Bokeh figure.
    * name (type: str): Uniquely identifying name

    Additinoally they may implement the following attributes if required. Data
    registered in live_data will be passed onto the figure ColumnDataSource
    using the same mapping. And properites in live_props will be updated
    on the figures as well.

    * live_data (type: dict)
    * live_props (type: dict)


    """

    #: A dictionary of data that shall be updatable dynamically. Each value in live data will be regularly and automatically
    #: synced with the :class:`bokeh.plotting.ColumnDataSource` object associated with your plot. Thus in order to
    #: update your plot data, all you have to do is update the relevant field in live_data.
    #: For example if live_data = {'x': [1, 2, 3], 'y': [4, 5, 4]} indicates the x and y data in a plot, changing
    #: live_data[y] to [8, 10, 8] will be immediately reflected on the plot.
    live_data = dict()

    #: A dictionary of properties that shall be updatable dynamically. Each value in live props will be regularly and automatically
    #: updated in the bokeh object associated with your plot. Thus if for example you have an object with a text property
    #: you can change the text by updating the live_props['text']. The change will be immediately reflected on the element.
    live_props = dict()

    #: A uniquely identifying name for the plot
    name = None

    def __init__(self):
        pass

    def __get_name__(self):
        if self.name is None:
            raise Exception("LivePlot class does not have a name")

        return self.name

    def create_fig(self, sources):
        """
        The create_fig method shall set up a Bokeh Figure object appropriately and return it

        Args:
            sources:  Will be a ictionary of ColumnDataSources where the keys will correspond to the keys
            of the :attr:`.live_data` attribute dictionary.

        Returns:

        Args:
            sources:

        Returns:

        """
        raise Error('create_fig(self,sources) must be overloaded')
        # live plots


class SatellitePass(LivePlot):
    """
    Visualisation of the sky.

    Can show, in real-time, the current and demanded pointing of the
    antennas, the satellite track, and the position of the tracked satellite

    Attr (See :class:`LivePlot`
        name: A descriptive (and unique) name. Required for the Bokeh server
        live_data: The datapoints that can be updated in real-time
        live_props: The properties that can be updated in real-time

    """


    def __init__(self, name, **fig_args):
        """

        Args:
            name:       Unique name for this plot
            **fig_args: Arguments to pass to :class:`bokeh.plotting.figure.Figure`
        """
        self.name=name

        # Create some live data, but plot it outside the view so it isnt visible
        self.live_data = dict(
            ant_cur = {
                'x': [-1e9],
                'y': [0]},

            ant_cmd = {
                'x': [-1e9],
                'y': [0]},

            sat = {
                'x': [-1e9],
                'y': [0]},

            dpass = {
                'x': [-1e9,-1e9,-1e9,-1e9],
                'y': [-10, -5, 5, 10]}
                )

        # Figure arguments
        self._fig_args = fig_args


    def create_fig(self, sources):
        """
        Implementation of :meth:`LivePlot.create_fig` to set up the bokeh figure
        """

        fig = Figure(background_fill_color= None,
                     toolbar_location = None,
                     x_range=[-100, 100], y_range=[-100, 100], tools="", **self._fig_args)



        # Remove existing axes and grid
        fig.xgrid.grid_line_color = None
        fig.ygrid.grid_line_color = None
        fig.axis.visible = False


        # Draw circular grid
        th = np.linspace(0, 360, 100)

        # Draw visibility field
        self.vis_horizon = 10
        #fig.patch(*pol2rect([90 - self.vis_horizon]*len(th), th), color='lightgray')
        fig.patch(*azel2rect(th, [self.vis_horizon]*len(th)), color='lightgray')


        for r in [0, 20, 40, 60, 80]:
            fig.line(*azel2rect(th, [r]*len(th)), line_dash='dashed')

        for th in np.arange(0,360,45):
            fig.line(*azel2rect([th,th], [0,90]), line_dash='dashed')

        # Add grid labels
        lx,ly = azel2rect([0, 90, 180, 270], [0]*4)
        lx[1] -= 30
        lx[2] -= 20
        ly[0] -= 10
        lx[0] -= 10
        src_labels = ColumnDataSource(dict(
            labels= ['N (0)', 'E (90)', 'S (180)', 'W (270)'],
            label_x= lx,
            label_y =ly))

        fig.add_layout(LabelSet(x='label_x', y='label_y', text='labels', source=src_labels))



        fig.line(source=sources['dpass'], x='x', y = 'y', line_width=2)
        fig.circle(source=sources['ant_cmd'], x='x', y='y', size=20, fill_color=None)
        fig.circle(source=sources['ant_cur'], x='x', y='y', size=10, color='green')
        fig.circle(source=sources['sat'], x= 'x', y ='y', size=10, color= 'yellow')

        return fig




    def plot_pass(self,az, el):
        """
        Convenience function for plotting a pass
        """
        x, y = azel2rect(az, el)
        self.live_data['dpass'] = dict(x=x,y=y)

    def update_data(self, dataset, az, el):
        """
        Convenience function for updating any live_data element

        Args:
            dataset (string): The live_data to update. dataset='dpass' is equivalent
                              to calling plot_pass
            az: The azimuth coordinate(s)
            el: The elevaiton coordinate(s)

        """

        if dataset not in self.live_data.keys():
            raise Error("Invalid dataset")

        x, y = azel2rect(az, el)

        self.live_data[dataset] = dict(x=x, y=y)

class FrequencyPlot(LivePlot):
    """
    A frequency spectrum plot for use within a libgs dashboard web-application.

    .. note::

        FrequencyPlot needs a callable that it can query to obtain the frequency and spectrum information. Normally
         this would be :meth:`.hardware.RadioBase.get_spectrum`. If you are implementing a non-standard radio,
         ensure you consult that documentation for the format of the callable.

    .. note::
        FrequencyPlot uses the ColumnDataSource identifier 'freq'

    """

    def __init__(self, name, get_spectrum, wfall=None,  title=None, **fig_args):
        """

        Args:
            name:                   The identifying name of the plot
            get_spectrum:           A callable that should return the current frequency vector and spectrum. Normally this would be the method from a :class:`.RadioBase` derived object.
            wfall (optional):       The waterfall plot to connect to
            title (optional):       The title of the frequency plot
            **fig_args (optional:   Any other kw argument is passed directly to :class:`bokeh.plotting.Figure` when creating the figure.
        """
        self.live_data = {'freq': {'x': [], 'y':[]}}
        self.name = name
        self._get_spectrum = get_spectrum

        #Figure title
        self._fig_title = title if title is not None else name

        # Figure arguments
        self._fig_args = fig_args

        # The waterfall to connect spectrum to
        self._wfall_plot = wfall
        
        # Rate at which to update spectrum
        self._update_delay = Defaults.VIS_FREQUENCY_PLOT_UPDATE_DELAY


    ##########################################################################################
    #
    # Private methods
    #
    ##########################################################################################

    def _update_plots(self):
        try:
            x, y = self._get_spectrum(old=False)
        except:
            return
    
        self.live_data['freq'] = {'x':x, 'y':y}
   
        if self._wfall_plot is not None:
            self._wfall_plot.add_freq_plot(y)
            

    ##########################################################################################
    #
    # Overloaded methods
    #
    ##########################################################################################


    def create_fig(self, sources):
        """
        Class implementation of :class:`.LivePlot.create_fig`.

        """

        self._sample_rate = 32000 #<-- just a default sample rate to use until something is read from the get_spectrum callable
        self._freq=0
        fig = Figure(logo=None, **self._fig_args)

        fig.line(source=sources['freq'], x='x', y = 'y')
        fig.xaxis.axis_label = "Frequency (MHz)"
        if self._fig_title is not None:
            fig.title.text = self._fig_title

        fig.x_range.range_padding = 0

        return(fig)

    ##########################################################################################
    #
    # Other methods
    #
    ##########################################################################################


    def connect(self):
        self._regcb = RegularCallback(self._update_plots, delay=self._update_delay)
        self._regcb.start()

    def disconnect(self):
        if hasattr(self, '_regcb'):
            self._regcb.stop()


class Waterfall(LivePlot):
    """
    LivePlot visualisation of a "waterfall plot".

    This plot must be connected to a FrequencyPlot which will feed it data. The connection is done in the
    :class:`FrequencyPlot` constructor.

    """

    def __init__(self, name, sample_rate=3200, freq=0,  wfallwidth=128, wfallheight=100, **fig_args):
        """

        Args:
            name (str):                     The :attr:`LivePlot name <LivePlot.name>`
            sample_rate (int, optional):    Only affects the figure x-axis which is disabled by default. This parameter
                                            will therefore normally have no effect.
            freq (float, optional):         Only affects the figure x-axis which is disabled by default. This parameter
                                            will therefore normally have no effect.
            wfallwidth (int, optional):     The width of the waterfall (in pixels). Note wfallwidth must divide
                                            the number of channels in the spectrum returned by the radio. I.e. if the radio
                                            returns a 1024 point fft, then wfallwidth could be 128 since 8 * 128 = 1024.
                                            A wfallwidth of 129 will cause an exception and error.
            wfallheight (int, optinal):     The height of the waterfall (in pixels).
            **fig_args:                     Additional arguments to pass to the :class:`bokeh.plotting.figure.Figure` constructor.
        """
        self.live_data = {'wfall': { 'image':[np.random.random((wfallheight,wfallwidth))]}}
        self.name = name
        self._sample_rate = sample_rate
        self._freq = freq
        self._height = wfallheight
        self._width = wfallwidth
        self._fig_args = fig_args

    def create_fig(self, sources):
        """
        Class implementation of :meth:`LivePlot.create_fig`.
        """

        fig = Figure(logo=None,
                     x_range=[-self._sample_rate/2.0, self._sample_rate/2.0],
                    y_range=[0,self._height], **self._fig_args)

        fig.image('image', source= sources['wfall'], x=-self._sample_rate/2.0, y = 0, dw=self._sample_rate,dh=self._height,palette=Defaults.WFALL_COLORMAP )

        fig.xgrid.grid_line_color = None
        fig.ygrid.grid_line_color = None
        fig.axis.visible = False

        return fig

    def add_freq_plot(self, freq):
        """
        Method to append a spectrum to the waterfall.

        It does this by appending a row to the live_data image property.

        Args:
            freq: (list[float]). Spectrum to append.

        """

        if self._width < len(freq):
            if  len(freq) % self._width != 0:
                raise Error('frequency vector must be a multiple of waterfall width')
            else:
                freq = np.array(freq).reshape((-1, len(freq)/self._width))
                freq = freq.max(1)

        if self._width != len(freq):
            raise Error('Dimension mismatch')

        data = self.live_data['wfall']['image'][0]
        if data.shape[0] < self._height:
            self.live_data['wfall']['image'] = [np.concatenate((data, [freq]))]
        else:
            self.live_data['wfall']['image'] = [np.concatenate((data[1:,:], [freq]))]


class Markup(LivePlot):
    """
        A LivePlot wrapper for the three Bokeh Markup widgets;

        * :class:`bokeh.models.widgets.markups.Div`
        * :class:`bokeh.models.widgets.markups.Paragraph`
        * :class:`bokeh.models.widgets.markups.PreText`

        The text (or html) can be changed through the 'text' property in the :attr:`~LivePlot.live_props` attribute.

    """

    def __init__(self, name, text, mtype='PreText', **args):
        """

        Args:
            name:       The :attr:`LivePlot.name` for the LivePlot
            text:       The text/html to populate the widget with
            mtype:      The type of Boke Markup widget. One of 'LivePlot', 'PreText', or 'Paragraph'
            **args:     Additional kw arguments to pass to the bokeh widget constructor.
        """
        self._text = text
        self.name = name
        self.live_props = {'text': text}
        self.live_data = {}
        self._args = args

        if mtype not in ['PreText', 'Div', 'Paragraph']:
            raise Error('Invalid mtype')

        self._type = mtype

    def create_fig(self, sources):
        """


        """

        if self._type == 'PreText':
            fig = PreText(text=self._text,  **self._args)
        elif self._type == 'Div':
            fig = Div(text=self._text, **self._args)
        elif self._type == 'Paragraph':
            fig = Paragraph(text=self._text, **self._args)

        return fig


class BokehServer(object):
    """
        A class to set up and run the bokeh server to serve the dashboard apps.

        Apps need to be added to the server using the :meth:`.add_app` method

    """


    def __init__(self, port=5001, host='127.0.0.1'):
        """
        Args:
            port: The port to start the server on
            host: The host to bind the server to
        """
        self._loop = IOLoop()
        self._apps = {}
        self._bokeh_port = port
        self._bokeh_host = host

    def add_app(self, uri, makefn):
        """
        Adds an app to the server

        the app is a standard :class:`bokeh.application.application.Application` that is created by passing either
        an arbitrary makefunction (see :class:`bokeh.application.handlers.function.FunctionHandler`), or a :class:`BokehDash`
        object (which implements the same make function as the make_doc method).

        Args:
            uri:    The URI to serve the app on (e.g. '/dash', or '/' or ...)
            makefn: The app to add (can be either a BokehDash app, or an arbitrary user-define app maker function.
                    If you are implementing arbitrary app-maker ensure it follows the format required by
                     :class:`bokeh.application.handlers.function.FunctionHandler`

        Returns:

        """
        if isinstance(makefn, BokehDash):
            makefn = makefn.make_doc
        elif not callable(makefn):
            raise Error("App must either be of type BokehDash (i.e. with a make_doc method), or a callable")

        self._apps[uri] = Application(FunctionHandler(makefn))

    def start(self):
        """
            Starts the server and tornado IOloop. This is required for the plots
            to become live. The ioloop is started in a separate thread so this method returns immediately.

        """

        self._server = Server(self._apps, address=self._bokeh_host, port=self._bokeh_port, loop=self._loop,
                              allow_websocket_origin=["*"])

        self._server.start()

        self._ploop = threading.Thread(target=self._loop.start)
        self._ploop.daemon = True
        self._ploop.start()

        # Now request the page so that all the figures get initialised

        for uri in self._apps.keys():
            url = "http://%s:%d%s" % (self._bokeh_host, self._bokeh_port, uri)
            log.debug("Initialising app on %s" % (url))
            requests.get(url)

    def stop(self):
        """
            Stops the tornado IOloop (does not do anything with the server)

            ..todo::
              Properly stop server too
        """

        self._loop.stop()
        self._ploop.join()



class BokehDash(object):
    """
        A bare-bone Bokeh dashboard app.

        Plots and Visualisations can be added to the Dashboard using the add_plot
        method.


    """

    def __init__(self, update_rate=0.1, title="Bokeh-based dashboard", layout_callback=None):
        """
        Args:
            update_rate (float, optional): The delay (in seconds) between each update of
                        the dashboard (on the client-side)
            title (string, optional): The dashboard title
            layout_callback (function, optional): An optional function that defines
                        the layout using bokeh.layout elements. The layout_callback function
                        shall accept a single argument being a list of figures.
                        It shall return a layout comprising those figures.
        """

        self._title_text = title

        # set update rate (in ms)
        self._update_rate = int(update_rate * 1000)

        # plots
        self._plots = []

        # Layout function
        # TODO: Change this to be a method that we overload in the derived classes instead (?)
        self._layout_callback = layout_callback

    def add_plot(self, plot):
        """
            Add a :class:`LivePlot` to the document

            Args:
                plot: The :class:`LivePlot` to add.
        """

        self._plots.append(plot)

    def get_plot(self, name):
        """
        Return a :class:`LivePlot` by name

        """

        for p in self._plots:
            if p.name == name:
                return p

        raise Error('Plot does not exist')

    def _create_title_fig(self):
        fig = Figure(sizing_mode='scale_width',
                     x_range=[0, 1], y_range=[0, 1], plot_height=50, tools="")

        # Remove existing axes and grid
        fig.xgrid.grid_line_color = None
        fig.ygrid.grid_line_color = None
        fig.axis.visible = False
        fig.background_fill_color = None
        fig.toolbar_location = None

        text = Label(x=0.5, y=0.5,
                     text=self._title_text, render_mode='css',
                     background_fill_color='white', background_fill_alpha=1.0,
                     text_font_size='28pt', text_align='center', text_baseline='middle'
                     )

        fig.add_layout(text)

        return (fig)

    def make_doc(self, doc):
        """
            Set up the document. This function is called once for each
            client connection.

            Variables are therefore kept local in this scope rather than
            added to the class as method which would have meant that multiple
            users were served the same variable (ColumnDataSource or Figure)
            something that is not permitted by Bokeh.

            .. note::

                This method is the bokeh makefunction (see :class:`bokeh.application.handlers.function.FunctionHandler`)
                that will be passed to the :class:`bokeh.application.Application` constructor.

            While a derived class *may* overload this method it is not recommended to do so. Instead you can initialise
            this class with the layout_function parameter in order to lay out the LivePlots.

        """
        titlefig = self._create_title_fig()

        clock = Paragraph(text="A clock")

        datasrc = {}

        for plot in self._plots:
            datasrc[plot.__get_name__()] = dict()
            for data_key, data in plot.live_data.items():
                datasrc[plot.__get_name__()][data_key] = ColumnDataSource(data)

        # Create a dot that continually changes colour to show that app is live
        src_heartbeat = ColumnDataSource(dict(x=[0.01], y=[0.9], color=['red']))
        hb_cols = [bokeh.colors.RGB(*np.array(colorsys.hsv_to_rgb(a, 1, 1)) * 255) for a in np.linspace(0, 1, 40)]

        def update():

            # Update heartbeat
            update.counter = (update.counter + 1) % len(hb_cols)
            src_heartbeat.data['color'] = [hb_cols[update.counter]]

            # Update clock
            clock.text = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

            # Update everything else
            for plot in self._plots:
                for data_key, data in plot.live_data.items():
                    datasrc[plot.__get_name__()][data_key].data = data

                for prop, data in plot.live_props.items():
                    setattr(figs[plot.__get_name__()], prop, data)

        update.counter = 0

        # Set update frequency
        doc.add_periodic_callback(update, self._update_rate)

        # Set up the figures, and plot anything that is static
        #
        # WARNING: Using self.figs here is probably dangerous
        #  Since I believe a new figs object needs to be created
        #  at every reload.
        figs = dict()
        for plot in self._plots:
            figs[plot.__get_name__()] = plot.create_fig(datasrc[plot.__get_name__()])

        # Draw heartbeat
        titlefig.circle(source=src_heartbeat, x='x', y='y', color='color', size=10)

        # Lay everything out
        if self._layout_callback is None:
            layout = bl.layout([[titlefig, clock], figs.values()], sizing_mode='scale_width')
        else:
            layout = bl.column([titlefig, clock, self._layout_callback(figs)], sizing_mode='scale_width')

        doc.add_root(layout)

        doc.title = self._title_text


class TrackDash(BokehDash):
    """
    A full dashboard featuring:

    * :class:`SatellitePass` plot to show the trajectory of the satellite and rotators
    * :class:`Markup` box to show the current status of the ground station
    * :class:`FrequencyPlot` + :class:`Waterfall` for each of the configured :class:`radios <hardware.RadioBase>`
    * :class:`Markup` box to show the current schedule executed by the scheduler

    """


    #: The base number of units to use to scale the plots.
    #: Note, to change, must be set before instanitating anything from the class
    UNITS = 50

    def __init__(self,  radios=[], title="Groundstation Dashboard", links=[]):
        """

        Args:
            radios (list[:class:`hardware.RadioBase]).  The radios to create plots for
            title: (str).                               The title of the dashboard
            links: (list[tuple[str]])                   A list of tuples (name, URI) to use to create navigation links
        """

        UNITS = self.UNITS
        WFALLH = 5*UNITS
        FREQH = 5*UNITS

        # Radio plots - freqency and waterfalls
        wfall = []
        freq = []

        i = 1
        for radio in radios:

            wfall.append(Waterfall('wfall%d'%(i), 32000, 0, plot_height=WFALLH, toolbar_location=None))
            freq.append(FrequencyPlot('freq%d'%(i), radio.get_spectrum, wfall=wfall[-1], title = radio.name, plot_height=FREQH, tools="hover"))
            freq[-1].connect()
            i +=1

        # Satellite pass visualisation
        spass = SatellitePass('spass', plot_height=5*UNITS, plot_width=5*UNITS)

        # Textbox for tracking info
        track_info  = Markup('track_info', mtype='Div', text='', width=500)

        # Tetbox for schedule info
        sch_info = Markup('sch_info', text='')


        # Links along the top to different apps
        linksbox = Markup('links', mtype='Div', text=linktext(links))


        #
        # Create a custom layout to make things look nice
        #
        def layout_figs(figs):

            #row1 = bl.row([figs['title']], sizing_mode='scale_width')
            row2 = bl.row([figs['links']], sizing_mode='scale_width')
            row3 = bl.row([figs['spass'], figs['track_info']], sizing_mode='fixed')

            radios = []

            for i in range(1, len(wfall)+1):
                radios.append(bl.column([figs['freq%d'%(i)],figs['wfall%d'%(i)]], sizing_mode='scale_width'))


            row4 = bl.row(radios, sizing_mode='scale_width')
            row5 = bl.row([figs['sch_info']], sizing_mode='scale_width')

            layout = bl.column([row2,row3,row4, row5], sizing_mode='scale_width')

            return layout

        super(TrackDash, self).__init__(layout_callback=layout_figs, title=title)

        #
        # Now add everything to the dashboard
        #
        for wf in wfall:
            self.add_plot(wf)

        for f in freq:
            self.add_plot(f)

        self.add_plot(spass)
        self.add_plot(track_info)
        self.add_plot(linksbox)
        self.add_plot(sch_info)


class TextDash(BokehDash):
    """
    A simple Dash app that just contains a single :class:`Markup` text nbox.
    """

    def __init__(self, title, plot_name, mtype='PreText',  links=[]):
        """

        Args:
            title:      The title of the plot
            plot_name:  The unique name to refer to the LivePlot by (this dash only has a single LivePlot - the textbox)
            mtype:      The type of textbox to use. Options are PreText, Div, or Paragraph. See :class:Markup
            links:      An array of links to display. See :function:`linktext` for the format.
        """


        if plot_name == 'links':
            raise Error("Plot name cannot be links")

        linksbox = Markup('links', mtype='Div', text=linktext(links))

        textbox  = Markup(plot_name, mtype=mtype, text='')


        #
        # Create a custom layout to make things look nice
        #
        def layout_figs(figs):

            row1 = bl.row([figs['links']], sizing_mode='scale_width')
            row2 = bl.row([figs[plot_name]], sizing_mode='scale_width')
            layout = bl.column([row1,row2], sizing_mode='scale_width')

            return layout

        super(TextDash, self).__init__(layout_callback=layout_figs, title=title)


        self.add_plot(linksbox)
        self.add_plot(textbox)



if __name__=='__main__':

    if 1:
        from adfags import Radio, Defaults
        server = BokehServer()
        radios = [\
                Radio('UHF TX', Defaults.RADIO_INTS['UHFTX']),
                Radio('UHF RX', Defaults.RADIO_INTS['UHFRX']),
                Radio('SBAND', Defaults.RADIO_INTS['SBAND'])]
        dash = TrackDash(radios=radios)
        statdash = TextDash(plot_name='hwstatus')
        servdash = TextDash(plot_name='servstatus')

        server.add_app('/', dash)
        server.add_app('/status', statdash)
        server.add_app('/services', servdash)
        server.start()
