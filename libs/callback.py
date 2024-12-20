# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/callback.py
#
# File Description: a class to track callbacks
#
# By: Bast
"""
Holds a class to track callbacks
It holds the callback name, owner_id, function, enabled status, created time, last raised time, and raised count
It tracks the number of times the callback has been raised and the last time it was raised
"""
# Standard Library
import datetime
import typing

# 3rd Party

# Project
from libs.api import API

class Callback: # pylint: disable=too-few-public-methods
    """
    a basic callback class
    """
    def __init__(self, name: str, owner_id: str, func: typing.Callable, enabled: bool=True):
        """
        init the class
        """
        self.name: str = name
        self.owner_id: str = owner_id or f"{owner_id}:callback:{name}"
        self.api = API(owner_id=self.owner_id)
        self.raised_count: int = 0
        self.func: typing.Callable = func
        self.enabled: bool = enabled
        self.created_time: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
        self.last_raised_datetime: datetime.datetime | None = None

    def __hash__(self) -> int:
        """
        hash the callback
        """
        return hash(self.func) + hash(self.owner_id) + hash(self.name) + hash(self.created_time)

    def __eq__(self, other_function):
        """
        check equality between two callbacks
        """
        if isinstance(other_function, Callback):
            return hash(self) == hash(other_function)

        return (
            isinstance(other_function, typing.Callable)
            and other_function == self.func
        )

    def execute(self, args: dict | None = None):
        """
        execute the callback
        """
        self.last_raised_datetime = datetime.datetime.now(datetime.timezone.utc)
        self.raised_count = self.raised_count + 1
        return self.func(args) if args else self.func()

    def __str__(self) -> str:
        """
        return a string representation of the callback
        """
        return f"Event {self.name:<10} : {self.owner_id:<15}"
