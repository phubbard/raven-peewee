#!/usr/bin/env python

__author__ = 'phubbard'
__date__ = '7/23/15'

# see https://pythonspot.com/flask-and-great-looking-charts-using-chart-js/
import datetime
import os
from math import floor

from peewee import *
from flask import Flask, render_template, send_from_directory, make_response, jsonify
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install
import logging

from config import *
from model import *

# Install rich traceback handler
install()

# Configure Rich console with theme
console = Console(theme={
    "logging.level.debug": "dim",
    "logging.level.info": "cyan",
    "logging.level.warning": "yellow",
    "logging.level.error": "bold red",
    "logging.level.critical": "bold red",
})

# Configure logging with Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(
        console=console,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=True
    )]
)

app = Flask(__name__)
log = logging.getLogger('raven-app')


def calc_stride(num_max, item_count):
    if item_count <= num_max:
        return 1

    array_stride = int(floor(item_count / num_max))
    return array_stride

# TODO average values instead of just decimating the array - want a true downsample
def get_todays_readings(num_final=100):
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= datetime.date.today())
    array_stride = calc_stride(num_final, usage_vals.count())
    decimated = usage_vals[::array_stride]
    rc = []
    for val in decimated:
        rc.append({'x': val.timestamp, 'y': val.kW})
    return rc


def get_todays_readings_relative(num_final=100):
    # Pull all readings for today, but the times are seconds since midnight, for easier plotting
    today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= datetime.date.today())
    # Decimate the array
    array_stride = calc_stride(num_final, usage_vals.count())
    decimated = usage_vals[::array_stride]
    # Now convert each timestamp to relative, on a scale of 0 to 24 fractional hours in the day
    # TODO List comprehension
    rc = []
    for datum in decimated:
        tdiff = (datum.timestamp - today).total_seconds()
        rc.append({'x': tdiff * (24.0 / 86400), 'y': datum.kW})
        datum.timestamp = tdiff
        
    return rc


def get_yesterdays_readings_relative(num_final=100):
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    # Cute trick from https://www.tutorialspoint.com/How-to-convert-date-to-datetime-in-Python
    tzero = datetime.datetime.combine(yesterday, datetime.datetime.min.time())
    usage_vals = UsageDatum.select().where(UsageDatum.timestamp >= yesterday, UsageDatum.timestamp < today)
    array_stride = calc_stride(num_final, usage_vals.count())
    decimated = usage_vals[::array_stride]
    # Now convert each timestamp to relative
    # TODO List comprehension
    rc = []
    for datum in decimated:
        tdiff = (datum.timestamp - tzero).total_seconds()
        rc.append({'x': tdiff * ( 24.0 / 86400), 'y': datum.kW})
        
    return rc


def get_latest_reading():
    val = UsageDatum.select().order_by(UsageDatum.timestamp.desc()).limit(1).get()
    return val.kW
    

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/')
def rel_chart():
    # Pull downsampled sets of data for today and yesterday
    # TODO this is 4 SQL queries - rewrite for single query, this is a bottleneck
    log.info('[cyan]Fetching chart data[/cyan]')
    today_data = get_todays_readings_relative()
    yd_data = get_yesterdays_readings_relative()
    today_abs = get_todays_readings()
    last = get_latest_reading()
    if last > 0:
        current = f'{last}W (consuming from grid)'
        log.info(f'[green]Current usage:[/green] {current}')
    else:
        current = f'{last}W (generating to grid)'
        log.info(f'[green]Current generation:[/green] {current}')
    return render_template('chart.html', today=today_data, yesterday=yd_data, current=current, today_abs=today_abs)


@app.route('/latest')
def latest_value():
    # API for gauge updates
    val = get_latest_reading()
    log.debug(f'[dim]Latest value:[/dim] {val}W')
    return make_response(str(val))


@app.route('/mini')
def mini_chart():
    # Goal here is mobile-friendly dashboard - latest reading and a pre-scaled min/max display
    val = get_latest_reading()
    log.debug(f'[dim]Mini chart value:[/dim] {val}W')
    return render_template('mini.html', latest=val)


@app.route('/old')
def chart():
    # Pull downsampled sets of data for today and yesterday
    log.info('[cyan]Fetching old chart data[/cyan]')
    labels, values = zip(*[(x.timestamp, x.kW) for x in get_todays_readings()])
    y_labels, y_values = zip(*[(x.timestamp, x.kW) for x in get_yesterdays_readings()])
    log.info('[cyan]Rendering old chart template[/cyan]')
    return render_template('chart.html', values=values, labels=labels, yesterday_values=y_values, yesterday_labels=y_labels)


if __name__ == '__main__':
    log.info('[bold green]Starting Raven web server[/bold green]')
    log.info(f'[cyan]Server will be available at:[/cyan] [bold]http://0.0.0.0:5050[/bold]')
    app.run(host='0.0.0.0', port=5050, debug=True)
