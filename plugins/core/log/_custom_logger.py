# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/log/_init_.py
#
# File Description: a plugin to change logging settings
#
# By: Bast
"""
This module handles changing logging settings

see info/logging_notes.txt for more information about logging
"""
# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/log.py
#
# File Description: setup logging with some customizations
#
# By: Bast
"""
This plugin sets up logging for various types of data

data from the mud and the client
general logging of everything else which will use the root logger

see info/logging_notes.txt for more information about logging
"""

# Standard Library
import os
import logging
import logging.handlers
import sys
import traceback
from typing import Protocol

# Third Party

# Project
from libs.api import API
import libs.colors
from libs.records import ToClientRecord, LogRecord
from plugins._baseplugin import RegisterPluginHook

default_log_file = "bastproxy.log"
data_logger_log_file = "networkdata.log"

class CustomColorFormatter(logging.Formatter):
    """Logging colored formatter, adapted from https://stackoverflow.com/a/56944256/3638629"""

    error = f"\x1b[{libs.colors.ALLCONVERTCOLORS['@x136']}m"
    warning = f"\x1b[{libs.colors.ALLCONVERTCOLORS['@y']}m"
    info = f"\x1b[{libs.colors.ALLCONVERTCOLORS['@w']}m"
    debug = f"\x1b[{libs.colors.ALLCONVERTCOLORS['@x246']}m"
    critical = f"\x1b[{libs.colors.ALLCONVERTCOLORS['@r']}m"
    reset = '\x1b[0m'

    def __init__(self, fmt: str):
        super().__init__()
        self.fmt = fmt
        self.api = API(owner_id=f"{__name__}:CustomColorFormatter")
        self.FORMATS = {
            logging.DEBUG: self.debug + self.fmt + self.reset,
            logging.INFO: self.info + self.fmt + self.reset,
            logging.WARNING: self.warning + self.fmt + self.reset,
            logging.ERROR: self.error + self.fmt + self.reset,
            logging.CRITICAL: self.critical + self.fmt + self.reset
        }

    def format(self, record: logging.LogRecord):
        if 'exc_info' in record.__dict__ and record.exc_info:
            formatted_exc = traceback.format_exception(record.exc_info[1])
            formatted_exc_no_newline = [line.rstrip() for line in formatted_exc if line]
            if isinstance(record.msg, LogRecord):
                record.msg.extend(formatted_exc_no_newline)
                record.msg.addupdate('Modify', 'add traceback', 'CustomColorFormatter')
                record.msg.format()
            elif isinstance(record.msg, str):
                record.msg += '\n'.join(formatted_exc_no_newline)
            record.exc_info = None
            record.exc_text = None
        if self.api('libs.api:has')('plugins.core.log:get.level.color'):
            color = self.api('plugins.core.log:get.level.color')(record.levelno)
            log_fmt = f"\x1b[{libs.colors.ALLCONVERTCOLORS[color]}m{self.fmt}{self.reset}"
        else:
            log_fmt = self.FORMATS.get(record.levelno)

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class CustomConsoleHandler(logging.StreamHandler):
    def __init__(self, stream=sys.stdout):
        super().__init__(stream=stream)
        self.api = API(owner_id=f"{__name__}:CustomConsoleHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        try:
            canlog = bool(
                not self.api('libs.api:has')('plugins.core.log:can.log.to.console')
                or self.api('plugins.core.log:can.log.to.console')(
                    record.name, record.levelno
                )
            )
            if type(record.msg) == LogRecord:
                if canlog and not record.msg.wasemitted['console']:
                    record.msg.wasemitted['console'] = True
                    super().emit(record)
            elif canlog:
                super().emit(record)
        except Exception as e:
            super().emit(record)


class CustomRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    def __init__(self, filename, when='midnight', interval=1, backupCount=0, encoding=None, delay=False, utc=False, atTime=None):
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)
        self.api = API(owner_id=f"{__name__}:CustomRotatingFileHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        try:
            canlog = bool(
                not self.api('libs.api:has')('plugins.core.log:can.log.to.file')
                or self.api('plugins.core.log:can.log.to.file')(
                    record.name, record.levelno
                )
            )
            if type(record.msg) == LogRecord:
                if canlog and not record.msg.wasemitted['file']:
                    record.msg.wasemitted['file'] = True
                    super().emit(record)
            elif canlog:
                super().emit(record)
        except Exception as e:
            super().emit(record)

class CustomClientHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.api = API(owner_id=f"{__name__}:CustomClientHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        if self.api.startup:
            return

        if not self.api('libs.api:has')('plugins.core.log:can.log.to.client'):
            return

        canlog = self.api('plugins.core.log:can.log.to.client')(
                record.name, record.levelno
            )
        if canlog or record.levelno >= logging.ERROR:
            formatted_message = self.format(record)
            if type(record.msg) == LogRecord:
                if self.api('libs.api:has')('plugins.core.log:get.level.color'):
                    color = self.api('plugins.core.log:get.level.color')(record.levelno)
                else:
                    color = None
                if not record.msg.wasemitted['client']:
                    record.msg.wasemitted['client'] = True
                    ToClientRecord(formatted_message, color_for_all_lines=color)('logging client handler')
            else:
                ToClientRecord(formatted_message)('logging client handler')

def setup_loggers(log_level: int):

    from libs.api import API

    rootlogger = logging.getLogger()
    rootlogger.setLevel(log_level)
    for item in rootlogger.handlers:
        rootlogger.removeHandler(item)

    default_log_file_path = API.BASEDATALOGPATH / default_log_file
    os.makedirs(API.BASEDATALOGPATH / 'networkdata', exist_ok=True)
    data_logger_log_file_path = API.BASEDATALOGPATH / 'networkdata' / data_logger_log_file

    file_handler = CustomRotatingFileHandler(filename=default_log_file_path,
                                                    when='midnight')
    file_handler.formatter = logging.Formatter(
        f"%(asctime)s {API.TIMEZONE} : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    console_handler = CustomConsoleHandler()
    console_handler.formatter = CustomColorFormatter(
        f"%(asctime)s {API.TIMEZONE} : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    client_handler = CustomClientHandler()
    client_handler.formatter = CustomColorFormatter(
        f"%(asctime)s {API.TIMEZONE} : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    # add the handler to the root logger
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(console_handler)
    logging.getLogger().addHandler(client_handler)

    # This logger is for any network data from both the mud and the client to facilitate
    # debugging. It is not intended to be used for general logging. It will not use the same
    # log settings as the root logger. It will log to a file and not to the console.
    # logging network data from the mud will use data.mud
    # logging network data to/from the client will use data.<client_uuid>
    data_logger = logging.getLogger("data")
    data_logger.setLevel(logging.INFO)
    data_logger_file_handler = logging.handlers.TimedRotatingFileHandler(data_logger_log_file_path, when='midnight')
    data_logger_file_handler.formatter = logging.Formatter(
        f"%(asctime)s {API.TIMEZONE} : %(name)-11s - %(message)s"
    )
    data_logger.addHandler(data_logger_file_handler)
    data_logger.propagate = False

class CustomLogger(Protocol):
    @RegisterPluginHook('post_init')
    def _log_custom_logger_loadhook_post_init_custom_logging(self):
        # setup file logging and network data logging
        setup_loggers(logging.DEBUG)
