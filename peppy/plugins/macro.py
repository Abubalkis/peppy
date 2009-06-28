# peppy Copyright (c) 2006-2008 Rob McMullen
# Licenced under the GPLv2; see http://peppy.flipturn.org for more info
"""Simple macros created by recording actions

This plugin provides macro recording
"""

import os

import wx
from wx.lib.pubsub import Publisher

from peppy.yapsy.plugins import *

from peppy.actions import *
from peppy.actions.minibuffer import *
from peppy.major import MajorMode
from peppy.minor import *
from peppy.lib.multikey import *
from peppy.debug import *
import peppy.vfs as vfs
from peppy.vfs.itools.vfs.memfs import MemFS, MemFile, MemDir, TempFile


class CharEvent(FakeCharEvent):
    """Fake character event used by L{RecordKeyboardAction} when generating
    scripted copies of an action list.
    
    """
    def __init__(self, key, unicode, modifiers):
        self.id = -1
        self.event_object = None
        self.keycode = key
        self.unicode = unicode
        self.modifiers = modifiers
        self.is_quoted = True
    
    @classmethod
    def getScripted(cls, evt):
        """Returns a string that represents the python code to instantiate
        the object.
        
        Used when serializing a L{RecordedKeyboardAction} to a python string
        """
        return "%s(%d, %d, %d)" % (cls.__name__, evt.GetKeyCode(), evt.GetUnicodeKey(), evt.GetModifiers())


class RecordedKeyboardAction(RecordedAction):
    """Subclass of L{RecordedAction} for keyboard events.
    
    """
    def __init__(self, action, evt, multiplier):
        RecordedAction.__init__(self, action, multiplier)
        self.evt = FakeCharEvent(evt)
        
        # Hack to force SelfInsertCommand to process the character, because
        # normally it uses the evt.Skip() to force the EVT_CHAR handler to
        # insert the character.
        self.evt.is_quoted = True
    
    def __str__(self):
        return "%s: %dx%s" % (self.actioncls.__name__, self.multiplier, self.evt.GetKeyCode())
    
    def performAction(self, system_state):
        action = self.actioncls(system_state.frame, mode=system_state.mode)
        action.actionKeystroke(self.evt, self.multiplier)
    
    def getScripted(self):
        return "%s(frame, mode).actionKeystroke(%s, %d)" % (self.actioncls.__name__, CharEvent.getScripted(self.evt), self.multiplier)


class RecordedMenuAction(RecordedAction):
    """Subclass of L{RecordedAction} for menu events.
    
    """
    def __init__(self, action, index, multiplier):
        RecordedAction.__init__(self, action, multiplier)
        self.index = index
    
    def __str__(self):
        return "%s x%d, index=%s" % (self.actioncls.__name__, self.multiplier, self.index)
    
    def performAction(self, system_state):
        action = self.actioncls(system_state.frame, mode=system_state.mode)
        action.action(self.index, self.multiplier)
    
    def getScripted(self):
        return "%s(frame, mode).action(%d, %d)" % (self.index, self.multiplier)


class ActionRecorder(AbstractActionRecorder, debugmixin):
    """Creates, maintains and plays back a list of actions recorded from the
    user's interaction with a major mode.
    
    """
    def __init__(self):
        self.recording = []
    
    def __str__(self):
        summary = ''
        count = 0
        for recorded_item in self.recording:
            if hasattr(recorded_item, 'text'):
                summary += recorded_item.text + " "
                if len(summary) > 50:
                    summary = summary[0:50] + "..."
            count += 1
        if len(summary) == 0:
            summary = "untitled"
        return MacroFS.escapeFileName(summary)
        
    def details(self):
        """Get a list of actions that have been recorded.
        
        Primarily used for debugging, there is no way to use this list to
        play back the list of actions.
        """
        lines = []
        for recorded_item in self.recording:
            lines.append(str(recorded_item))
        return "\n".join(lines)
        
    def recordKeystroke(self, action, evt, multiplier):
        if action.isRecordable():
            record = RecordedKeyboardAction(action, evt, multiplier)
            self.appendRecord(record)
    
    def recordMenu(self, action, index, multiplier):
        if action.isRecordable():
            record = RecordedMenuAction(action, index, multiplier)
            self.appendRecord(record)
    
    def appendRecord(self, record):
        """Utility method to add a recordable action to the current list
        
        This method checks for the coalescability of the record with the
        previous record, and it is merged if possible.
        
        @param record: L{RecordedAction} instance
        """
        self.dprint("adding %s" % record)
        if self.recording:
            last = self.recording[-1]
            if last.canCoalesceActions(record):
                self.recording.pop()
                record = last.coalesceActions(record)
                self.dprint("coalesced into %s" % record)
        self.recording.append(record)
    
    def getRecordedActions(self):
        return self.recording
    
    def playback(self, frame, mode, multiplier=1):
        mode.BeginUndoAction()
        state = MacroPlaybackState(frame, mode)
        self.dprint(state)
        SelectAction.debuglevel = 1
        while multiplier > 0:
            for recorded_action in self.getRecordedActions():
                recorded_action.performAction(state)
            multiplier -= 1
        SelectAction.debuglevel = 0
        mode.EndUndoAction()


