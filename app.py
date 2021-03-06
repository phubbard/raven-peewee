#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'
# see https://pythonspot.com/flask-and-great-looking-charts-using-chart-js/

from peewee import *
import datetime
import logging
import os
from math import floor
from flask import Flask, Markup, render_template, send_from_directory, make_response, jsonify

from config import *
from model import *

app = Flask(__name__)

log = logging.getLogger('raven-app')


def calc_stride(num_max, item_count):
    if item_count <= num_max:
        return 1

    array_stride = int(floor(item_count / num_max))
    return array_stride


def get_yesterdays_readings(num_final=100):
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= yesterday, UsageDatum.timestamp < today)
    array_stride = calc_stride(num_final, usage_vals.count())
    return usage_vals[::array_stride]

    
def get_todays_readings(num_final=100):
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= datetime.date.today())
    array_stride = calc_stride(num_final, usage_vals.count())
    return usage_vals[::array_stride]


def get_todays_totals():
    usage_vals = SumDatum.select().where(SumDatum.timestamp >= datetime.date.today())
    return usage_vals


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/')
def chart():
    # Pull downsampled sets of data for today and yesterday
    print('today')
    labels, values = zip(*[(x.timestamp, x.kW) for x in get_todays_readings()])
    print('yesterday')
    y_labels, y_values = zip(*[(x.timestamp, x.kW) for x in get_yesterdays_readings()])
    print('render')
    return render_template('chart.html', values=values, labels=labels, yesterday_values=y_values, yesterday_labels=y_labels)



@app.route('/latest')
def latest():
    # Hook for Swift - retrieve latest reading only.
    val = UsageDatum.select().order_by(UsageDatum.timestamp.desc()).get()
    return make_response({'kW': val.kW, 'timestamp': val.timestamp}, 200)


if __name__ == '__main__':
#    log.debug("Today's readings:")
#    [log.debug(reading) for reading in get_todays_readings()]

#    log.debug("Today's sums:")
#    [log.debug(reading) for reading in get_todays_totals()]

    app.run(host='0.0.0.0', port=5050, debug=True)
