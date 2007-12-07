import os

from peppy.vfs.itools.datatypes import FileName
from peppy.vfs.itools.vfs import *
from peppy.vfs.itools.vfs.registry import get_file_system, deregister_file_system
from peppy.vfs.itools.uri import *
from peppy.vfs.itools.vfs.base import BaseFS

import peppy.vfs.mem
import peppy.vfs.http
import peppy.vfs.tar

def normalize(ref, base=None):
    """Normalize a url string into a reference and fix windows shenanigans"""
    if not isinstance(ref, Reference):
        ref = get_reference(ref)
    # Check the reference is absolute
    if ref.scheme:
        return ref
    # Default to the current working directory
    if base is None:
        base = os.getcwd()
    
    # URLs always use /
    if os.path.sep == '\\':
        base = base.replace(os.path.sep, '/')
    # Check windows drive letters
    if base[1] == ':':
        base = "%s:%s" % (base[0].lower(), base[2:])
    baseref = get_reference('file://%s/' % base)
    return baseref.resolve(ref)

def canonical_reference(ref):
    """Normalize a uri but remove any query string or fragments."""
    # get a copy of the reference
    ref = normalize(str(ref))
    ref.query = {}
    ref.fragment = ''
    
    # make sure that any path that points to a folder ends with a slash
    if is_folder(ref):
        ref.path.endswith_slash = True
    return ref
    

# Simple cache of files.  FIXME: restrict the list to only keep the last few
# files in memory.
cache = {}
def find_cached(fstype, path):
    if fstype in cache:
        subcache = cache[fstype]
        if path in subcache:
            return subcache[path]
    return None
BaseFS.find_cached = staticmethod(find_cached)

def store_cache(fstype, path, obj):
    if fstype not in cache:
        cache[fstype] = {}
    cache[fstype][path] = obj
BaseFS.store_cache = staticmethod(store_cache)


__all__ = [
    ##### From vfs:
    'BaseFS',
    'FileFS',
    # File modes
    'READ',
    'WRITE',
    'APPEND',
    # Registry
    'register_file_system',
    'deregister_file_system',
    'get_file_system',
    # Functions
    'exists',
    'is_file',
    'is_folder',
    'can_read',
    'can_write',
    'get_ctime',
    'get_mtime',
    'get_atime',
    'get_mimetype',
    'get_size',
    'make_file',
    'make_folder',
    'remove',
    'open',
    'copy',
    'move',
    'get_names',
    'traverse',

    ##### From uri:
    'get_reference',
    'normalize',
    'canonical_reference',
    ]
