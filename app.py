#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'

from peewee import *
import datetime
import logging
from flask import Flask, Markup, render_template

from config import *
from model import *

app = Flask(__name__)

def get_todays_readings():
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= datetime.date.today())
    return usage_vals

def get_todays_totals():
    usage_vals = SumDatum.select().where(SumDatum.timestamp >= datetime.date.today())
    return usage_vals

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def chart():
    labels = None
    values = [x.kW for x in get_todays_readings()]
    return render_template('chart.html', values=values, labels=labels)

if __name__ == '__main__':
#    log.debug("Today's readings:")
#    [log.debug(reading) for reading in get_todays_readings()]

#    log.debug("Today's sums:")
#    [log.debug(reading) for reading in get_todays_totals()]

    app.run(host='0.0.0.0', port=5050, debug=True)
