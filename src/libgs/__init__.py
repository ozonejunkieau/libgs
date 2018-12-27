"""
..
    Copyright 2017 UNSW Canberra Space

    Permission is hereby granted, free of charge, to any person obtaining a copy of
    this software and associated documentation files (the "Software"), to deal in
    the Software without restriction, including without limitation the rights to
    use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
    the Software, and to permit persons to whom the Software is furnished to do so,
    subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
    FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
    COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
    IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


"""


#
# Set matplotlib to use a non-X backend if on a machine without a DISPLAY
#
import os
try:
    if os.name == 'posix' and 'DISPLAY' not in os.environ:
        import matplotlib
        matplotlib.use("Agg")
        # have to print this since log is not available yet when calld.
        print("Matplotlib is available but there is no DISPLAY. Setting Agg backend")
except:
   pass



#
# Magic to get version number from git repository tag, regardless of whether the package has been installed or
# just checked out.
#
from pkg_resources import get_distribution
try:
    __version__ = get_distribution(__name__).version
except:
    # package is not installed

    try:
        from setuptools_scm import get_version
        __version__ = get_version(root='../..', relative_to=__file__) + '.notinst'
    except Exception as e:
        __version__ = 'unknown_{}'.format(str(e).replace(' ', '_'))

    