class PythonScriptableMacro(MemFile):
    """A list of serialized SelectAction commands used in playing back macros.
    
    This object contains python code in the form of text strings that
    provide a way to reproduce the effects of a previously recorded macro.
    Additionally, since they are in plain text, they may be carefully edited
    by the user to provide additional functionality that is not possible only
    using the record capability.
    
    The generated python script looks like the following:
    
    SelfInsertCommand(frame, mode).actionKeystroke(CharEvent(97, 97, 0), 1)
    BeginningTextOfLine(frame, mode).actionKeystroke(CharEvent(65, 65, 2), 1)
    SelfInsertCommand(frame, mode).actionKeystroke(CharEvent(98, 98, 0), 1)
    ElectricReturn(frame, mode).actionKeystroke(CharEvent(13, 13, 0), 1)
    
    where the actions are listed, one per line, by their python class name.
    The statements are C{exec}'d in in the global namespace, but have a
    constructed local namespace that includes C{frame} and C{mode} representing
    the current L{BufferFrame} and L{MajorMode} instance, respectively.
    """
    def __init__(self, recorder=None, name=None):
        """Converts the list of recorded actions into python string form.
        
        """
        if isinstance(recorder, str):
            data = recorder
        elif recorder:
            name = str(recorder)
            data = self.getScriptFromRecorder(recorder)
        else:
            data = ""
        
        if name is None:
            name = "untitled"
        MemFile.__init__(self, data, name)
    
    def __str__(self):
        return self.name
    
    def setName(self, name):
        """Changes the name of the macro to the supplied string.
        
        """
        self.name = name
    
    def getScriptFromRecorder(self, recorder):
        """Converts the list of recorded actions into a python script that can
        be executed by the L(playback) method.
        
        Calls the L{RecordAction.getScripted} method of each recorded action to
        generate the python script version of the action.
        
        @returns: a multi-line string, exec-able using the L{playback} method
        """
        script = ""
        lines = []
        for recorded_action in recorder.getRecordedActions():
            lines.append(recorded_action.getScripted())
        script += "\n".join(lines) + "\n"
        return script
    
    def playback(self, frame, mode, multiplier=1):
        """Plays back the list of actions.
        
        Uses the current frame and mode as local variables for the python
        scripted version of the action list.
        """
        local = {'mode': mode,
                 'frame': frame,
                 }
        self.addActionsToLocal(local)
        if hasattr(mode, 'BeginUndoAction'):
            mode.BeginUndoAction()
        mode.beginProcessingMacro()
        try:
            while multiplier > 0:
                exec self.data in globals(), local
                multiplier -= 1
        except Exception, e:
            import traceback
            error = "Error in macro %s:\n%s\n\n" % (self.name, traceback.format_exc())
            Publisher().sendMessage('peppy.log.info', (frame, error))
        finally:
            mode.endProcessingMacro()
            if hasattr(mode, 'BeginUndoAction'):
                mode.EndUndoAction()
    
    def addActionsToLocal(self, local):
        """Sets up the local environment for the exec call
        
        All the possible actions must be placed in the local environment for
        the call to exec.
        """
        actions = MacroAction.getAllKnownActions()
        for action in actions:
            local[action.__name__] = action
        actions = SelectAction.getAllKnownActions()
        for action in actions:
            local[action.__name__] = action



