# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/records/_records.py
#
# File Description: a plugin to inspect records
#
# By: Bast

# Standard Library
import os

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from libs.records import RMANAGER
from plugins.core.commands import AddParser, AddArgument

class RecordPlugin(BasePlugin):
    """
    a plugin to inspect records
    """
    @RegisterPluginHook('initialize')
    def _phook_initialize(self):
        """
        initialize the instance
        """
        self.api('plugins.core.settings:add')(self.plugin_id, 'showLogRecords', False, bool,
                                '1 to show LogRecords in detail command')

    @AddParser(description='return the list of record types')
    def _command_types(self):
        """
        List the types of records
        """
        tmsg = ['Record Types:']
        tmsg.extend(f"{rtype:<25} - {count}" for rtype, count in RMANAGER.get_types())
        return True, tmsg

    @AddParser(description='get a list of a specific type of record')
    @AddArgument('recordtype',
                    help='the type of record to list',
                    default='')
    @AddArgument('-c',
                    '--count',
                    help='the # of items to return (default 10)',
                    default=10,
                    nargs='?',
                    type=int)
    def _command_list(self):
        """
        List records of a specific type
        """
        line_length = self.api('plugins.core.commands:get.output.line.length')()
        header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')

        args = self.api('plugins.core.commands:get.current.command.args')()
        rtypes = [rtype for rtype, _ in RMANAGER.get_types()]
        if not args['recordtype'] or args['recordtype'] not in rtypes:
            return True, ["Valid Types:", *[f"    {rtype}" for rtype in rtypes]]
        tmsg = [f"Last {args['count']} records of type {args['recordtype']}:",
                header_color + line_length * '-' + '@w']
        if records := RMANAGER.get_records(args['recordtype'], count=args['count']):
            tmsg.extend([record.one_line_summary() for record in records])
        else:
            tmsg.append('No records found')

        return True, tmsg

    @AddParser(description='get details of a specific record')
    @AddArgument('uid', help='the uid of the record',
                    default='', nargs='?')
    @AddArgument('-u',
                    '--update',
                    help='the update uuid',
                    default='')
    @AddArgument('-dls',
                    '--data_lines_to_show',
                    help='the # of lines of data to show, -1 for all data',
                    default=10,
                    type=int)
    @AddArgument('-sd',
                    '--show_data',
                    help='show data in updates',
                    action='store_false',
                    default=True)
    @AddArgument('-ss',
                    '--show_stack',
                    help='show stack in updates',
                    action='store_false',
                    default=True)
    @AddArgument('-sfr',
                    '--full_children_records',
                    help='show the full children records (without updates)',
                    action='store_true',
                    default=False)
    @AddArgument('-iu',
                    '--include_updates',
                    help='include_updates in the detail',
                    action='store_false',
                    default=True)
    @AddArgument('-d',
                    '--dump',
                    help='dump the record to a file',
                    action='store_true',
                    default=False)
    def _command_detail(self):
        """
        get the details of a specific record
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []

        if not args['uid']:
            tmsg.append('No record id provided')
            return True, tmsg

        record = RMANAGER.get_record(args['uid'])

        # Records are list and can be empty, so check is None
        if record is None:
            tmsg.append(f"record {args['uid']} not found")

        elif args['update']:
            if update := record.get_update(args['update']):
                tmsg.extend(update.format_detailed())
            else:
                tmsg.append(f"update {args['update']} in record {args['uid']} not found")

        else:
            showlogrecords = self.api('plugins.core.settings:get')(self.plugin_id, 'showLogRecords')
            update_filter = [] if showlogrecords else ['LogRecord']
            data = record.get_formatted_details(update_filter=update_filter,
                                                     full_children_records=args['full_children_records'],
                                                     include_updates=args['include_updates'])

            if args['dump']:
                save_path = self.api.BASEDATAPATH / 'dumps'
                save_path.mkdir(parents=True, exist_ok=True)
                file_path = save_path / f"{args['uid']}.txt"
                if file_path.exists():
                    os.remove(file_path)
                with open(file_path, 'w') as f:
                    f.write('\n'.join(data))

                tmsg.append(f"Record dumped to {file_path}")
            else:
                tmsg.extend(data)

        return True, tmsg

    @AddParser(description='get a list of children of a specific record')
    @AddArgument('uid', help='the uid of the record',
                    default='', nargs='?')
    def _command_children(self):
        """
        get the children of a specific record
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        if not args['uid']:
            return True, ['No record id provided']

        record = RMANAGER.get_record(args['uid'])
        if not record:
            return True, [f"Record {args['uid']} not found"]

        child_records_formatted = RMANAGER.format_all_children(record)

        return True, child_records_formatted
