#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'

from peewee import *
import datetime
import logging

from config import *


class BaseModel(Model):
    class Meta:
        database = db

class UsageDatum(BaseModel):
    timestamp = DateTimeField(default=datetime.datetime.now)
    kW = FloatField(default=0.0)

    def __str__(self):
        return str(self.kW) + 'kW at ' + str(self.timestamp)

class SumDatum(BaseModel):
    timestamp = DateTimeField(default=datetime.datetime.now)
    kWh = FloatField(default=0.0)

    def __str__(self):
        return str(self.kWh) + 'kWh at ' + str(self.timestamp)

def create_data():
    db.connect()
    db.create_tables([UsageDatum, SumDatum])


if __name__ == '__main__':
    create_data()
