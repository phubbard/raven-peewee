#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'

from peewee import *
import datetime
import logging

from config import *
from model import *

log = logging.getLogger('raven-today')

def get_todays_readings():
    log.info(datetime.datetime.now())
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= datetime.date.today())
    log.info(datetime.datetime.now())
    return usage_vals

def get_todays_totals():
    usage_vals = SumDatum.select().where(SumDatum.timestamp >= datetime.date.today())
    return usage_vals


if __name__ == '__main__':
    log.info("Today's readings:")
    [log.info(reading) for reading in get_todays_readings()]

    log.info("Today's sums:")
    [log.info(reading) for reading in get_todays_totals()]