class StartRecordingMacro(SelectAction):
    """Begin recording actions"""
    name = "Start Recording"
    key_bindings = {'default': "S-C-9", 'mac': "^S-9", 'emacs': ["C-x S-9", "S-C-9"]}
    default_menu = (("Tools/Macros", -800), 100)
    
    def action(self, index=-1, multiplier=1):
        self.frame.root_accel.startRecordingActions(ActionRecorder())
        self.mode.setStatusText("Recording macro...")


class StopRecordingMixin(object):
    def stopRecording(self):
        if self.frame.root_accel.isRecordingActions():
            recorder = self.frame.root_accel.stopRecordingActions()
            self.dprint(recorder)
            macro = MacroFS.addMacroFromRecording(recorder, self.mode)
            RecentMacros.append(macro)
            self.mode.setStatusText("Stopped recording macro.")

class StopRecordingMacro(StopRecordingMixin, SelectAction):
    """Stop recording actions"""
    name = "Stop Recording"
    key_bindings = {'default': "S-C-0", 'mac': "^S-0", 'emacs': ["C-x S-0", "S-C-0"]}
    default_menu = ("Tools/Macros", 110)
    
    @classmethod
    def isRecordable(cls):
        return False
    
    def action(self, index=-1, multiplier=1):
        self.stopRecording()


class ReplayLastMacro(StopRecordingMixin, SelectAction):
    """Play back last macro that was recorded"""
    name = "Play Last Macro"
    key_bindings = {'default': "S-C-8", 'mac': "^S-8", 'emacs': ["C-x e", "S-C-8"]}
    default_menu = ("Tools/Macros", 120)
    
    def isEnabled(self):
        return RecentMacros.isEnabled()
    
    @classmethod
    def isRecordable(cls):
        return False
    
    def action(self, index=-1, multiplier=1):
        self.stopRecording()
        macro = RecentMacros.getLastMacro()
        if macro:
            self.dprint("Playing back %s" % macro)
            wx.CallAfter(macro.playback, self.frame, self.mode, multiplier)
        else:
            self.dprint("No recorded macro.")


class MacroNameMinibufferMixin(object):
    def getMacroPathMap(self):
        """Generate list of possible names to complete.

        For all the currently active actions, find all the names and
        aliases under which the action could be called, and add them
        to the list of possible completions.
        
        @returns: tuple containing a list and a dict.  The list contains the
        precedence of paths which is used to determine which duplicates are
        marked as auxiliary names.  The dict contains a mapping of the path to
        the macros in that path.
        """
        raise NotImplementedError
        
    def createList(self):
        """Generate list of possible macro names to complete.

        Uses L{getMacroPathMap} to get the set of macro names on which to
        complete.  Completes on macro names, not path names, so duplicate
        macro names would be possible.  Gets around any possible duplication
        by using the macro path order to get the hierarchy of paths, and any
        duplicates are marked with the path name.
        
        So, if we are in Python mode and there are macros "macro:Python/test"
        and "macro:Fundamental/test", the Python mode macro would be marked
        as simply "test", while the fundamental mode macro would be marked as
        "test (Fundamental)" to mark the distinction.
        """
        self.map = {}
        path_order, macros = self.getMacroPathMap()
        for path in path_order:
            for name in macros[path]:
                #dprint("name = %s" % name)
                macro_path = "%s/%s" % (path, name)
                if name in self.map:
                    name = "%s (%s)" % (name, path)
                self.map[name] = macro_path
        self.sorted = self.map.keys()
        self.sorted.sort()
        self.dprint(self.sorted)

    def action(self, index=-1, multiplier=1):
        # FIXME: ignoring number right now
        self.createList()
        minibuffer = StaticListCompletionMinibuffer(self.mode, self,
                                                    label = "Execute Macro",
                                                    list = self.sorted,
                                                    initial = "")
        self.mode.setMinibuffer(minibuffer)

