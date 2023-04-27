# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/change.py
#
# File Description: Holds the change record type
#
# By: Bast
"""
Holds the change record type
"""
# Standard Library
from uuid import uuid4
import datetime
import traceback
import pprint

# 3rd Party

# Project
from libs.api import API

class UpdateRecord(object):
    """
    a update event for a record
    flag: one of 'Modify', 'Set Flag', 'Info'
    action: a description of what was updated
    actor: the item that send the update (likely a plugin)
    extra: any extra info about this update
    data: the new data

    will automatically add the time and last 5 stack frames
    """
    def __init__(self, parent, flag: str, action: str, actor: str = '', extra: dict | None = None, data=None):
        self.uuid = uuid4().hex
        self.time_taken = datetime.datetime.now(datetime.timezone.utc)
        self.parent = f"{parent.__class__.__name__}:{parent.uuid}"
        self.flag = flag
        self.api = API(owner_id=f"UpdateRecord:{self.uuid}")
        self.action = action
        self.actor = actor
        self.extra = {}
        if extra:
            self.extra |= extra
        self.data = data
        # Extract the last 7 stack frames
        self.stack = self.fix_stack(traceback.format_stack(limit=10))
        self.event_stack = []
        if self.api('libs.api:has')('plugins.core.events:get.event.stack'):
            self.event_stack = self.api('plugins.core.events:get.event.stack')()

    def fix_stack(self, stack):
        new_stack = []
        # don't need the last 2 lines
        for line in stack:
            new_stack.extend(line.split('\n'))
            if 'addupdate' in line:
                break
        return new_stack

    def __str__(self):
        return f"{self.actor} - {self.flag} - {self.action} - {self.data} - {self.extra})"

    def format(self):
        """
        format the change record
        """
        if self.flag == 'Modify':
            return f"{self.actor} updated {self.action}"
        if self.flag == 'Set Flag':
            return f"{self.actor} set {self.action} to {self.data}"
        if self.flag == 'Info':
            return f"{self.actor} {self.action}"

    def format_detailed(self, show_data: bool = False, show_stack: bool = False,
                        data_lines_to_show: int = 10):
        """
        format the change record
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        if 'show_data' in args:
            show_data = args['show_data']
        if 'show_stack' in args:
            show_stack = args['show_stack']
        if 'data_lines_to_show' in args:
            data_lines_to_show = int(args['data_lines_to_show'])

        tmsg =  [
            f"{'UUID':<15} : {self.uuid}",
            f"{'Parent':<15} : {self.parent}",
            f"{'Actor':<15} : {self.actor}",
            f"{'Flag':<15} : {self.flag}",
            f"{'Action':<15} : {self.action}",
            f"{'Time Taken':<15} : {self.time_taken}"]
        if self.extra:
            tmsg.append(f"{'Extra':<15} : {self.extra}")
        if self.event_stack:
            tmsg.append(f"{'Event Stack':<15} :",)
            tmsg.extend([f"{'':<15} : {event}" for event in self.event_stack])
        if show_data and self.data is not None:
            if isinstance(self.data, list) and data_lines_to_show != -1:
                data = self.data[:data_lines_to_show]
            else:
                data = self.data
            tmsg.append(f"{'Data':<15} :")
            tmsg.extend(f"{'':<15} : {line}" for line in pprint.pformat(data, width=120).split('\n'))
        if show_stack and self.stack:
            tmsg.append(f"{'Stack':<15} :")
            tmsg.extend([f"{'':<15} {line}" for line in self.stack if line.strip()])

        return tmsg
