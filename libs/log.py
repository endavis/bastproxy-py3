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
"""

# Standard Library
import os
import logging
import logging.handlers
import sys
import traceback

# Third Party

# Project
from libs.api import API
import libs.colors
from libs.record import ToClientRecord, LogRecord

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

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.api = API()
        self.FORMATS = {
            logging.DEBUG: self.debug + self.fmt + self.reset,
            logging.INFO: self.info + self.fmt + self.reset,
            logging.WARNING: self.warning + self.fmt + self.reset,
            logging.ERROR: self.error + self.fmt + self.reset,
            logging.CRITICAL: self.critical + self.fmt + self.reset
        }

    def format(self, record):
        if 'exc_info' in record.__dict__:
            if record.exc_info:
                formatted_exc = traceback.format_exception(record.exc_info[1])
                formatted_exc_no_newline = [line.rstrip() for line in formatted_exc if line]
                if isinstance(record.msg, LogRecord):
                    record.msg.extend(formatted_exc_no_newline)
                    record.msg.addchange('Modify', 'add tb', 'CustomColorFormatter')
                    record.msg.clean()
                elif isinstance(record.msg, str):
                    record.msg += '\n'.join(formatted_exc_no_newline)
                record.exc_info = None
                record.exc_text = None
        if self.api('libs.api:has')('plugins.core.log:get:level:color'):
            color = self.api('plugins.core.log:get:level:color')(record.levelno)
            log_fmt = f"\x1b[{libs.colors.ALLCONVERTCOLORS[color]}m" + self.fmt + self.reset
        else:
            log_fmt = self.FORMATS.get(record.levelno)

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class CustomConsoleHandler(logging.StreamHandler):
    def __init__(self, stream=sys.stdout):
        super().__init__(stream=stream)
        self.api = API()
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        # can we log to the console for this logger
        if self.api('libs.api:has')('plugins.core.log:can:log:to:console'):
            if self.api('plugins.core.log:can:log:to:console')(record.name, record.levelno):
                canlog = True
            else:
                canlog = False
        else:
            canlog = True

        if type(record.msg) == LogRecord:
            if canlog and not record.msg.wasemitted['console']:
                record.msg.wasemitted['console'] = True
                super().emit(record)
        elif canlog:
            super().emit(record)

class CustomRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    def __init__(self, filename, when='midnight', interval=1, backupCount=0, encoding=None, delay=False, utc=False, atTime=None):
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)
        self.api = API()
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        # can we log to the file for this logger
        if self.api('libs.api:has')('plugins.core.log:can:log:to:file'):
            if self.api('plugins.core.log:can:log:to:file')(record.name, record.levelno):
                canlog = True
            else:
                canlog = False
        else:
            canlog = True

        if canlog:
            if type(record.msg) == LogRecord:
                if not record.msg.wasemitted['file']:
                    record.msg.wasemitted['file'] = True
                    super().emit(record)
                else:
                    super().emit(record)

class CustomClientHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.api = API()
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        if self.api.startup:
            return

        # can we log to the client for this logger
        if self.api('libs.api:has')('plugins.core.log:can:log:to:client'):
            if self.api('plugins.core.log:can:log:to:client')(record.name, record.levelno):
                canlog = True
            else:
                canlog = False
        else:
            canlog = True

        if canlog or record.levelno >= logging.ERROR:
            formatted_message = self.format(record)
            if type(record.msg) == LogRecord:
                if self.api('libs.api:has')('plugins.core.log:get:level:color'):
                    color = self.api('plugins.core.log:get:level:color')(record.levelno)
                else:
                    color = None
                if not record.msg.wasemitted['client']:
                    record.msg.wasemitted['client'] = True
                    ToClientRecord(formatted_message, color_for_all_lines=color).send('logging client handler')
            else:
                ToClientRecord(formatted_message).send('logging client handler')

def setup_loggers(log_level):

    from libs.api import API

    # for item in logging.root.manager.loggerDict:
    #     temp = logging.getLogger(item)
    #     print(f"{temp.name} handlers: {temp.handlers}")

    rootlogger = logging.getLogger()
    # print(f"rootlogger handlers: {rootlogger.handlers}")
    rootlogger.setLevel(log_level)
    rootlogger.removeHandler(logging.getLogger().handlers[0])

    default_log_file_path = API.BASEDATALOGPATH / default_log_file
    os.makedirs(API.BASEDATALOGPATH / 'networkdata', exist_ok=True)
    data_logger_log_file_path = API.BASEDATALOGPATH / 'networkdata' / data_logger_log_file

    # This logger is the root logger and will be setup with log_level from
    # a command line argument. It will log to a file and to the console.
    file_handler = CustomRotatingFileHandler(filename=default_log_file_path,
                                                    when='midnight')
    file_handler.formatter = logging.Formatter("%(asctime)s " + API.TIMEZONE + " : %(levelname)-9s - %(name)-12s - %(message)s")

    console_handler = CustomConsoleHandler()
    console_handler.formatter = CustomColorFormatter("%(asctime)s " + API.TIMEZONE + " : %(levelname)-9s - %(name)-12s - %(message)s")

    client_handler = CustomClientHandler()
    client_handler.formatter = CustomColorFormatter("%(asctime)s " + API.TIMEZONE + " : %(levelname)-9s - %(name)-12s - %(message)s")

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
    data_logger_file_handler.formatter = logging.Formatter("%(asctime)s " + API.TIMEZONE + " : %(name)-11s - %(message)s")
    data_logger.addHandler(data_logger_file_handler)
    data_logger.propagate = False
