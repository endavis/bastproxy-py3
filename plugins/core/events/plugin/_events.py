# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/events/_events.py
#
# File Description: a plugin to handle events
#
# By: Bast

# Standard Library
import types

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from libs.records import LogRecord
from ._event import Event
from libs.stack import SimpleStack
from libs.queue import SimpleQueue
from plugins.core.commands import AddParser, AddArgument
from plugins.core.events import RegisterToEvent
from libs.api import AddAPI

class EventsPlugin(BasePlugin):
    """
    a class to manage events
    """
    @RegisterPluginHook('__init__')
    def _phook_init_plugin(self):
        self.can_reload_f: bool = False

        self.global_raised_count: int = 0
        self.current_event: Event | None = None
        self.active_event_stack = SimpleStack(100)

        self.all_event_stack = SimpleQueue(300)

        self.events: dict[str, Event] = {}

    @RegisterPluginHook('initialize')
    def _phook_initialize(self):
        """
        initialize the plugin
        """
        self.api('plugins.core.settings:add')(self.plugin_id, 'log_savestate', False, bool,
                                'flag to log savestate events, reduces log spam if False')

        # Can't use decorator since this is the one that registers all events from decorators
        self.api('plugins.core.events:register.to.event')("ev_libs.plugins.loader_post_startup_plugins_loaded", self._eventcb_post_startup_plugins_loaded)

    def _eventcb_post_startup_plugins_loaded(self):
        """
        register all events in all plugins
        """
        self._register_all_plugin_events()
        self.api('plugins.core.events:raise.event')(f"ev_{self.plugin_id}_all_events_registered")

    @RegisterToEvent(event_name='ev_baseplugin_patched')
    def _eventcb_baseplugin_patched(self):
        """
        a plugin was patched, so reload all events
        """
        if self.api.startup:
            return

        self._register_all_plugin_events()

    def _register_all_plugin_events(self):
        """
        add commands on startup
        """
        LogRecord("_register_all_plugin_events: start", level='debug',
                        sources=[self.plugin_id])()
        for plugin_id in self.api('libs.plugins.loader:get.loaded.plugins.list')():
            LogRecord(f"_register_all_plugin_events: registering events in {plugin_id}", level='debug',
                        sources=[self.plugin_id])()
            self._register_events_for_plugin(plugin_id)
        LogRecord("_register_all_plugin_events: finish", level='debug',
                        sources=[self.plugin_id])()

    def _register_events_for_plugin(self, plugin_id):
        """
        register all events in a plugin
        """
        plugin_instance = self.api('libs.plugins.loader:get.plugin.instance')(plugin_id)
        event_functions = self.get_event_registration_functions_in_object(plugin_instance)
        LogRecord(f"_register_events_for_plugin: {plugin_id} has {len(event_functions)} registrations", level='debug',
                    sources=[self.plugin_id, plugin_id])()
        if event_functions:
            names = [item.__name__ for item in event_functions]
            LogRecord(f"_register_events_for_plugin {names = }", level='debug',
                        sources=[self.plugin_id, plugin_id])()
            for func in event_functions:
                self.api(f"{self.plugin_id}:register.event.by.func")(func)

    @RegisterToEvent(event_name='ev_plugin_loaded', priority=1)
    def _eventcb_plugin_initialized(self):
        """
        a plugin was loaded, so register all events
        """
        if self.api.startup or not (event_record := self.api('plugins.core.events:get.current.event.record')()):
            return

        self._register_events_for_plugin(event_record['plugin_id'])

    def get_event_registration_functions_in_object(self, base, recurse=True):
        """
        recursively search for functions that are commands in a plugin instance
        and it's attributes
        """
        function_list = []
        for item in dir(base):
            if item.startswith('__'):
                continue
            try:
                item = getattr(base, item)
            except AttributeError:
                continue
            if isinstance(item, types.MethodType) and item.__name__.startswith('_eventcb_') and hasattr(item, 'event_registration'):
                function_list.append(item)
            elif recurse:
                function_list.extend(self.get_event_registration_functions_in_object(item, recurse=False))

        return function_list

    @AddAPI('register.event.by.func', description='register a decorated function to an event')
    def _api_register_event_by_func(self, func):
        """
        register a decorated function as an event
        """
        for item in func.event_registration:
            event_name = item['event_name']
            event_name = event_name.format(**func.__self__.__dict__)
            prio = item['priority']
            self.api('plugins.core.events:register.to.event')(event_name, func, priority=prio)

    @RegisterToEvent(event_name='ev_plugin_unloaded')
    def _eventcb_plugin_unloaded(self):
        """
        a plugin was unloaded
        """
        if event_record := self.api('plugins.core.events:get.current.event.record')():
            LogRecord(f"_eventcb_plugin_unloaded - removing events for {event_record['plugin_id']}",
                    level='info', sources=[self.plugin_id, event_record['plugin_id']])()
            self.api(f"{self.plugin_id}:remove.events.for.owner")(event_record['plugin_id'])

    @AddAPI('get.current.event.name', description='return the current event name')
    def _api_get_current_event_name(self):
        """
        return the current event name
        """
        return self.active_event_stack.peek()

    @AddAPI('get.current.event.record', description='return the current event record')
    def _api_get_current_event_record(self):
        """
        return the current event record
        """
        if last_event := self.active_event_stack.peek():
            event = self.api(f"{self.plugin_id}:get.event")(last_event)
            return event.get_active_event().event_data
        return None

    @AddAPI('get.event.stack', description='return the current event stack')
    def _api_get_event_stack(self):
        """
        return the current event stack
        """
        return self.active_event_stack.getstack()

    @AddAPI('add.event', description='add an event for this plugin to track')
    def _api_add_event(self, event_name: str, created_by: str, description: list | None = None,
                       arg_descriptions: dict[str, str] | None = None):
        """
        add an event for this plugin to track
        """
        event = self.api(f"{self.plugin_id}:get.event")(event_name)
        event.created_by = created_by
        event.description = description or []
        event.arg_descriptions = arg_descriptions or {}

    @AddAPI('get.event', description='return the event')
    def _api_get_event(self, event_name):
        """  return an event
        @Yevent_name@w   = the event to return

        this function returns an Event object
        """
        if event_name not in self.events:
            self.events[event_name] = Event(event_name)

        return self.events[event_name]

    @AddAPI('has.event', description='return the event')
    def _api_has_event(self, event_name):
        """  check if an event exists
        @Yevent_name@w   = the event to check for

        this function returns True if found, False otherwise
        """
        return event_name in self.events

    @AddAPI('is.registered.to.event', description='check if a function is registered to an event')
    def _api_is_registered_to_event(self, event_name, func):
        """  check if a function is registered to an event
        @Yevent_name@w   = the event to check
        @Yfunc@w        = the function to check for

        this function returns True if found, False otherwise
        """
        if event_name in self.events:
            return self.events[event_name].isregistered(func)

        return False

    @AddAPI('register.to.event', description='register a function to an event')
    def _api_register_to_event(self, event_name, func, **kwargs):
        """  register a function to an event
        @Yevent_name@w   = The event to register with
        @Yfunc@w        = The function to register
        keyword arguments:
          prio          = the priority of the function (default: 50)

        this function returns no values"""

        priority = 50 if 'prio' not in kwargs else kwargs['prio']
        func_owner_id = self.api('libs.api:get.function.owner.plugin')(func)

        if not func_owner_id:
            LogRecord(f"_api_register_to_event - could not find owner for {func}",
                      level='error', sources=[self.plugin_id])()
            return

        # unregister if it's already registered, it might be a new priority
        if self.api(f'{self.plugin_id}:is.registered.to.event')(event_name, func):
            self.api(f'{self.plugin_id}:unregister.from.event')(event_name, func)

        event = self.api(f"{self.plugin_id}:get.event")(event_name)

        event.register(func, func_owner_id, priority)

    @AddAPI('unregister.from.event', description='unregister a function from an event')
    def _api_unregister_from_event(self, event_name, func):
        # pylint: disable=unused-argument
        """  unregister a function from an event
        @Yevent_name@w   = The event to unregister with
        @Yfunc@w        = The function to unregister

        this function returns no values"""
        if event_name in self.events:
            self.events[event_name].unregister(func)
        else:
            LogRecord(f"_api_unregister_from_event - could not find event {event_name}",
                      level='error', sources=[self.plugin_id])()

    @AddAPI('remove.events.for.owner', description='remove all registered functions that are specific to a owner_id')
    def _api_remove_events_for_owner(self, owner_id):
        """  remove all registered functions that are specific to a owner_id
        @Yowner_id@w   = The owner to remove events for
        this function returns no values"""
        LogRecord(f"_api_remove_events_for_owner - removing events for {owner_id}",
                  level='info', sources=[self.plugin_id, owner_id])()

        for event in self.events:
            self.events[event].removeowner(owner_id)

    @AddAPI('get.detailed.data.for.plugin', description='get detailed data for a plugin')
    def _api_get_detailed_data_for_plugin(self, owner_name):
        """
        return all events for an owner
        """
        owner_events = {}
        for event in self.events.values():
            if registrations := event.getownerregistrations(owner_name):
                owner_events[event.name] = registrations

        if not owner_events:
            return []

        columns = [
            {'name': 'Event Name', 'key': 'event', 'width': 10},
            {'name': 'Priority', 'key': 'priority', 'width': 10},
            {'name': 'Function', 'key': 'function_name', 'width': 40},
        ]

        data = []
        sorted_keys = sorted(owner_events.keys())
        for event_name in sorted_keys:
            data.extend(
                {
                    'event': event_name,
                    'function_name': item['function_name'],
                    'priority': item['priority'],
                }
                for item in owner_events[event_name]
            )

        count = len(data)

        return [
            *self.api('plugins.core.utils:convert.data.to.output.table')(
                f"{count} Event Registrations for owner: {owner_name}", data, columns
            )
        ]

    @AddAPI('raise.event', description='raise an event')
    def _api_raise_event(self, event_name, event_args=None, calledfrom=None, data_list=None, key_name=None):
        # pylint: disable=too-many-nested-blocks
        """  raise an event with args
        @Yevent_name@w   = The event to raise
        @Yargs@w         = A dict or EventDataRecord of arguments
        """
        if not event_args:
            event_args = {}

        if not calledfrom:
            calledfrom = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        if not calledfrom:
            LogRecord(f"event {event_name} raised with unknown caller",
                      level='warning', sources=[self.plugin_id])()

        event = self.api(f"{self.plugin_id}:get.event")(event_name)

        self.global_raised_count += 1

        # push the event onto the stack
        self.active_event_stack.push(event.name)
        self.all_event_stack.enqueue(event.name)

        raised_event = event.raise_event(event_args, calledfrom, data_list=data_list, key_name=key_name)

        # pop it back off
        self.active_event_stack.pop()

        return raised_event

    @AddAPI('get.event.detail', description='get the details of an event')
    def _api_get_event_detail(self, event_name):
        """  get the details of an event
        @Yevent_name@w = The event name

        this function returns a list of strings for the info"""
        message = []

        if event_name in self.events:
            message.extend(self.events[event_name].detail())
        else:
            message.append(f"event {event_name} does not exist")
        return message

    @AddParser(description='raise an event')
    @AddArgument('event',
                    help='the event to raise',
                    default='',
                    nargs='?')
    def _command_raise(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          raise an event - only works for events with no arguments
          @CUsage@w: raise @Y<event_name>@w
            @Yevent_name@w  = the event_name to raise
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message = []
        if self.api(f"{self.plugin_id}:get.event")(args['event']):
            self.api(f"{self.plugin_id}:raise.event")(args['event'])
            message.append(f"raised event: {args['event']}")
        else:
            message.append(f"event does not exist: {args['event']}")

        return True, message

    @AddParser(description='get details of an event')
    @AddArgument('event',
                    help='the event name to get details for',
                    default=[],
                    nargs='*')
    def _command_detail(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list events and the owner ids registered with them
          @CUsage@w: detail show @Y<event_name>@w
            @Yevent_name@w  = the event_name to get info for
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message = []
        if args['event']:
            for event_name in args['event']:
                message.extend(self.api(f"{self.plugin_id}:get.event.detail")(event_name))
                message.append('')
        else:
            message.append('Please provide an event name')

        return True, message

    @AddParser(description='list events and the ' \
                                                      'owners registered with them')
    @AddArgument('match',
                    help='list only events that have this argument in their name',
                    default='',
                    nargs='?')
    @AddArgument('-sr',
                    '--show-registered-only',
                    help="show only events that have registered functions",
                    action='store_true',
                    default=False)
    @AddArgument('-snr',
                    '--show-not-registered-only',
                    help="show only events that have not registered functions",
                    action='store_true',
                    default=False)
    @AddArgument('-snda',
                    '--show-no-description-or-args',
                    help="show events that have no description or args",
                    action='store_true',
                    default=False)
    @AddArgument('-ra',
                    '--show-raised-only',
                    help="show events that have no description or args",
                    action='store_true',
                    default=False)
    def _command_list(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list events and the owner_ids registered with them
          @CUsage@w: list
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        match = args['match']
        show_registered_only = args['show_registered_only']
        show_no_description_or_args = args['show_no_description_or_args']
        show_raised_only = args['show_raised_only']
        show_not_registered_only = args['show_not_registered_only']
        eventnames = self.events.keys()
        eventnames = sorted(eventnames)
        eventlist = []

        if show_registered_only:
            eventlist = [name for name in eventnames if self.events[name].count() > 0]
        elif show_not_registered_only:
            eventlist = [name for name in eventnames if self.events[name].count() == 0]
        elif show_no_description_or_args:
            eventlist = [name for name in eventnames if not self.events[name].description or not self.events[name].arg_descriptions]
        elif show_raised_only:
            eventlist = [name for name in eventnames if self.events[name].raised_count > 0]
        else:
            eventlist = eventnames

        message = [
            f"{self.events[name].count():<3} - {name:<30}"
            for name in eventlist
            if (not match or match in name) and self.events[name]
        ] or ['No events found']

        return True, message

    @AddParser(description='list registrations for a specific owner')
    @AddArgument('owner',
                    help='list only events that have this argument in their name',
                    default='',
                    nargs='?')
    def _command_owner(self):
        """
        show all registrations for a specific owner
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        if not args['owner']:
            return False, ['Please provide an owner']

        owner_name = args['owner']

        data = self.api(f"{self.plugin_id}:get.detailed.data.for.plugin")(owner_name)

        return True, data or ['No registrations']

    @AddAPI('get.summary.data.for.plugin', description="get summary data for a plugin")
    def _api_get_summary_data_for_plugin(self, plugin_id):
        """
        return a summary of the data in this plugin for a specific plugin_id
        """
        msg = []
        if plugin_id == self.plugin_id:
            msg.extend(
                (
                    self.api('plugins.core.utils:center.colored.string')(
                        "Overall Event Data", '=', 80, filler_color='@G'
                    ),
                    f'Total Events  : {len(self.events)}',
                    f'Raised Events : {self.global_raised_count}',
                    '',
                    self.api('plugins.core.utils:center.colored.string')(
                        f"{self.plugin_id} specific data", '=', 80, filler_color='@G'
                    ),

                )
            )

        registrations = {}
        for event in self.events:
            if new_registrations := self.events[event].getownerregistrations(plugin_id):
                registrations[event] = new_registrations

        all_registrations = list(registrations.keys())

        registrations_str = "".join(f"{'':<26}{item}\n" for item in all_registrations)

        count = len(all_registrations)

        msg.extend([
            f"{f'{count} Event Registrations':<23} : {registrations_str.strip()}",
        ])

        return msg
