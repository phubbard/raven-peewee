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
from enum import Enum, auto
#from ConfigParser import SafeConfigParser
from configparser import ConfigParser
from xml.etree import ElementTree as ET
import sys
import os
from logging.handlers import RotatingFileHandler

import serial
import requests
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.theme import Theme
import logging

from version import VERSION

from model import *
from config import *

# Install rich traceback handler
install()

# Create logs directory if it doesn't exist
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configure file handler for plain text logging with rotation
file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'capture.log'),
    maxBytes=100000,  # ~1000 lines
    backupCount=1,    # Keep one backup file
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

# Check if we're running in a terminal
if sys.stdout.isatty():
    # Configure Rich console with theme
    custom_theme = Theme({
        "logging.level.debug": "dim",
        "logging.level.info": "cyan",
        "logging.level.warning": "yellow",
        "logging.level.error": "bold red",
        "logging.level.critical": "bold red",
    })
    console = Console(theme=custom_theme)
    
    # Configure console handler with Rich
    console_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=True
    )
    
    # Configure root logger with both handlers
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[console_handler, file_handler]
    )
else:
    # If not in a terminal, only use file handler
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[file_handler]
    )

log = logging.getLogger('raven-capture')

class ParserState(Enum):
    """States for the XML parser state machine"""
    WAITING = auto()
    IN_INSTANTANEOUS_DEMAND = auto()
    IN_CURRENT_SUMMATION = auto()

class ParserStateMachine:
    """State machine for parsing XML data from the Raven device"""
    
    def __init__(self):
        self.state = ParserState.WAITING
        self.buffer = ''
        self.close_tag = None
        
    def process_line(self, line):
        """Process a single line of input and return complete XML if found"""
        line = line.strip().decode("utf-8")
        log.debug(f"[cyan]Received line:[/cyan] {line}")
        
        if line == '\x00':
            log.debug('[yellow]Skipping mark[/yellow]')
            return None
            
        if self.state == ParserState.WAITING:
            if line == '<InstantaneousDemand>':
                self.state = ParserState.IN_INSTANTANEOUS_DEMAND
                self.buffer = line
                self.close_tag = '</InstantaneousDemand>'
                log.debug('[green]Got start of InstantaneousDemand[/green]')
                return None
            elif line == '<CurrentSummationDelivered>':
                self.state = ParserState.IN_CURRENT_SUMMATION
                self.buffer = line
                self.close_tag = '</CurrentSummationDelivered>'
                log.debug('[green]Got start of CurrentSummationDelivered[/green]')
                return None
            return None
            
        # We're in an element, accumulate the line
        self.buffer += line
        
        if line == self.close_tag:
            log.debug('[green]Got end of XML element[/green]')
            result = self.buffer
            self.reset()
            return result
            
        return None
        
    def reset(self):
        """Reset the state machine to initial state"""
        self.state = ParserState.WAITING
        self.buffer = ''
        self.close_tag = None

def get_demand_chunk(serial):
    """Get a complete XML chunk from the serial port using the state machine"""
    parser = ParserStateMachine()
    
    while True:
        in_buf = serial.readline()
        result = parser.process_line(in_buf)
        if result is not None:
            return result

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
    log.info('[bold green]Starting main loop[/bold green]')
    havereading = False
    havenewreading = False

    if sys.stdout.isatty():
        # Only show progress when running in a terminal
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            progress.add_task("[cyan]Monitoring energy usage...", total=None)
            _run_loop(serial, havereading, havenewreading)
    else:
        # Run without progress indicator when not in a terminal
        _run_loop(serial, havereading, havenewreading)

def _run_loop(serial, havereading, havenewreading):
    """Internal loop function that handles the actual monitoring"""
    while True:
        log.debug('[dim]Reading from serial port[/dim]')
        data_chunk = get_demand_chunk(serial)
        log.debug('[dim]Parsing XML[/dim]')
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
                        log.info(f'[bold green]Actual Meter reading:[/bold green] {meterreading:.2f} kWh')
                    else:
                        log.info('[yellow]Ignoring repeated Meter Reading[/yellow]')
                else:
                    havereading = True
                    meterreading = (float(demand['summationdelivered']) - float(demand['summationreceived']))/1000.0
                    hardmeterreading = meterreading
                    readingtime = demand['atinsec']
                    log.info(f"[yellow]Meter reading:[/yellow] {meterreading:.2f} kWh [yellow](possibly stale reading)[/yellow]")
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
                    meterreading = previousmeterreading + 1.0*(int(readingtime) - int(previousreadingtime))*float(demand['demand'])/(60*60*1000)
                    log.info(f'[bold cyan]Current Usage:[/bold cyan] {demand["demand"]} W')
                    log.info(f'[cyan]Approximate Meter Reading:[/cyan] {meterreading:.2f} kWh')
                    log.info(f'[cyan]Last Actual Meter Reading:[/cyan] {hardmeterreading:.2f} kWh')

                elif havereading:
                    previousmeterreading = meterreading
                    previousreadingtime = readingtime
                    readingtime = demand['atinsec']
                    meterreading = previousmeterreading + 1.0*(int(readingtime) - int(previousreadingtime))*float(demand['demand'])/(60*60*1000)
                    log.info(f'[cyan]Current Usage:[/cyan] {demand["demand"]} W')
                    log.info(f'[yellow]Approximate Meter Reading:[/yellow] {meterreading:.2f} kWh [yellow](based on possibly stale meter reading)[/yellow]')
                    log.info(f'[yellow]Last Actual Meter Reading:[/yellow] {hardmeterreading:.2f} kWh [yellow](possibly stale reading)[/yellow]')
                else:
                    log.info(f'[cyan]Current Usage:[/cyan] {demand["demand"]} W')
                    log.debug('[dim]Meter not yet read[/dim]')

        except Exception as err:
            log.exception('[bold red]Caught a parse or DB error:[/bold red]')
            continue



def setup():
    cfg_file = 'config.ini'
    if (len(sys.argv) == 2):
        cfg_file = sys.argv[1]

    log.info(f'[bold cyan]Reading configuration file[/bold cyan] {cfg_file}')
    cf = ConfigParser()
    cf.read(cfg_file)
    log.info('[bold green]Opening Raven...[/bold green]')
    serial_port = serial.Serial(cf.get('raven', 'port'), cf.getint('raven', 'baud'))
    loop(serial_port)


if __name__ == '__main__':
    setup()
