#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'

from peewee import *
import datetime
import logging

from config import *
from model import *


def get_todays_readings():
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= datetime.date.today())
    return usage_vals

def get_todays_totals():
    usage_vals = SumDatum.select().where(SumDatum.timestamp >= datetime.date.today())
    return usage_vals


if __name__ == '__main__':
    log.debug("Today's readings:")
    [log.debug(reading) for reading in get_todays_readings()]

    log.debug("Today's sums:")
    [log.debug(reading) for reading in get_todays_totals()]