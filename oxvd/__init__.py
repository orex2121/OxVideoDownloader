"""oxvd package.

Import side effect: when running under the app's bundled portable Python
(python\\), point TCL_LIBRARY/TK_LIBRARY at the Tcl/Tk script folders that
ship inside it. Tcl otherwise resolves init.tcl through the registry or the
working directory, which breaks once the folder is moved to another machine.
On a regular Python install the directories do not exist and nothing changes.
"""

import os
import sys


def bootstrap_tcltk():
    if os.name != "nt":
        return
    pydir = os.path.dirname(sys.executable)
    for var, sub in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        path = os.path.join(pydir, "lib", sub)
        if os.path.isfile(os.path.join(path, "init.tcl")):
            os.environ[var] = path


bootstrap_tcltk()