class ExecuteMacroByName(MacroNameMinibufferMixin, SelectAction):
    """Execute a macro by name
    
    Using the tab completion minibuffer, execute an action by its name.  The
    actions shown in the minibuffer will be limited to the actions relevant to
    the current major mode.
    """
    name = "&Execute Macro"
    key_bindings = {'default': "S-C-7", 'emacs': "C-c e", }
    default_menu = ("Tools/Macros", 130)
    
    def getMacroPathMap(self):
        hierarchy = self.mode.getSubclassHierarchy()
        #dprint(hierarchy)
        path_map = {}
        path_order = []
        for modecls in hierarchy:
            path, names = MacroFS.getMacroNamesFromMajorModeClass(modecls)
            path_map[path] = names
            path_order.append(path)
        return path_order, path_map
    
    def processMinibuffer(self, minibuffer, mode, text):
        if text in self.map:
            macro_path = self.map[text]
            macro = MacroFS.getMacro(macro_path)
            if macro:
                wx.CallAfter(macro.playback, self.frame, self.mode)
        else:
            self.frame.SetStatusText("%s not a known macro" % text)



class RecentMacros(OnDemandGlobalListAction):
    """Play a macro from the list of recently created macros
    
    Maintains a list of the recent macros and runs the selected macro if chosen
    out of the submenu.
    
    Macros are stored as a list of L{PythonScriptableMacro}s in most-recent to
    least recent order.
    """
    name = "Recent Macros"
    default_menu = ("Tools/Macros", -200)
    inline = False
    
    storage = []
    
    @classmethod
    def isEnabled(cls):
        return bool(cls.storage)
    
    @classmethod
    def append(cls, macro):
        """Adds the macro to the list of recent macros.
        
        """
        cls.storage[0:0] = (macro.name, )
        cls.trimStorage(MacroPlugin.classprefs.list_length)
        cls.calcHash()
    
    @classmethod
    def validateAll(cls):
        """Update the list to contain only valid macros.
        
        This is used after rearranging the macro file system.
        """
        valid_macros = []
        for name in cls.storage:
            macro = MacroFS.getMacro(name)
            if macro:
                valid_macros.append(name)
        cls.setStorage(valid_macros)
    
    @classmethod
    def setStorage(cls, array):
        cls.storage = array
        cls.trimStorage(MacroPlugin.classprefs.list_length)
        cls.calcHash()
        
    @classmethod
    def getLastMacro(cls):
        """Return the most recently added macro
        
        @returns L{PythonScriptableMacro} instance, or None if no macro has yet
        been added.
        """
        if cls.storage:
            name = cls.storage[0]
            return MacroFS.getMacro(name)
        return None
    
    def action(self, index=-1, multiplier=1):
        name = self.storage[index]
        macro = MacroFS.getMacro(name)
        assert self.dprint("replaying macro %s" % macro)
        wx.CallAfter(macro.playback, self.frame, self.mode, 1)


class MacroSaveData(object):
    """Data transfer object to serialize the state of the macro system"""
    
    version = 1
    
    def __init__(self):
        self.macros = MacroFS.macros
        self.recent = RecentMacros.storage
    
    @classmethod
    def load(cls, url):
        import cPickle as pickle
        
        # Note: because plugins are loaded using the execfile command, pickle
        # can't find classes that are in the global namespace.  Have to supply
        # PythonScriptableMacro into the builtin namespace to get around this.
        import __builtin__
        __builtin__.PythonScriptableMacro = PythonScriptableMacro
        
        if not vfs.exists(url):
            return
        
        fh = vfs.open(url)
        bytes = fh.read()
        fh.close()
        if bytes:
            version, data = pickle.loads(bytes)
            if version == 1:
                cls.unpackVersion1(data)
            else:
                raise RuntimeError("Unknown version of MacroSaveData in %s" % url)
    
    @classmethod
    def unpackVersion1(cls, data):
        root, recent = data
        MacroFS.root = root
        #dprint(MacroFS.macros)
        RecentMacros.setStorage(recent)
    
    @classmethod
    def save(cls, url):
        bytes = cls.packVersion1()
        fh = vfs.open_write(url)
        fh.write(bytes)
        fh.close()
    
    @classmethod
    def packVersion1(cls):
        import cPickle as pickle
        
        # See above for the note about the builtin namespace
        import __builtin__
        __builtin__.PythonScriptableMacro = PythonScriptableMacro
        
        data = (cls.version, (MacroFS.root, RecentMacros.storage))
        #dprint(data)
        pickled = pickle.dumps(data)
        return pickled


