# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/cmdq/_cmdq.py
#
# File Description: a command queue plugin
#
# By: Bast

# Standard Library
import re

# 3rd Party

# Project
from libs.records import LogRecord, SendDataDirectlyToMud, NetworkData
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from plugins.core.commands import AddParser
from plugins.core.events import RegisterToEvent
from libs.api import AddAPI

class CMDQPlugin(BasePlugin):
    """
    a plugin to handle sending a command to the mud
    """
    @RegisterPluginHook('__init__')
    def _phook_init_plugin(self):
        self.queue = []
        self.cmds = {}
        self.current_command = {}

        self.reload_dependents_f = True

    @RegisterToEvent(event_name='ev_plugin_unloaded')
    def _eventcb_plugin_unloaded(self):
        """
        a plugin was unloaded
        """
        if event_record := self.api(
            'plugins.core.events:get.current.event.record'
        )():
            self.api(f"{self.plugin_id}:remove.mud.commands.for.plugin")(event_record['plugin_id'])

    @AddAPI('remove.mud.commands.for.plugin', description='remove all mud commands related to a plugin')
    def _api_remove_mud_commands_for_plugin(self, plugin_id):
        """  remove all commands related to a plugin
        @Yplugin_id@w   = The plugin name

        this function returns no values"""
        LogRecord(f"_api_remove_commands_for_plugin - removing cmdq data for plugin {plugin_id}",
                  level='debug', sources=[self.plugin_id, plugin_id])()
        tkeys = self.cmds.keys()
        for i in tkeys: # iterate keys since we are deleting things
            if self.cmds[i]['owner'] == plugin_id:
                self.api(f"{self.plugin_id}:remove.command.type")(i)

    @AddAPI('type.remove', description='remove a command type')
    def _api_type_remove(self, cmdtype):
        """
        remove a command
        """
        if cmdtype in self.cmds:
            del self.cmds[cmdtype]
        else:
            LogRecord(f"_api_command_type_remove - {cmdtype} not found",
                      level='debug', sources=[self.plugin_id])()

    @AddAPI('start', description='tell the plugin a command has started')
    def _api_start(self, cmdtype):
        """
        tell the plugin a command has started
        """
        if self.current_command and cmdtype != self.current_command['ctype']:
            LogRecord(f"_api_command_start - got command start for {cmdtype} and it's not the current cmd: {self.current_command['ctype']}",
                      level='error', sources=[self.plugin_id])()
            return
        self.api('libs.timing:timing.start')(f"cmd_{cmdtype}")

    @AddAPI('type.add', description='add a command type')
    def _api_type_add(self, cmdtype, cmd, regex, **kwargs):
        """
        add a command type
        """
        owner = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])
        beforef = kwargs.get('beforef', None)
        afterf = kwargs.get('afterf', None)
        if 'plugin' in kwargs:
            owner = kwargs['owner']
        if cmdtype not in self.cmds:
            self.cmds[cmdtype] = {'cmd': cmd,
                                  'regex': regex,
                                  'cregex': re.compile(regex),
                                  'beforef': beforef,
                                  'afterf': afterf,
                                  'ctype': cmdtype,
                                  'owner': owner}

            self.api('plugins.core.events:add.event')(f"cmd_{self.current_command['ctype']}_send", self.cmds[cmdtype]['owner'],
                                                        description=[f"event for the command {self.cmds[cmdtype]['ctype']} being sent"],
                                                        arg_descriptions={'None': None})
            self.api('plugins.core.events:add.event')(f"cmd_{self.current_command['ctype']}_completed", self.cmds[cmdtype]['owner'],
                                                        description=[f"event for the command {self.cmds[cmdtype]['ctype']} completing"],
                                                        arg_descriptions={'None': None})

    def sendnext(self):
        """
        send the next command
        """
        LogRecord(
            "sendnext - checking queue", level='debug', sources=[self.plugin_id]
        )()
        if not self.queue or self.current_command:
            return

        cmdt = self.queue.pop(0)
        cmd = cmdt['cmd']
        cmdtype = cmdt['ctype']
        LogRecord(f"sendnext - sending cmd: {cmd} ({cmdtype})",
                  level='debug', sources=[self.plugin_id])()

        if cmdtype in self.cmds and self.cmds[cmdtype]['beforef']:
            self.cmds[cmdtype]['beforef']()

        self.current_command = cmdt
        self.api('plugins.core.events:raise.event')(f"cmd_{self.current_command['ctype']}_send")
        SendDataDirectlyToMud(NetworkData(cmd), show_in_history=False)()

    def checkinqueue(self, cmd):
        """
        check for a command in the queue
        """
        return any(i['cmd'] == cmd for i in self.queue)

    @AddAPI('finish', description='tell the plugin a command has finished')
    def _api_finish(self, cmdtype):
        """
        tell the plugin that a command has finished
        """
        LogRecord(f"_api_command_finish - got command finish for {cmdtype}",
                  level='debug',
                  sources=[self.plugin_id])(actor=f"{self.plugin_id}:_api_command_finish")
        if not self.current_command:
            return
        if cmdtype == self.current_command['ctype']:
            if cmdtype in self.cmds and self.cmds[cmdtype]['afterf']:
                LogRecord(f"_api_command_finish - running afterf for {cmdtype}",
                          level='debug', sources=[self.plugin_id])()
                self.cmds[cmdtype]['afterf']()

            self.api('libs.timing:timing.finish')(f"cmd_{self.current_command['ctype']}")
            self.api('plugins.core.events:raise.event')(f"cmd_{self.current_command['ctype']}_completed")
            self.current_command = {}
            self.sendnext()

    @AddAPI('queue.add.command', description='add a command to the plugin')
    def _api_queue_add_command(self, cmdtype, arguments=''):
        """
        add a command to the queue
        """
        plugin = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])
        cmd = self.cmds[cmdtype]['cmd']
        if arguments:
            cmd = f'{cmd} {str(arguments)}'
        if self.checkinqueue(cmd) or \
                        ('cmd' in self.current_command and self.current_command['cmd'] == cmd):
            return
        LogRecord(f"_api_queue_add_command - adding {cmd} to queue",
                  level='debug', sources=[self.plugin_id])()
        self.queue.append({'cmd':cmd, 'ctype':cmdtype, 'plugin':plugin})
        if not self.current_command:
            self.sendnext()

    def resetqueue(self, _=None):
        """
        reset the queue
        """
        self.queue = []

    @AddParser(description='drop the last command')
    def _command_fixqueue(self):
        """
        finish the last command
        """
        if self.current_command:
            self.api('libs.timing:timing.finish')(f"cmd_{self.current_command['ctype']}")
            self.current_command = {}
            self.sendnext()

        return True, ['finished the currentcmd']
