import json
import pytz
import calendar
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import EmailValidator, URLValidator
from django.utils import timezone

from openpyxl import Workbook

from seed_services_client import HubApiClient


def mk_validator(django_validator):
    def validator(inputstr):
        django_validator(inputstr)
        return inputstr
    return validator


def midnight(timestamp):
    return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)


def one_month_after(timestamp):
    weekday, number_of_days = calendar.monthrange(
        timestamp.year, timestamp.month)
    return timestamp + timedelta(days=number_of_days)


def midnight_validator(inputstr):
    return midnight(datetime.strptime(inputstr, '%Y-%m-%d')).replace(
        tzinfo=pytz.timezone(settings.TIME_ZONE))


class ExportSheet(object):

    def __init__(self, sheet, headers=None):
        self._sheet = sheet
        self.set_header(headers or [])

    def set_header(self, headers):
        self._headers = headers
        for index, header in enumerate(headers):
            self._sheet.cell(row=1, column=index + 1, value=header)

    def get_header(self):
        return self._headers

    def add_row(self, row):
        row_number = self._sheet.max_row + 1
        for key, value in row.items():
            cell = self._sheet.cell(
                row=row_number,
                column=self._headers.index(key) + 1)
            cell.value = value


class ExportWorkbook(object):

    def __init__(self):
        self._workbook = Workbook()

    def add_sheet(self, sheetname, position):
        return ExportSheet(self._workbook.create_sheet(sheetname, position))

    def save(self, file_name):
        return self._workbook.save(file_name)


class Command(BaseCommand):

    workbook_class = ExportWorkbook

    help = (
        'Generate a CSV report and write it to disk or optionally email '
        'it to a list of recipients')

    def add_arguments(self, parser):
        parser.add_argument(
            '--start',
            type=midnight_validator, default=midnight(timezone.now()),
            help=('The start of the reporting range (YYYY-MM-DD). '
                  'Defaults to today according to the configured timezone.'))
        parser.add_argument(
            '--end',
            type=midnight_validator,
            default=None,
            help=('The end of the reporting range (YYYY-MM-DD). '
                  'Defaults to exactly 1 month after `--start`'))
        parser.add_argument(
            '--email-to', type=mk_validator(EmailValidator),
            action='append',
            help=('The email address to send the reports to. '
                  '(can specify multiple times)'))
        parser.add_argument(
            '--hub-url', type=mk_validator(URLValidator),
            default=settings.HUB_URL,
        )
        parser.add_argument(
            '--hub-token', type=str, default=settings.HUB_TOKEN
        )
        parser.add_argument(
            '--output-file', type=str, default=None,
            help='The file to write the report to.'
        )

    def handle(self, *args, **kwargs):
        hub_token = kwargs['hub_token']
        hub_url = kwargs['hub_url']
        start_date = kwargs['start']
        end_date = kwargs['end']
        file_name = kwargs['output_file']
        recipients = kwargs['email_to']

        if not any([file_name, recipients]):
            raise CommandError(
                'Please specify --file-name or --email-to.')

        if end_date is None:
            end_date = one_month_after(start_date)

        workbook = self.workbook_class()
        sheet = workbook.add_sheet('Registrations by date', 0)
        self.handle_registrations(
            sheet, hub_token, hub_url, start_date, end_date)
        workbook.save(file_name)

    def handle_registrations(self, sheet, hub_token, hub_url,
                             start_date, end_date):
        hub_client = HubApiClient(hub_token, hub_url)
        registrations = hub_client.get_registrations({
            'created_after': start_date.isoformat(),
            'created_before': end_date.isoformat(),
        })

        sheet.set_header([
            'Created',
            'gravida',
            'msg_type',
            'last_period_date',
            'language',
            'msg_receiver',
            'voice_days',
            'Voice_times',
            'preg_week',
            'reg_type',
            'Personnel_code',
            'Facility',
            'Cadre',
            'State',
        ])

        for registration in registrations['results']:
            data = registration.get('data', {})
            sheet.add_row({
                'Created': registration['created_at'],
                'gravida': data.get('gravida'),
                'msg_type': data.get('msg_type'),
                'last_period_date': data.get('last_period_date'),
                'language': data.get('language'),
                'msg_receiver': data.get('msg_receiver'),
                'voice_days': data.get('voice_days'),
                'Voice_times': data.get('voice_times'),
                'preg_week': data.get('preg_week'),
                'reg_type': data.get('reg_type'),
                'Personnel_code': '',
                'Facility': '',
                'Cadre': '',
                'State': '',
            })