class TempMacro(TempFile):
    file_class = PythonScriptableMacro


class MacroFS(MemFS):
    """Filesystem to recognize "macro:macro_name" URLs
    
    This simple filesystem allows URLs in the form of "macro:macro_name", and
    provides the mapping from the macro name to the L{PythonScriptableMacro}
    instance.
    
    On disk, this is serialized as a pickle object of the macro class attribute.
    """
    root = MemDir()
    
    temp_file_class = TempMacro
    
    @classmethod
    def escapeFileName(cls, name):
        name = name.replace("/", " ")
        return name.strip()
    
    @classmethod
    def findAlternateName(cls, dirname, basename):
        """Find alternate name if the requested name already exists
        
        If basename already exists in the directory, appends the emacs-style
        counter <1>, <2>, etc. until an unused filename is found.
        
        @returns: new filename guaranteed to be unique
        """
        if dirname:
            if not dirname.endswith("/"):
                dirname += "/"
        else:
            dirname = ""
        orig_basename = basename
        fullpath = dirname + basename
        count = 0
        existing = True
        while existing:
            parent, existing, name = cls._find(fullpath)
            if existing:
                count += 1
                basename = orig_basename + "<%d>" % count
                fullpath = dirname + basename
        return fullpath, basename
    
    @classmethod
    def addMacro(cls, macro, dirname=None):
        if dirname:
            if not dirname.endswith("/"):
                dirname += "/"
            
            # Make sure the directory exists
            url = vfs.normalize("macro:%s" % dirname)
            needs_mkdir = False
            if vfs.exists(url):
                if vfs.is_file(url):
                    # we have a macro that is the same name as the directory
                    # name.  Rename the file and create the directory.
                    components = dirname.strip('/').split('/')
                    filename = components.pop()
                    parent_dirname = "/".join(components)
                    dum, new_filename = cls.findAlternateName(parent_dirname, filename)
                    #dprint("parent=%s filename=%s: New filename: %s" % (parent_dirname, filename, new_filename))
                    parent, existing, name = cls._find(parent_dirname)
                    #dprint("existing=%s" % existing)
                    existing[new_filename] = existing[filename]
                    del existing[filename]
                    #dprint("existing after=%s" % existing)
                    needs_mkdir = True
            else:
                needs_mkdir = True
            if needs_mkdir:
                #dprint("Making folder %s" % url)
                vfs.make_folder(url)
        else:
            dirname = ""
        fullpath, basename = cls.findAlternateName(dirname, macro.name)
        
        parent, existing, name = cls._find(dirname)
        #dprint("name=%s: parent=%s, existing=%s" % (basename, parent, existing))
        macro.setName(fullpath)
        existing[basename] = macro
    
    @classmethod
    def addMacroFromRecording(cls, recorder, mode):
        """Add a macro to the macro: filesystem.
        
        The macro: filesystem is organized by major mode name.  Any macro that
        is defined on the Fundamental mode appears is valid for text modes;
        otherwise, the macros are organized into directories based on mode
        name.
        """
        macro = PythonScriptableMacro(recorder)
        path = mode.keyword
        cls.addMacro(macro, path)
        return macro

    @classmethod
    def getMacro(cls, name):
        parent, macro, name = cls._find(name)
        #dprint(macro)
        return macro

    @classmethod
    def isMacro(cls, name):
        parent, macro, name = cls._find(name)
        return bool(macro)

    @classmethod
    def getMacroNamesFromMajorModeClass(cls, modecls):
        """Get the list of macro names available for the specified major mode
        class.
        
        This is roughly equivalent to using C{vfs.get_names("macro:%s" %
        mode.keyword)} except that it also handles the case of universal
        macros linked to the abstract L{MajorMode} that are in the macro
        directory "".
        
        @param modecls: major mode class
        
        @returns: tuple containing the path in the macro: filesystem and the
        list of all macros in that path
        """
        keyword = modecls.keyword
        if keyword == "Abstract_Major_Mode":
            path = ""
        else:
            path = keyword
        try:
            all_names = vfs.get_names("macro:%s" % path)
        except OSError:
            all_names = []
        
        # Check to see that all the names are macro names and not directories
        macro_names = []
        for name in all_names:
            url = "macro:" + path + "/" + name
            if vfs.is_file(url):
                macro_names.append(name)
        return path, macro_names

    @classmethod
    def get_mimetype(cls, reference):
        path = str(reference.path)
        parent, existing, name = cls._find(path)
        if existing:
            if existing.is_file:
                return "text/x-python"
            return "application/x-not-regular-file"
        raise OSError("[Errno 2] No such file or directory: '%s'" % reference)







