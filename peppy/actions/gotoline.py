# peppy Copyright (c) 2006-2007 Rob McMullen
# Licenced under the GPL; see http://www.flipturn.org/peppy for more info
"""
Includable file that is used to provide a Goto Line function for a
major mode.
"""

import os

import wx
import wx.stc

from peppy.actions.minibuffer import *
from peppy.major import *
from peppy.debug import *


class GotoLine(MinibufferAction):
    """Goto a line number.
    
    Use minibuffer to request a line number, then go to that line in
    the stc.
    """
    alias = _("goto-line")
    name = _("Goto Line...")
    tooltip = _("Goto a line in the text.")
    key_bindings = {'default': 'M-G',}
    minibuffer = IntMinibuffer
    minibuffer_label = _("Goto Line:")

    def processMinibuffer(self, minibuffer, mode, line):
        """
        Callback function used to set the stc to the correct line.
        """
        
        # stc counts lines from zero, but displayed starting at 1.
        #dprint("goto line = %d" % line)
        mode.stc.GotoLine(line - 1)
