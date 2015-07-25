#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'

from peewee import *
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')


# See https://github.com/coleifer/peewee
db = SqliteDatabase('data.db', threadlocals=True)
