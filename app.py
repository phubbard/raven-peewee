#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'
# see https://pythonspot.com/flask-and-great-looking-charts-using-chart-js/

from peewee import *
import datetime
import logging
from flask import Flask, Markup, render_template

from config import *
from model import *

app = Flask(__name__)

def get_todays_readings():
    log.info(datetime.datetime.now())
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= datetime.date.today())
    log.info(datetime.datetime.now())
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

    labels, values = zip(*[(x.timestamp, x.kW) for x in get_todays_readings()[::108]])
#    labels = [x.timestamp for x in get_todays_readings()][::108]
#    values = [x.kW for x in get_todays_readings()][::108]
    return render_template('chart.html', values=values, labels=labels)

if __name__ == '__main__':
#    log.debug("Today's readings:")
#    [log.debug(reading) for reading in get_todays_readings()]

#    log.debug("Today's sums:")
#    [log.debug(reading) for reading in get_todays_totals()]

    app.run(host='0.0.0.0', port=5050, debug=True)
