# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/event.py
#
# File Description: Holds base classes for event items
#
# By: Bast
"""
Holds base classes for an event to raise

The created_by attribute is the name of the plugin or module that created the event
It can be updated in two ways, by using the api plugins.core.events:add:event
    or when the event is raised and a calledfrom argument is passed and created_by is not already been set
"""
# Standard Library
import typing
import datetime

# 3rd Party

# Project
from libs.api import API
from libs.records import LogRecord, EventArgsRecord
from libs.callback import Callback
from libs.queue import SimpleQueue

class RegisterToEvent:
    """
    a class to decorate a function with command data
    """
    def __init__(self, **kwargs):
        """
        kwargs:
            event_name: the event to register to
            priority: the priority to register the function with (Default: 50)
        """
        self.registration_args = {'event_name':'', 'priority':50} | kwargs

    def __call__(self, func):
        if not hasattr(func, 'event_registration'):
            func.event_registration = []
        func.event_registration.append(self.registration_args)

        return func

class Event:
    """
    a base class for an event and it's arguments
    """
    def __init__(self, name: str, created_by: str ='', description: list | None = None, arg_descriptions: dict[str, str] | None = None):
        self.name: str = name
        self.owner_id: str = f"{__name__}:{self.name}"
        self.api = API(owner_id=self.owner_id)
        # this is the plugin or module that created the event
        # it should be the __name__ of the module or plugin
        self.created_by: str = created_by
        self.priority_dictionary = {}
        self.raised_count = 0
        self.description = description or []
        self.arg_descriptions = arg_descriptions or {}
        self.current_record: EventArgsRecord | None = None
        self.call_stacks = SimpleQueue(length=10)

    def count(self) -> int:
        """
        return the number of functions registered to this event
        """
        return sum(len(v) for v in self.priority_dictionary.values())

    def isregistered(self, func) -> bool:
        """
        check if a function is registered to this event
        """
        return any(
            func in self.priority_dictionary[priority]
            for priority in self.priority_dictionary
        )

    def isempty(self) -> bool:
        """
        check if an event has no functions registered
        """
        return not any(
            self.priority_dictionary[priority]
            for priority in self.priority_dictionary
        )

    def register(self, func: typing.Callable, func_owner_id: str, prio: int = 50) -> bool:
        """
        register a function to this event container
        """
        priority = prio or 50
        if priority not in self.priority_dictionary:
            self.priority_dictionary[priority] = []

        event_function = Callback(func.__name__, func_owner_id, func)

        if event_function not in self.priority_dictionary[priority]:
            self.priority_dictionary[priority].append(event_function)
            LogRecord(f"{self.name} - register function {event_function} with priority {priority}",
                      level='debug', sources=[event_function.owner_id, self.created_by])()
            return True

        return False

    def unregister(self, func) -> bool:
        """
        unregister a function from this event container
        """
        for priority in self.priority_dictionary:
            if func in self.priority_dictionary[priority]:
                event_function = self.priority_dictionary[priority][self.priority_dictionary[priority].index(func)]
                LogRecord(f"unregister - {self.name} - unregister function {event_function} with priority {priority}",
                          level='debug', sources=[event_function.owner_id, self.created_by])()
                self.priority_dictionary[priority].remove(event_function)
                return True

        LogRecord(f"unregister - {self.name} - could not find function {func.__name__}",
                  level='error', sources=[self.created_by])()
        return False

    def getownerregistrations(self, owner_id):
        registrations = []
        for priority in self.priority_dictionary:
            registrations.extend(
                event_function.name
                for event_function in self.priority_dictionary[priority]
                if event_function.owner_id == owner_id
            )
        return registrations

    def removeowner(self, owner_id):
        """
        remove all functions related to a owner
        """
        plugins_to_unregister = []
        for priority in self.priority_dictionary:
            plugins_to_unregister.extend(
                event_function
                for event_function in self.priority_dictionary[priority]
                if event_function.owner_id == owner_id
            )
        for event_function in plugins_to_unregister:
            self.api('plugins.core.events:unregister.from.event')(self.name, event_function.func)

    def detail(self) -> list[str]:
        """
        format a detail of the event
        """
        header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')
        subheader_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_subheader_color')

        description = []
        for i, line in enumerate(self.description):
            if not line:
                continue
            if i == 0:
                description.append(f"{'Description':<13} : {line}")
            else:
                description.append(f"{'':<13}   {line}")

        message: list[str] = [
            f"{'Event':<13} : {self.name}",
            *description,
            f"{'Created by':<13} : {self.created_by}",
            f"{'Raised':<13} : {self.raised_count}",
            '',
            self.api('plugins.core.utils:center.colored.string')(
                '@x86Registrations@w', '-', 60, filler_color=header_color
            ),
            f"{'priority':<13} : {'owner':<25} - function name",
            subheader_color + '-' * 60 + '@w',
        ]
        function_message: list[str] = []
        key_list = self.priority_dictionary.keys()
        key_list = sorted(key_list)
        for priority in key_list:
            function_message.extend(
                f"{priority:<13} : {event_function.owner_id:<25} - {event_function.name}"
                for event_function in self.priority_dictionary[priority]
            )
        if not function_message:
            message.append('None')
        else:
            message.extend(function_message)
        message.extend((header_color + '-' * 60 + '@w', ''))
        message.append(self.api('plugins.core.utils:center.colored.string')('@x86Data Keys@w', '-', 60, filler_color=header_color))
        if self.arg_descriptions and 'None' not in self.arg_descriptions:
            message.extend(
                f"@C{arg:<13}@w : {self.arg_descriptions[arg]}"
                for arg in self.arg_descriptions
            )
        elif 'None' in self.arg_descriptions:
            message.append('None')
        else:
            message.append('Unknown')
        message.append(header_color + '-' * 60 + '@w')

        if self.call_stacks:
            message.append('')
            message.append(self.api('plugins.core.utils:center.colored.string')('@x86Last 10 Call Stacks@w', '-', 60, filler_color=header_color))
            for i, call_stack in enumerate(self.call_stacks.get()):
                if i > 0:
                    message.append('')
                message.append(self.api('plugins.core.utils:center.colored.string')(f'{subheader_color}Stack: {i + 1}@w', '-', 40, filler_color=subheader_color))
                message.append(f"Called from : {call_stack['calledfrom']:<13}@w")
                message.append(f"Timestamp   : {call_stack['timestamp']}@w")
                message.append(self.api('plugins.core.utils:center.colored.string')(f'{subheader_color}Event Stack@w', '-', 40, filler_color=subheader_color))
                message.extend([f"  {event}" for event in call_stack['event_stack']])
                message.append(self.api('plugins.core.utils:center.colored.string')(f'{subheader_color}Function Stack@w', '-', 40, filler_color=subheader_color))
                message.extend([f"{call}" for call in call_stack['call_stack']])
            message.append(header_color + '-' * 60 + '@w')

        return message

    def raise_event(self, data: dict | EventArgsRecord, calledfrom: str) -> EventArgsRecord | None:
        """
        raise this event
        """
        self.raised_count = self.raised_count + 1

        # if the created_by is not set, set it to the calledfrom argument
        if calledfrom and not self.created_by:
            self.created_by = calledfrom

        # Any standard dictionary will be converted to a EventArgsRecord object
        if not data:
            data = {}

        # If data is not a dict or EventArgsRecord object, log an error and the event will not be processed
        if not isinstance(data, EventArgsRecord) and not isinstance(data, dict):
            LogRecord(f"raise_event - event {self.name} raised by {calledfrom} did not pass a dict or EventArgsRecord object",
                        level='error', sources=[calledfrom, self.created_by, 'plugins.core.events'])()
            LogRecord(
                "The event will not be processed",
                level='error',
                sources=[calledfrom, self.created_by, 'plugins.core.events'],
            )()
            return None

        # convert a dict to an EventArgsRecord object
        if not isinstance(data, EventArgsRecord):
            data = EventArgsRecord(owner_id=calledfrom, event_name=self.name, data=data)

        # log the event if the log_savestate setting is True or if the event is not a _savestate event
        log_savestate = self.api('plugins.core.settings:get')('plugins.core.events', 'log_savestate')
        log: bool = True if log_savestate else not self.name.endswith('_savestate')
        if log:
            LogRecord(f"raise_event - event {self.name} raised by {calledfrom} with data {data}",
                      level='debug', sources=[calledfrom, self.created_by])()

        call_stack = {'calledfrom': calledfrom, 'data': data, 'call_stack': self.api('libs.api:stackdump')(),
                      'event_stack':self.api('plugins.core.events:get.event.stack')(),
                      'timestamp':datetime.datetime.now(datetime.timezone.utc)}
        self.call_stacks.enqueue(call_stack)

        self.current_record = data
        if keys := self.priority_dictionary.keys():
            keys = sorted(keys)
            for priority in keys:
                for event_function in self.priority_dictionary[priority][:]:
                    try:
                        # A callback should call the api 'plugins.core.events:get:current:event'
                        # which returns event_name, EventArgsRecord
                        # If the registered event changes the data, it should snapshot it with addupdate
                        event_function.execute()
                    except Exception:  # pylint: disable=broad-except
                        LogRecord(f"raise_event - event {self.name} with function {event_function.name} raised an exception",
                                    level='error', sources=[event_function.owner_id, self.created_by], exc_info=True)()
        self.current_record = None
        return data

