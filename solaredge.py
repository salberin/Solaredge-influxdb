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
        logger.error(f'Error during connection to InfluxDb {dbhost}: {e}')
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
                logger.debug(f'Writing to Influx: {str(datapoint)}')

                await solar_client.write(datapoint)
            else:
                # Error during data receive
                if client.last_error() == 2:
                    logger.error(f'Failed to connect to SolarEdge inverter {client.host()}!')
                elif client.last_error() == 3 or client.last_error() == 4:
                    logger.error('Send or receive error!')
                elif client.last_error() == 5:
                    logger.error('Timeout during send or receive operation!')
        except InfluxDBWriteError as e:
            logger.error(f'Failed to write to InfluxDb: {e}')
        except IOError as e:
            logger.error(f'I/O exception during operation: {e}')
        except Exception as e:
            logger.error(f'Unhandled exception: {e}')

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
    if args.debug and args.debug >= 1:
        logging.getLogger('solaredge').setLevel(logging.DEBUG)
    if args.debug and args.debug == 2:
        logging.getLogger('aioinflux').setLevel(logging.DEBUG)

    print('Starting up solaredge monitoring')
    print(f'Connecting to Solaredge inverter {args.solaredge} on port {args.port} using unitid {args.unitid}')
    print(f'Writing data to influxDb {args.influxdb} on port {args.influxport}')
    client = ModbusClient(args.solaredge, port=args.port, unit_id=args.unitid, auto_open=True)
    logger.debug('Running eventloop')
    asyncio.get_event_loop().run_until_complete(write_to_influx(args.influxdb, args.influxport))
