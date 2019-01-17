.. libgs documentation master file, created by
   sphinx-quickstart on Wed Apr 11 10:41:28 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.


.. container:: License

 Copyright © 2017-2018 The University of New South Wales

 Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
 The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

 Except as contained in this notice, the name or trademarks of a copyright holder shall not be used in advertising or otherwise to promote the sale, use or other dealings in this Software without prior written authorization of the copyright holder.

 UNSW is a trademark of The University of New South Wales.


Welcome to libgs's documentation!
=================================

.. warning::

   If you are reading this on readthedocs, the documentation is most likely broken.
   So until I succeed in getting it to play nice with RTD (i.e. until further notice), it will be hosted
   on github pages and you can access it at the following address:

   https://kworm1.github.io/libgs-docs/




libgs module reference
-----------------------

.. autosummary::
    :toctree: _autosummary
    
    ~libgs.utils
    ~libgs.scheduler
    ~libgs.rpc
    ~libgs.restapi
    ~libgs.hardware
    ~libgs.groundstation
    ~libgs.console_scripts
    ~libgs.visualisation
    ~libgs.database
    ~libgs.emulators
    ~libgs.monitoring
    ~libgs.protocols.protocolbase

libgs_ops modules
-----------------

.. autosummary::

    libgs_ops.propagator
    libgs_ops.scheduling
    libgs_ops.rpc
