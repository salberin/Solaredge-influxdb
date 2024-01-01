FROM python:3.10.13-alpine

MAINTAINER alberink@gmail.com

ENV INFLUXDB=192.168.1.1
ENV INFLUXPORT=8086
ENV INVERTER=192.168.1.2
ENV INVERTERPORT=502
ENV UNITID=1

ADD requirements.txt /
RUN pip3 install -r /requirements.txt

ADD solaredge.py /

CMD python3 /solaredge.py --influxdb $INFLUXDB --influxport $INFLUXPORT --port $INVERTERPORT --unitid $UNITID $INVERTER

