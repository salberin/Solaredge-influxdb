import argparse
import datetime
import logging

from aiohttp import ClientConnectionError
from pyModbusTCP.client import ModbusClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
import asyncio
from aioinflux import InfluxDBClient, InfluxDBWriteError

datapoint = {
    'measurement': 'SolarEdge',
    'tags': {
        'inverter': '1'
    },
    'fields': {}
}

logger = logging.getLogger('solaredge')


async def write_to_influx(dbhost, dbport, dbname='solaredge'):
    global client

    def trunc_float(floatval):
        return float('%.2f' % floatval)

    try:
        solar_client = InfluxDBClient(host=dbhost, port=dbport, db=dbname)
        await solar_client.create_database(db=dbname)
    except ClientConnectionError as e:
        logger.error('Error during connection to InfluxDb {0}: {1}'.format(dbhost, e))
        return

    logger.info('Database opened and initialized')
    while True:
        try:
            reg_block = client.read_holding_registers(40069, 38)
            if reg_block:
                # print(reg_block)
                data = BinaryPayloadDecoder.fromRegisters(reg_block, byteorder=Endian.Big, wordorder=Endian.Big)
                data.skip_bytes(12)
                scalefactor = 10**data.decode_16bit_int()
                data.skip_bytes(-10)
                datapoint['fields']['AC Total Current'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                datapoint['fields']['AC Current phase A'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                datapoint['fields']['AC Current phase B'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                datapoint['fields']['AC Current phase C'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                data.skip_bytes(14)
                scalefactor = 10**data.decode_16bit_int()
                data.skip_bytes(-8)
                datapoint['fields']['AC Voltage phase A'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                datapoint['fields']['AC Voltage phase B'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                datapoint['fields']['AC Voltage phase C'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                data.skip_bytes(4)
                scalefactor = 10**data.decode_16bit_int()
                data.skip_bytes(-4)
                datapoint['fields']['AC Power output'] = trunc_float(data.decode_16bit_int() * scalefactor)
                data.skip_bytes(26)
                scalefactor = 10**data.decode_16bit_int()
                data.skip_bytes(-4)
                datapoint['fields']['DC Current'] = trunc_float(data.decode_16bit_uint() *scalefactor)
                data.skip_bytes(4)
                scalefactor = 10**data.decode_16bit_int()
                data.skip_bytes(-4)
                datapoint['fields']['DC Voltage'] = trunc_float(data.decode_16bit_uint() * scalefactor)
                data.skip_bytes(4)
                scalefactor = 10**data.decode_16bit_int()
                data.skip_bytes(-4)
                datapoint['fields']['DC Power input'] = trunc_float(data.decode_16bit_int() * scalefactor)

                datapoint['time'] = str(datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
                logger.debug('Writing to Influx: ' + str(datapoint))

                await solar_client.write(datapoint)
        except InfluxDBWriteError as e:
            logger.error('Failed to write to InfluxDb: {0}'.format(e))
        except Exception as e:
            logger.error('Unhandled exception: {0}'.format(e), exc_info=True)

        await asyncio.sleep(5)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--influxdb', default='localhost')
    parser.add_argument('--influxport', type=int, default=8086)
    parser.add_argument('--port', type=int, default=502, help='ModBus TCP port number to use')
    parser.add_argument('--unitid', type=int, default=1, help='ModBus unit id to use in communication')
    parser.add_argument('solaredge', metavar='SolarEdge IP', help='IP address of the SolarEdge inverter to monitor')
    parser.add_argument('--debug', '-d', action='count')
    args = parser.parse_args()

    logging.basicConfig()
    if args.debug >= 1:
        logging.getLogger('solaredge').setLevel(logging.DEBUG)
    if args.debug == 2:
        logging.getLogger('aioinflux').setLevel(logging.DEBUG)

    print('Starting up solaredge monitoring')
    client = ModbusClient(args.solaredge, port=args.port, unit_id=args.unitid, auto_open=True)
    logger.debug('Running eventloop')
    asyncio.get_event_loop().run_until_complete(write_to_influx(args.influxdb, args.influxport))
