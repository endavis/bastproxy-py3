# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/timers/_plugin.py
#
# File Description: a plugin to handle timers
#
# By: Bast

# Standard Library
import time
import datetime
import sys
import asyncio
import math
import typing

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from libs.callback import Callback
from libs.records import LogRecord
from libs.commands import AddParser, AddArgument
from libs.event import RegisterToEvent
from libs.api import AddAPI

class Timer(Callback):
    """
    a class for a timer
    """
    def __init__(self, name, func, seconds, plugin_id, enabled=True, **kwargs):
        """
        Initialize the class. Time should be in military format, e.g.,"1430".

        Parameters:
        name (str): Name of the timer event.
        func (func): Function to execute on the timer event.
        seconds (int): Time interval in seconds.
        plugin (obj): Plugin related to the timer event.
        **kwargs (Optional): Additional keyword arguments
            onetime (bool): True if the timer is one-time only. Defaults to False.
            enabled (bool): True if the timer is enabled. Defaults to True.
            time (str): Time (in military format) when the timer should fire. If None, timer will fire according to the "seconds" value. Defaults to None.
            log (bool): True if the timer should show up in the logs. Defaults to True.
        """
        super().__init__(name, plugin_id, func, enabled)
        self.seconds: int = seconds

        self.onetime: bool = False
        if 'onetime' in kwargs:
            self.onetime = kwargs['onetime']

        self.time: str = ''
        if 'time' in kwargs:
            self.time = kwargs['time']

        self.log = True
        if 'log' in kwargs:
            self.log = kwargs['log']

        self.last_fired_datetime: datetime.datetime | None = None

        # this should be a datetime object
        self.next_fire_datetime: datetime.datetime = self.get_first_fire()

    def get_first_fire(self) -> datetime.datetime:
        """
        Gets the first fire time of the timer.

        Returns:
            datetime: First fire time of the timer.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if self.time:
            hour_minute = time.strptime(self.time, '%H%M')
            new_date = now.replace(hour=hour_minute.tm_hour, minute=hour_minute.tm_min, second=0)
            while new_date < now:
                new_date = new_date + datetime.timedelta(days=1)
            return new_date

        else:
            new_date = now + datetime.timedelta(seconds=self.seconds)

            while new_date < now:
                new_date = new_date + datetime.timedelta(seconds=self.seconds)
            return new_date

    def get_next_fire(self) -> datetime.datetime:
        """
        Gets the next timestamp when the timer should fire.

        Returns:
            int: Timestamp of the next time when the timer should fire.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if self.last_fired_datetime:
            next_fire = self.last_fired_datetime + datetime.timedelta(seconds=self.seconds)
            while next_fire < now:
                next_fire = next_fire + datetime.timedelta(seconds=self.seconds)
            return next_fire
        else:
            return self.get_first_fire()

    def __str__(self) -> str:
        """
        return a string representation of the timer
        """
        return f"Timer {self.name:<10} : {self.owner_id:<15} : {self.seconds:05d} : {self.enabled:<6} : {self.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}"

