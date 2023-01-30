# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/persistentdict.py
#
# File Description: setup logging with some customizations
#
# By: Bast
"""
a module that holds a persistent dictionary implementation
it saves the dict to a file
"""

# Standard Library
import pickle
import json
import os
import shutil
import stat

# Third Party

# Project
from libs.api import API
#api = API()

def convert(tinput):
    """
    converts input to ascii (utf-8)
    """
    if isinstance(tinput, dict):
        return {convert(key): convert(value) for key, value in tinput.items()}
    elif isinstance(tinput, list):
        return [convert(element) for element in tinput]
    elif isinstance(tinput, str):
        return tinput
    elif isinstance(tinput, bytes):
        return str(tinput)

    return tinput

def convert_keys_to_int(tdict):
    """
    convert all keys in int if they are numbers
    """
    new = {}
    for i in tdict:
        nkey = i
        try:
            nkey = int(i)
        except ValueError:
            pass
        ndata = tdict[i]
        if isinstance(tdict[i], dict):
            ndata = convert_keys_to_int(tdict[i])
        new[nkey] = ndata
    return new

class PersistentDict(dict):
    ''' Persistent dictionary with an API compatible with shelve and anydbm.

    The dict is kept in memory, so the dictionary operations run as fast as
    a regular dictionary.

    Write to disk is delayed until close or sync (similar to gdbm's fast mode).

    Input file format is automatically discovered.
    Output file format is selectable between pickle and json
    All three serialization formats are backed by fast C implementations.

    '''
    def __init__(self, file_name, flag='c', mode=None,
                 tformat='json', *args, **kwds):
        """
        initialize the instance
        """
        self._dump_shallow_attrs = ['api']
        self.api = API()

        # r=readonly, c=create, or n=new
        self.flag = flag

        # None or an octal triple like 0644
        self.mode = (stat.S_IWUSR | stat.S_IRUSR) or mode

        # json', or 'pickle'
        self.format = tformat
        self.file_name = file_name
        self.pload()
        dict.__init__(self, *args, **kwds)

    def sync(self):
        """
        write data to disk
        """
        if self.flag == 'r':
            return
        temp_name = self.file_name + '.tmp'

        try:
            self.dump(temp_name)
        except Exception:
            os.remove(temp_name)
            raise
        finally:
            shutil.move(temp_name, self.file_name)    # atomic commit
        if self.mode is not None:
            os.chmod(self.file_name, self.mode)

    def close(self):
        """
        close the file
        """
        self.sync()

    def __enter__(self):
        """
        ????
        """
        return self

    def __exit__(self, *exc_info):
        """
        close the file
        """
        self.close()

    def dump(self, file_object):
        """
        dump the file
        """
        if self.format == 'json':
            with open(file_object, mode='w', encoding='utf-8') as f:
                json.dump(self, f, separators=(',', ':'), skipkeys=True, indent=2)
        elif self.format == 'pickle':
            with open(file_object, 'wb') as f:
                pickle.dump(dict(self), f, 2)
        else:
            raise NotImplementedError('Unknown format: ' + repr(self.format))

    def pload(self):
        """
        load from file
        """
        # try formats from most restrictive to least restrictive
        if os.path.exists(self.file_name):
            if self.flag != 'n' and os.access(self.file_name, os.R_OK):
                self.load()

    def load(self):
        """
        load the dictionary
        """
        tstuff = {}
        if not os.path.exists(self.file_name):
            return
        try:
            if self.format == 'pickle':
                with open(self.file_name, 'rb') as tfile:
                    tstuff = pickle.load(tfile)
            elif self.format == 'json':
                with open(self.file_name, 'r', encoding='utf-8') as tfile:
                    tstuff = json.load(tfile, object_hook=convert)

            nstuff = convert_keys_to_int(tstuff)
            return self.update(nstuff)

        except Exception:  # pylint: disable=broad-except
            #if 'log' not in self.file_name:
            self.api('libs.io:send:traceback')(f"Error when loading {self.format} from {self.file_name}")
            #else:
            #  pass

        raise ValueError('File not in a supported format')

    def __setitem__(self, key, val):
        """
        override setitem
        """
        try:
            key = int(key)
        except ValueError:
            key = convert(key)
        val = convert(val)
        super().__setitem__(key, val)

    def update(self, *args, **kwargs):
        """
        override update
        """
        for k, val in dict(*args, **kwargs).items():
            self[k] = val

    def __deepcopy__(self, memo):
        return self

class PersistentDictEvent(PersistentDict):
    """
    a class to send events when a dictionary object is set
    """
    def __init__(self, plugin_instance, file_name, *args, **kwds):
        """
        init the class
        """
        self.plugin_instance = plugin_instance
        super().__init__(file_name, *args, **kwds)

    def __setitem__(self, key, val):
        """
        override setitem
        """
        key = convert(key)
        val = convert(val)
        old_value = None
        if key in self:
            old_value = self.plugin_instance.api('setting:get')(key)
        if old_value != val:
            dict.__setitem__(self, key, val)

            event_name = f"ev_{self.plugin_instance.plugin_id}_var_{key}_modified"
            if not self.plugin_instance.reset_f and key != '_version':
                self.plugin_instance.api('core.events:raise:event')(
                    event_name,
                    {'var':key,
                     'newvalue':self.plugin_instance.api('setting:get')(key),
                     'oldvalue':old_value})

    def raiseall(self):
        """
        go through and raise a ev_<plugin>_var_<setting>_modified event for each setting
        """
        for i in self:
            event_name = f"ev_{self.plugin_instance.plugin_id}_var_{i}_modified"
            if not self.plugin_instance.reset_f and i != '_version':
                self.plugin_instance.api('core.events:raise:event')(
                    event_name,
                    {'var':i,
                     'newvalue':self.plugin_instance.api('setting:get')(i),
                     'oldvalue':'__init__'})

    def sync(self):
        """
        always put plugin version in here
        """
        try:
            self['_version'] = self.plugin_instance.version
        except AttributeError:
            pass

        super().sync()