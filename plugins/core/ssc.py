# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/ssc.py
#
# File Description: a plugin to save settings that should not stay in memory
#
# By: Bast
"""
this plugin is for saving settings that should not appear in memory
the setting is saved to a file with read only permissions for the user
the proxy is running under

## Using
See the source for [net.proxy](/bastproxy/plugins/net/proxy.html)
for an example of using this plugin

'''python
    ssc = self.plugin.api('plugins.core.ssc:baseclass.get')()
    self.plugin.apikey = ssc('somepassword', self, desc='Password for something')
'''
"""
# Standard Library
import os
import stat

# 3rd Party

# Project
from libs.api import API
from libs.records import LogRecord
from libs.commands import AddCommand, AddParser, AddArgument
from plugins._baseplugin import BasePlugin

NAME = 'Secret Setting Class'
SNAME = 'ssc'
PURPOSE = 'Class to save settings that should not stay in memory'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class SSC(object):
    """
    a class to manage settings
    """
    def __init__(self, name, plugin_id, **kwargs):
        """
        initialize the class
        """
        self.name = name
        self.api = API(owner_id=f"{plugin_id}:{name}")
        self.plugin_id = plugin_id

        self.default = kwargs.get('default', '')
        self.desc = kwargs.get('desc', 'setting')
        plugin_instance = self.api('plugins.core.pluginm:get.plugin.instance')(self.plugin_id)
        plugin_instance.api('libs.api:add')(self.plugin_id, f"ssc.{self.name}", self.getss)

    # read the secret from a file
    def getss(self, quiet=False):
        """
        read the secret from a file
        """
        first_line = ''
        plugin_instance = self.api('plugins.core.pluginm:get.plugin.instance')(self.plugin_id)
        file_name = os.path.join(plugin_instance.save_directory, self.name)
        try:
            with open(file_name, 'r') as fileo:
                first_line = fileo.readline()

            return first_line.strip()
        except IOError:
            if not quiet:
                LogRecord(f"getss - Please set the {self.desc} with {plugin_instance.api('plugins.core.commands:get.command.format')(self.plugin_id, self.name)}",
                          level='warning', sources=[self.plugin_id])()

        return self.default

    @AddCommand(dynamic_name="{name}")
    @AddParser(description="set the {desc}")
    @AddArgument('value',
                    help='the new {desc}',
                    default='',
                    nargs='?')
    def _command_setssc(self):
        """
        set the secret
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        if args['value']:
            plugin_instance = self.api('plugins.core.pluginm:get.plugin.instance')(self.plugin_id)
            file_name = os.path.join(plugin_instance.save_directory, self.name)
            data_file = open(file_name, 'w')
            data_file.write(args['value'])
            os.chmod(file_name, stat.S_IRUSR | stat.S_IWUSR)
            return True, [f"{self.desc} saved"]

        return True, [f"Please enter the {self.desc}"]

class Plugin(BasePlugin):
    """
    a plugin to handle secret settings
    """
    def __init__(self, *args, **kwargs):
        BasePlugin.__init__(self, *args, **kwargs)

        self.reload_dependents_f = True

        self.api('libs.api:add')(self.plugin_id, 'baseclass.get', self.api_baseclass)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

    # return the secret setting baseclass
    def api_baseclass(self):
        # pylint: disable=no-self-use
        """
        return the sql baseclass
        """
        return SSC
