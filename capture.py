#!/usr/bin/env python

"""
@author Paul Hubbard
@date 5/7/14
@file main.py
@brief Starting new project for home energy monitoring, using Graphite plus MQTT.

"""

import json
import datetime
import calendar
import time
#from ConfigParser import SafeConfigParser
from configparser import ConfigParser
from xml.etree import ElementTree as ET
import logging as log
import sys

import serial
import requests

from version import VERSION

from model import *
from config import *


log = logging.getLogger('raven-capture')

def get_demand_chunk(serial):
    # FIXME Bug where it never re-syncs if reads start mid-block. Needs a rewrite.

    buf = ''
    in_element = False
    closestring = '</InstantaneousDemand>'

    while True:
        in_buf = serial.readline()
        in_buf_stripped = in_buf.strip().decode("utf-8")
        log.debug(in_buf_stripped)

        if in_buf_stripped == '\x00':
            log.debug('Skipping mark')
            continue

        if not in_element:
            if in_buf_stripped == '<InstantaneousDemand>':
                in_element = True
                buf += in_buf.decode("utf-8")
                log.debug('got start')
                closestring = '</InstantaneousDemand>'
                continue
            elif in_buf_stripped == '<CurrentSummationDelivered>':
                in_element = True
                buf += in_buf.decode("utf-8")
                closestring = '</CurrentSummationDelivered>'
                continue
            else:
                continue

        if in_element:
            buf += in_buf.decode("utf-8") 

        if in_buf_stripped == closestring:
            log.debug('got end of xml')
            return buf

def process_demand(elem):
    """
    Process the InstantaneoousDemand element - convert to decimal,
    shift timestamp, do proper scaling. Code borrows heavily from the
    raven-cosm project.
    """
    
    seconds_since_2000 = int(elem.find('TimeStamp').text, 16)
    multiplier = int(elem.find('Multiplier').text, 16)
    divisor = int(elem.find('Divisor').text, 16)
    epoch_offset = calendar.timegm(time.strptime("2000-01-01", "%Y-%m-%d"))
    gmt = datetime.datetime.utcfromtimestamp(seconds_since_2000 + epoch_offset).isoformat()
    try:
        demand = int(elem.find('Demand').text, 16)
        if seconds_since_2000 and demand and multiplier and divisor:
            if 1000.0*demand * multiplier/divisor > 32768.0:
                demand = -(0xffffffff - demand + 1)
            return({"at": gmt +'Z', "atinsec": seconds_since_2000, "demand": str(1000.0 * demand * multiplier / divisor), "type": 0})

    except:
        log.info("not a demand packet")
    try:
        summationdelivered = int(elem.find('SummationDelivered').text,16)
        summationreceived = int(elem.find('SummationReceived').text,16)
        if seconds_since_2000 and summationdelivered and multiplier and divisor:
            return({"at": gmt +'Z', "atinsec": seconds_since_2000, "summationdelivered": str(1000.0*summationdelivered*multiplier/divisor), "type": 1, "summationreceived": str(1000.0*summationreceived*multiplier/divisor)})
    except:
        log.info("not a meter reading packet either")


def loop(serial):
    """
    Read a chunk, buffer until complete, parse and send it on.
    """

    log.info('Loop starting')
    havereading = False
    havenewreading = False


    while True:
        log.debug('reading from serial')
        data_chunk = get_demand_chunk(serial)
        log.debug('Parsing XML')
        try:
            elem = ET.fromstring(data_chunk)
            demand = process_demand(elem)

            #type 1 is a CurrentSummation Packet (a meter reading packet)
            if demand['type'] == 1:
                if havereading:
                    proposedreading = (float(demand['summationdelivered']) - float(demand['summationreceived']))/1000.0
                    if proposedreading != hardmeterreading:
                        meterreading = proposedreading
                        hardmeterreading = meterreading
                        readingtime = demand['atinsec']
                        havenewreading = True
                        log.info('Actual Meter reading: ' + str(meterreading) + 'kWh')
                    else:
                        log.info('Ignoring repeated Meter Reading')
                else:
                    havereading = True
                    meterreading = (float(demand['summationdelivered']) - float(demand['summationreceived']))/1000.0
                    hardmeterreading = meterreading
                    readingtime = demand['atinsec']
                    log.info("Meter reading: " + str(meterreading) + "kWh (possibly stale reading)")
                    value = SumDatum()
                    value.kWh = meterreading
                    value.save()
                
            #type 0 is a InstantaneousDemand Packet
            if demand['type'] == 0:
                value = UsageDatum()
                value.kW = float(demand['demand'])
                value.save()

                if havenewreading:
                    previousreadingtime = readingtime
                    previousmeterreading = meterreading
                    previousreadingtime = readingtime
                    readingtime = demand['atinsec']
                    meterreading =   previousmeterreading + 1.0*(int(readingtime) - int(previousreadingtime))*float(demand['demand'])/(60*60*1000)
                    log.info('Current Usage: ' + demand['demand'] + 'W')
                    log.info('Approximate Meter Reading: ' + str(meterreading) + 'kWh')
                    log.info('Last Actual Meter Reading: ' + str(hardmeterreading) + 'kWh')

                elif havereading:
                    previousmeterreading = meterreading
                    previousreadingtime = readingtime
                    readingtime = demand['atinsec']
                    meterreading = previousmeterreading + 1.0*(int(readingtime) - int(previousreadingtime))*float(demand['demand'])/(60*60*1000)
                    log.info('Current Usage: ' + demand['demand'])
                    log.info('Approximate Meter Reading: ' + str(meterreading) + 'kWh, but based on possibly stale meter reading.')
                    log.info('Last Actual Meter Reading: ' + str(hardmeterreading) + 'kWh (possibly stale reading)')
                else:
                    log.info('Current Usage: ' + demand['demand'] + 'W')
                    log.debug('Meter not yet read')

        except Exception as err:
            log.exception('Caught a parse or DB error: ')
            continue

        # TODO return pre-set X and Y from process_demand



def setup():
    cfg_file = 'config.ini'
    if (len(sys.argv) == 2):
        cfg_file = sys.argv[1]

    log.info('Reading configuration file ' + cfg_file)
    cf = ConfigParser()
    cf.read(cfg_file)
    log.info('Opening Raven...')
    serial_port = serial.Serial(cf.get('raven', 'port'), cf.getint('raven', 'baud'))
    loop(serial_port)


if __name__ == '__main__':
    setup()