class TimersPlugin(BasePlugin):
    """
    a plugin to handle timers
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        BasePlugin.__init__(self, *args, **kwargs)

        self.can_reload_f: bool = False

        self.timer_events: dict[int, list[Timer]] = {}
        self.timer_lookup: dict[str, Timer] = {}
        self.overall_fire_count: int = 0
        self.time_last_checked: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        LogRecord(f"initialize - lasttime:  {self.time_last_checked}",
                  'debug', sources=[self.plugin_id])()

        # setup the task to check for timers to fire
        self.api('libs.asynch:task.add')(self.check_for_timers_to_fire, 'Timer thread')

    @RegisterToEvent(event_name='ev_plugins.core.pluginm_plugin_uninitialized')
    def _eventcb_plugin_uninitialized(self):
        """
        a plugin was uninitialized
        """
        if event_record := self.api(
            'plugins.core.events:get.current.event.record'
        )():
            LogRecord(f"_eventcb_plugin_uninitialized - removing timers for plugin {event_record['plugin_id']}",
                    'debug', sources=[self.plugin_id, event_record['plugin_id']])()
            self.api(f"{self.plugin_id}:remove.all.timers.for.plugin")(event_record['plugin_id'])

    @AddParser(description='toggle log flag for a timer')
    @AddArgument('timername',
                    help='the timer name',
                    default='',
                    nargs='?')
    def _command_log(self) -> tuple[bool, list[str]]:
        """
        change the log flag for a timer
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message: list[str] = []
        if args['timername'] in self.timer_lookup:
            self.timer_lookup[args['timername']].log = \
                not self.timer_lookup[args['timername']].log
            message.append('changed log flag to %s for timer %s' % \
              (self.timer_lookup[args['timername']].log,
               args['timername']))
        else:
            message.append(f"timer {args['timername']} does not exist")

        return True, message

    def get_stats(self):
        """
        return stats for this plugin
        """
        stats = BasePlugin.get_stats(self)

        disabled = 0
        enabled = 0

        for i in self.timer_lookup:
            if self.timer_lookup[i].enabled:
                enabled = enabled + 1
            else:
                disabled = disabled + 1

        stats['Timers'] = {}
        stats['Timers']['showorder'] = ['Total', 'Enabled', 'Disabled',
                                        'Fired', 'Memory Usage']
        stats['Timers']['Total'] = len(self.timer_lookup)
        stats['Timers']['Enabled'] = enabled
        stats['Timers']['Disabled'] = disabled
        stats['Timers']['Fired'] = self.overall_fire_count
        stats['Timers']['Memory Usage'] = sys.getsizeof(self.timer_events)
        return stats

    @AddParser(description='list timers')
    @AddArgument('match',
                    help='list only events that have this argument in their name',
                    default='',
                    nargs='?')
    def _command_list(self) -> tuple[bool, list[str]]:
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list timers and the plugins they are defined in
          @CUsage@w: list
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message: list[str] = []

        match: str = args['match']

        message.append(f"UTC time is: {datetime.datetime.now(datetime.timezone.utc).strftime('%a %b %d %Y %H:%M:%S %Z')}")

        message.append('@M' + '-' * 80 + '@w')
        templatestring = '%-20s : %-25s %-9s %-8s %s'
        message.append(templatestring % ('Name', 'Defined in',
                                                       'Enabled', 'Fired', 'Next Fire'))
        message.append('@M' + '-' * 80 + '@w')
        for i in self.timer_lookup:
            if not match or match in i:
                timer = self.timer_lookup[i]
                message.append(templatestring % (
                    timer.name, timer.owner_id,
                    timer.enabled, timer.raised_count,
                    timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')))

        return True, message

    @AddParser(description='get details for a timer')
    @AddArgument('timers',
                        help='a list of timers to get details',
                        default=None,
                        nargs='*')
    def _command_detail(self) -> tuple[bool, list[str]]:
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list the details of a timer
          @CUsage@w: detail
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        message: list[str] = []
        columnwidth: int = 13
        if args['timers']:
            for timer in args['timers']:
                if timer in self.timer_lookup:
                    timer = self.timer_lookup[timer]
                    message.append(f"{'Name':<{columnwidth}} : {timer.name}")
                    message.append(f"{'Enabled':<{columnwidth}} : {timer.enabled}")
                    message.append(f"{'Owner':<{columnwidth}} : {timer.owner_id}")
                    message.append(f"{'Onetime':<{columnwidth}} : {timer.onetime}")
                    message.append(f"{'Time':<{columnwidth}} : {timer.time or 'None'}")
                    message.append(f"{'Seconds':<{columnwidth}} : {timer.seconds}")
                    message.append(f"{'Times Fired':<{columnwidth}} : {timer.raised_count}")
                    message.append(f"{'Log':<{columnwidth}} : {timer.log}")
                    last_fire_time = 'None'
                    if timer.last_fired_datetime:
                        last_fire_time = timer.last_fired_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')
                        message.append(f"{'Last Fire':<{columnwidth}} : {last_fire_time}")
                    message.append(f"{'Next Fire':<{columnwidth}} : {timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}")
                    message.append('')
                else:
                    message.append(f"Timer {timer} does not exist")

        else:
            message.append('Please specify a timer name')

        return True, message

    @AddAPI('add.timer', description='add a timer')
    def _api_add_timer(self, name: str, func: typing.Callable, seconds: int, **kwargs) -> Timer | None:
        """  add a timer
        @Yname@w   = The timer name
        @Yfunc@w  = the function to call when firing the timer
        @Yseconds@w   = the interval (in seconds) to fire the timer
        @Yargs@w arguments:
          @Yunique@w    = True if no duplicates of this timer are allowed,
                                        False otherwise
          @Yonetime@w   = True for a onetime timer, False otherwise
          @Yenabled@w   = True if enabled, False otherwise
          @Ytime@w      = The time to start this timer, e.g. 1300 for 1PM

        returns an Event instance"""
        plugin_id: str = self.api('libs.api:get.caller.owner')(ignore_owner_list=[self.plugin_id])

        if 'plugin_id' in kwargs:
            plugin_instance = self.api('plugins.core.pluginm:get.plugin.instance')(kwargs['plugin'])
            plugin_id = plugin_instance.plugin_id

        if not plugin_id or not self.api('plugins.core.pluginm:is.plugin.id')(plugin_id):
            LogRecord(f"_api_add_timer: timer {name} has no plugin, not adding",
                      'error', sources=[self.plugin_id])()
            return

        if seconds <= 0:
            LogRecord(f"_api_add_timer: timer {name} has seconds <= 0, not adding",
                      'error', sources=[self.plugin_id, plugin_id])()
            return
        if not func:
            LogRecord(f"_api_add_timer: timer {name} has no function, not adding",
                      'error', sources=[self.plugin_id, plugin_id])()
            return

        if 'unique' in kwargs and kwargs['unique']:
            if name in self.timer_lookup:
                LogRecord(f"_api_add_timer: timer {name} already exists, not adding",
                          'error', sources=[self.plugin_id, plugin_id])()
                return

        timer = Timer(name, func, seconds, plugin_id, **kwargs)
        LogRecord(f"_api_add_timer: adding timer {name}",
                  level='debug', sources=[self.plugin_id, plugin_id])()
        self._add_timer_internal(timer)
        return timer

    @AddAPI('remove.all.timers.for.plugin', description='remove all timers for a plugin')
    def _api_remove_all_timers_for_plugin(self, name: str):
        """  remove all timers associated with a plugin
        @Yname@w   = the name of the plugin

        this function returns no values"""
        plugin_instance = self.api('plugins.core.pluginm:get.plugin.instance')(name)
        timers_to_remove: list[str] = []
        LogRecord(f"removing timers for {name}",
                  level='debug', sources=[self.plugin_id, name])()
        for i in self.timer_lookup:
            if plugin_instance.plugin_id == self.timer_lookup[i].owner_id:
                timers_to_remove.append(i)

        for i in timers_to_remove:
            self.api(f"{self.plugin_id}:remove.timer")(i)

    @AddAPI('remove.timer', description='remove a timer')
    def _api_remove_timer(self, name: str):
        """  remove a timer
        @Yname@w   = the name of the timer to remove

        this function returns no values"""
        try:
            timer = self.timer_lookup[name]
            if timer:
                LogRecord(f"_api_remove_timer - removing {timer}",
                          level='debug', sources=[self.plugin_id, timer.owner_id])()
                ttime = timer.get_next_fire()
                if timer in self.timer_events[math.floor(ttime.timestamp())]:
                    self.timer_events[math.floor(ttime.timestamp())].remove(timer)
                del self.timer_lookup[name]
        except KeyError:
            LogRecord(f"_api_remove_timer - timer {name} does not exist",
                      level='error', sources=[self.plugin_id])()

    @AddAPI('toggle.timer', description='toggle a timer to be enabled/disabled')
    def _api_toggle_timer(self, name: str, flag: bool):
        """  toggle a timer to be enabled/disabled
        @Yname@w   = the name of the timer to toggle
        @Yflag@w   = True to enable, False to disable

        this function returns no values"""
        if name in self.timer_lookup:
            self.timer_lookup[name].enabled = flag

    def _add_timer_internal(self, timer: Timer):
        """
        internally add a timer
        """
        timer_next_time_to_fire = math.floor(timer.next_fire_datetime.timestamp())
        if timer_next_time_to_fire != -1:
            if timer_next_time_to_fire not in self.timer_events:
                self.timer_events[timer_next_time_to_fire] = []
            self.timer_events[timer_next_time_to_fire].append(timer)
        self.timer_lookup[timer.name] = timer

    async def check_for_timers_to_fire(self):
        # this is a callback, so disable unused-argument
        # pylint: disable=unused-argument,too-many-nested-blocks
        """
        check all timers
        """
        current_task = asyncio.current_task()
        if current_task:
            current_task.set_name(f"timers task")
        firstrun: bool = True
        keepgoing: bool = True
        while keepgoing:
            now = datetime.datetime.now(datetime.timezone.utc)
            if now != self.time_last_checked:
                if not firstrun:
                    diff = now - self.time_last_checked
                    if diff.total_seconds() > 1:
                        LogRecord(f"check_for_timers_to_fire - timer had to check multiple seconds: {now - self.time_last_checked}",
                                  level='warning', sources=[self.plugin_id])()
                else:
                    LogRecord('Checking timers coroutine has started', level='debug', sources=[self.plugin_id])()
                firstrun = False
                for i in range(math.floor(self.time_last_checked.timestamp()), math.floor(now.timestamp()) + 1):
                    if i in self.timer_events and self.timer_events[i]:
                        for timer in self.timer_events[i][:]:
                            if timer.enabled:
                                try:
                                    timer.execute()
                                    self.overall_fire_count = self.overall_fire_count + 1
                                    if timer.log:
                                        LogRecord(f"check_for_timers_to_fire - timer fired: {timer}",
                                                level='debug', sources=[self.plugin_id, timer.owner_id])()
                                except Exception:  # pylint: disable=broad-except
                                    LogRecord(f"check_for_timers_to_fire - timer had an error: {timer}",
                                            level='error', sources=[self.plugin_id, timer.owner_id], exc_info=True)()
                            try:
                                self.timer_events[i].remove(timer)
                            except ValueError:
                                LogRecord(f"check_for_timers_to_fire - timer {timer.name} did not exist in timerevents",
                                        level='error', sources=[self.plugin_id, timer.owner_id])()
                            if not timer.onetime:
                                timer.next_fire_datetime = timer.get_next_fire()
                                if timer.log:
                                    LogRecord(f"check_for_timers_to_fire - re adding timer {timer.name} for {timer.next_fire_datetime.strftime('%a %b %d %Y %H:%M:%S %Z')}",
                                            level='debug', sources=[self.plugin_id, timer.owner_id])()
                                self._add_timer_internal(timer)
                            else:
                                self.api(f"{self.plugin_id}:remove.timer")(timer.name)
                            if not self.timer_events[i]:
                                del self.timer_events[i]

                self.time_last_checked = now

            await asyncio.sleep(.2)