class MacroListMinorMode(MinorMode, wx.TreeCtrl):
    """Tree control to display list of macros available for this major mode
    """
    keyword="Macros"
    
    default_classprefs = (
        IntParam('best_width', 300),
        IntParam('best_height', 500),
        BoolParam('springtab', True),
    )
    
    @classmethod
    def worksWithMajorMode(cls, modecls):
        return True

    @classmethod
    def showWithMajorModeInstance(cls, mode=None, **kwargs):
        # It only makes sense to allow macros on modes that you can save
        return mode.isMacroProcessingAvailable()

    def __init__(self, parent, **kwargs):
        if wx.Platform == '__WXMSW__':
            style = wx.TR_HAS_BUTTONS
            self.has_root = True
        else:
            style = wx.TR_HIDE_ROOT|wx.TR_HAS_BUTTONS
            self.has_root = False
        wx.TreeCtrl.__init__(self, parent, -1, size=(self.classprefs.best_width, self.classprefs.best_height), style=style | wx.TR_EDIT_LABELS | wx.TR_MULTIPLE)
        MinorMode.__init__(self, parent, **kwargs)
        self.root = self.AddRoot(_("Macros Compatible with %s") % self.mode.keyword)
        self.hierarchy = None
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)
        self.Bind(wx.EVT_TREE_ITEM_COLLAPSING, self.OnCollapsing)
        self.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self.OnBeginEdit)
        self.Bind(wx.EVT_TREE_END_LABEL_EDIT, self.OnEndEdit)
    
    def activateSpringTab(self):
        """Callback function from the SpringTab handler requesting that we
        initialize ourselves.
        
        """
        self.update()
        
    def update(self, evt=None):
        """Update tree with the source code of the editor"""
        self.DeleteChildren(self.root)
        
        keywords = self.findKeywordHierarchy(self.mode.__class__)
        
        # Getting the names of macros for a specific major mode may fail if no
        # macros exist
        for keyword in keywords:
            self.appendAllFromMajorMode(keyword)
            
        if self.has_root:
            self.Expand(self.root)
        if evt:
            evt.Skip()
    
    def findKeywordHierarchy(self, modecls):
        """Return a list of keywords representing the major mode subclassing
        hierarchy of the current major mode.
        """
        keywords = []
        hierarchy = modecls.getSubclassHierarchy()
        hierarchy.reverse()
        for cls in hierarchy:
            keywords.append(cls.keyword)
        return keywords
        
    def appendAllFromMajorMode(self, keyword):
        """Append all macros for a given major mode
        
        """
        if keyword == "Abstract_Major_Mode":
            keyword = "Universal Macros"
            path = ""
        else:
            path = keyword
        item = self.AppendItem(self.root, _(keyword))
        try:
            names = vfs.get_names("macro:%s" % path)
            self.appendItems(item, path, names)
        except OSError:
            pass
        self.Expand(item)

    def appendItems(self, wxParent, path, names):
        """Append the macro names to the specified item
        
        For the initial item highlighing, uses the current_line instance
        attribute to determine the line number.
        """
        names.sort()
        for name in names:
            if path:
                fullpath = path + "/" + name
            else:
                fullpath = name
            url = "macro:" + fullpath
            if vfs.is_file(url):
                wxItem = self.AppendItem(wxParent, name)
                self.SetPyData(wxItem, fullpath)
            
    def OnActivate(self, evt):
        name = self.GetPyData(evt.GetItem())
        self.dprint("Activating macro %s" % name)
        if name is not None:
            macro = MacroFS.getMacro(name)
            wx.CallAfter(macro.playback, self.getFrame(), self.mode)
    
    def OnCollapsing(self, evt):
        item = evt.GetItem()
        if item == self.root:
            # Don't allow the root item to be collapsed
            evt.Veto()
        evt.Skip()
    
    def OnBeginEdit(self, evt):
        item = evt.GetItem()
        name = self.GetPyData(item)
        if name == None:
            # Only actual macros are allowed to be edited.  Other items in the
            # tree are not macros, so we veto edit requests
            evt.Veto()
    
    def OnEndEdit(self, evt):
        if evt.IsEditCancelled():
            return

        item = evt.GetItem()
        old_path = self.GetPyData(item)
        new_name = evt.GetLabel()
        components = old_path.split('/')
        components.pop()
        dirname = '/'.join(components)
        new_path = dirname + '/' + new_name
        dprint("old=%s new=%s" % (old_path, new_path))
        exists = MacroFS.getMacro(new_name)
        if exists:
            evt.Veto()
            wx.CallAfter(self.frame.showErrorDialog, "Cannot rename %s\%s already exists.")
        else:
            vfs.move("macro:%s" % old_path, "macro:%s" % new_path)
            RecentMacros.validateAll()

    def getSelectedMacros(self):
        """Return a list of all the selected macros
        
        @returns: a list containing the full path to the macro (note: it is not
        the url; it doesn't include the leading 'macro:')
        """
        paths = []
        for item in self.GetSelections():
            path = self.GetPyData(item)
            if path is not None:
                paths.append(path)
        return paths

    def getOptionsForPopupActions(self):
        options = {
            'minor_mode': self,
            'macros': self.getSelectedMacros(),
            }
        return options
    
    def getPopupActions(self, evt, x, y):
        return [EditMacro, RenameMacro, (-900, DeleteMacro)]


class EditMacro(SelectAction):
    """Edit the macro in a new tab.
    
    """
    name = "Edit Macro"

    def action(self, index=-1, multiplier=1):
        dprint(self.popup_options)
        for path in self.popup_options['macros']:
            url = "macro:%s" % path
            self.frame.open(url)


class RenameMacro(SelectAction):
    """Rename the selected macros.
    
    """
    name = "Rename Macro"

    def action(self, index=-1, multiplier=1):
        tree = self.popup_options['minor_mode']
        items = tree.GetSelections()
        if items:
            tree.EditLabel(items[0])


class DeleteMacro(SelectAction):
    """Delete the selected macros.
    
    """
    name = "Delete Macro"

    def action(self, index=-1, multiplier=1):
        dprint(self.popup_options)
        wx.CallAfter(self.processDelete)
    
    def processDelete(self):
        tree = self.popup_options['minor_mode']
        macros = tree.getSelectedMacros()
        retval = self.frame.showQuestionDialog("Are you sure you want to delete:\n\n%s" % "\n".join(macros))
        if retval == wx.ID_YES:
            for macro in macros:
                dprint("removing %s" % macro)
                vfs.remove("macro:%s" % macro)
            tree.update()
            RecentMacros.validateAll()



class MacroPlugin(IPeppyPlugin):
    """Plugin providing the macro recording capability
    """
    default_classprefs = (
        StrParam('macro_file', 'macros.dat', 'File name in main peppy configuration directory used to store macro definitions'),
        IntParam('list_length', 3, 'Number of macros to save in the Recent Macros list'),
        )

    def activateHook(self):
        vfs.register_file_system('macro', MacroFS)

    def initialActivation(self):
        pathname = wx.GetApp().getConfigFilePath(self.classprefs.macro_file)
        macro_url = vfs.normalize(pathname)
        try:
            MacroSaveData.load(macro_url)
        except:
            dprint("Failed loading macro data to %s" % macro_url)
            import traceback
            traceback.print_exc()

    def requestedShutdown(self):
        pathname = wx.GetApp().getConfigFilePath(self.classprefs.macro_file)
        macro_url = vfs.normalize(pathname)
        try:
            MacroSaveData.save(macro_url)
        except:
            dprint("Failed saving macro data to %s" % macro_url)
            import traceback
            traceback.print_exc()
            pass

    def deactivateHook(self):
        vfs.deregister_file_system('macro')
        
    def getMinorModes(self):
        yield MacroListMinorMode
        
    def getActions(self):
        return [
            StartRecordingMacro, StopRecordingMacro, ReplayLastMacro,
            
            RecentMacros, ExecuteMacroByName,
            ]
