# Copyright 2020 Johanna Roedenbeck
# derived from Windy driver by Matthew Wall
# thanks to Gary and Tom Keffer from Weewx development group

"""
This is a weewx extension that uploads data to a WNS

http://wetternetz-sachsen.de

Minimal configuration

[StdRESTful]
    [[Wns]]
        station = station ID
        api_key = WNS-Kennung

"""

# deal with differences between python 2 and python 3
try:
    # Python 3
    import queue
except ImportError:
    # Python 2
    # noinspection PyUnresolvedReferences
    import Queue as queue

try:
    # Python 3
    from urllib.parse import urlencode
except ImportError:
    # Python 2
    # noinspection PyUnresolvedReferences
    from urllib import urlencode

from distutils.version import StrictVersion
import json
import sys
import time

import weedb
import weewx
import weewx.manager
import weewx.restx
import weewx.units
from weeutil.weeutil import to_bool, to_int

VERSION = "0.1"

REQUIRED_WEEWX = "3.8.0"
if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_WEEWX):
    raise weewx.UnsupportedFeature("weewx %s or greater is required, found %s"
                                   % (REQUIRED_WEEWX, weewx.__version__))

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging
    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'wns: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)


class Wns(weewx.restx.StdRESTbase):
    DEFAULT_URL = 'http://www.wetternetz-sachsen.de/get_daten_23.php'

    def __init__(self, engine, cfg_dict):
        super(Wns, self).__init__(engine, cfg_dict)
        loginf("version is %s" % VERSION)
        site_dict = weewx.restx.get_site_dict(cfg_dict, 'Wns', 'api_key')
        if site_dict is None:
            return

        try:
            site_dict['manager_dict'] = weewx.manager.get_manager_dict_from_config(cfg_dict, 'wx_binding')
        except weewx.UnknownBinding:
            pass

        self.archive_queue = queue.Queue()
        self.archive_thread = WnsThread(self.archive_queue, **site_dict)

        self.archive_thread.start()
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

        # register data type for unit conversion
        weewx.units.obs_group_dict.extend(
          {"outTempDayMin":"group_temperature",
           "outTempDayMax":"group_temperature",
           "outTemp1h":"group_temperature",
           "windchillDayMin":"group_temperature",
           "windchill1hMin":"group_temperature",
           "barometer1h":"group_pressure",
           "UVDayMax":"group_uv"})
        
    def new_archive_record(self, event):
        self.archive_queue.put(event.record)


class WnsThread(weewx.restx.RESTThread):

    _DATA_MAP = {'T2AKT_':   ('outTemp','{:.1f}',1.0),
                 'T2MIN_':   ('outTempDayMin','{:.1f}',1.0),
                 'T2MAX_':   ('outTempDayMax','{:.1f}',1.0),
                 'T2D1H_':   ('outTempDiff1h','{:.1f}',1.0),
                 'T5AKT_':   ('','{:.1f}',1.0),
                 'T5MIN_':   ('','{:.1f}',1.0),
                 'LFAKT_':   ('outHumidity','{:.0f}',1.0),
                 'RRD05_':   ('','{:.1f}',1.0),
                 'RRD10_':   ('','{:.1f}',1.0),
                 'RRD1H_':   ('hourRain','{:.1f}',1.0),
                 'RRD3H_':   ('','{:.1f}',1.0),
                 'RRD24H':   ('rain24','{:.1f}',1.0),
                 'RRD1D_':   ('dayRain','{:.1f}',1.0),
                 'WSAKT_':   ('windSpeed','{:.1f}',3.6),
                 'WRAKT_':   ('windDir','{:.0f}',1.0),
                 'WBAKT_':   ('windGust','{:.1f}',3.6),
                 'WSM10_':   ('','{:.1f}',1.0),
                 'WRM10_':   ('','{:.1f}',1.0),
                 'WSMX1H':   ('','{:.1f}',1.0),
                 'WSMX1D':   ('','{:.1f}',1.0),
                 'WBMX1D':   ('','{:.1f}',1.0),
                 'WCAKT_':   ('windchill','{:.1f}',1.0),
                 'WCMN1H':   ('windchill1hMin','{:.1f}',1.0),
                 'WCMN1D':   ('windchillDayMin','{:.1f}',1.0),
                 'LDAKT_':   ('barometer','{:.1f}',1.0),
                 'LDABS_':   ('pressure','{:.1f}',1.0),
                 'LDD1H_':   ('barometerDiff1h','{:.1f}',1.0),
                 'LDD3H_':   ('','{:.1f}',1.0),
                 'LDD24H':   ('','{:.1f}',1.0),
                 'EVA1D_':   ('','{:.1f}',1.0),
                 'SOD1H_':   ('','{:.1f}',1.0),
                 'SOD1D_':   ('','{:.1f}',1.0),
                 'BEDGRA':   ('','{:.1f}',1.0),
                 'SSAKT_':   ('radiation','{:.0f}',1.0),
                 'SSMX1H':   ('','{:.0f}',1.0),
                 'SSMX1D':   ('maxSolarRad','{:.0f}',1.0),
                 'UVINDX':   ('UV','{:.1f}',1.0),
                 'UVMX1D':   ('UVDayMax','{:.1f}',1.0),
                 'WOLKUG':   ('','{:.1f}',1.0),
                 'SIWEIT':   ('','{:.1f}',1.0),
                 'SNEHOE':   ('','{:.1f}',1.0),
                 'SNEDAT':   ('','date',1.0),
                 'SNEFGR':   ('','{:.1f}',1.0),
                 'T2M1M_':   ('','{:.1f}',1.0),
                 'T2M1MA':   ('','{:.1f}',1.0),
                 'RRDATU':   ('','date',1.0),
                 'RRGEST':   ('','{:.1f}',1.0),
                 'RRD1M_':   ('','{:.1f}',1.0),
                 'RRD1MR':   ('','{:.1f}',1.0),
                 'RRD1A_':   ('','{:.1f}',1.0),
                 'RRD1AR':   ('','{:.1f}',1.0),
                 'EVAD1M':   ('','{:.1f}',1.0),
                 'EVAD1A':   ('','{:.1f}',1.0),
                 'SOD1M_':   ('','{:.1f}',1.0),
                 'SOD1MR':   ('','{:.1f}',1.0),
                 'SOD1A_':   ('','{:.1f}',1.0),
                 'SOD1AR':   ('','{:.1f}',1.0),
                 'KLTSUM':   ('','{:.1f}',1.0),
                 'WRMSUM':   ('','{:.1f}',1.0),
                 'GRASUM':   ('','{:.1f}',1.0),
                 'GRADAT':   ('','date',1.0),
                 'TSOI50':   ('','{:.1f}',1.0),
                 'TSOI10':   ('','{:.1f}',1.0),
                 'TSOI20':   ('','{:.1f}',1.0),
                 'WBMX1H':   ('','{:.1f}',1.0),
                 'SSSUMG':   ('','{:.1f}',1.0)
                }

    def __init__(self, q, api_key, station='WNS', server_url=Wns.DEFAULT_URL,
                 skip_upload=False, manager_dict=None,
                 post_interval=None, max_backlog=sys.maxsize, stale=None,
                 log_success=True, log_failure=True,
                 timeout=60, max_tries=3, retry_wait=5):
        super(WnsThread, self).__init__(q,
                                          protocol_name='Wns',
                                          manager_dict=manager_dict,
                                          post_interval=post_interval,
                                          max_backlog=max_backlog,
                                          stale=stale,
                                          log_success=log_success,
                                          log_failure=log_failure,
                                          max_tries=max_tries,
                                          timeout=timeout,
                                          retry_wait=retry_wait)
        self.api_key = api_key
        self.station = station
        loginf("Station %s" % self.station)
        self.server_url = server_url
        loginf("Data will be uploaded to %s" % self.server_url)
        self.skip_upload = to_bool(skip_upload)

    def __wns_umwandeln(self,record):    
        # convert to metric units
        record_m = weewx.units.to_METRICWX(record)

        # temperature change for the last 1 hour
        if ('outTempDiff1h' not in record_m and
           'outTemp' in record_m and 'outTemp1h' in record_m):
            try:
                record_m['outTempDiff1h']=record_m['outTemp']-record_m['outTemp1h']
            except (TypeError,ValueError):
                pass

        # barometer chnage for the last 1 hour
        if ('barometerDiff1h' not in record_m and 
            'barometer' in record_m and 'barometer1h' in record_m):
            try:
                record_m['barometerDiff1h']=record_m['barometer']-record_m['barometer1h']
            except (TypeError,ValueError):
                pass
        
        __data = {
            #'STA_ID': self.station,  # integer identifier, usually "0"
            #'STAKEN': '',
            'TMPVER': 'WNS_V2.3',
            'WSOVER': "WEEWX_%s" % (weewx.__version__),
            'ZEIT__': time.strftime("%H:%M",
                                     time.gmtime(record_m['dateTime'])),
            'DATUM_': time.strftime("%d.%m.%Y",
                                     time.gmtime(record_m['dateTime'])),
            'UTCDIF': '0'
            }

        for key in self._DATA_MAP:
            rkey = self._DATA_MAP[key][0]
            fstr = self._DATA_MAP[key][1]
            fakt = self._DATA_MAP[key][2]
            if rkey in record_m:
                try:
                    if fstr == 'date':
                        __data[key] = time.strftime("%d.%m.%Y",
                                               record_m[rkey])
                    else:
                        __data[key] = fstr.format(record_m[rkey]*fakt)
                except (TypeError, ValueError) as e:
                    logerr("%s" % e)
                    __data[key] = '--'
            else:
                __data[key] = '--'
        return __data

    def format_url(self, record):
        """Return an URL for doing a POST to wns"""
        data = WnsThread.__wns_umwandeln(self,record)
        
        zeilen=[]

        for lkey in data:
            zeilen.append(data[lkey])

        trennz = ';'
        body = trennz.join(zeilen)

        url = '%s?var=%s;%s;%s' % (self.server_url, 
                          self.station, self.api_key, body)

        loginf("url %s" % url)

        if weewx.debug >= 2:
            logdbg("url: %s" % url)
        return url

#    def get_post_body(self, record):
#        """Specialized version for doing a POST to wns"""
#        record_m = weewx.units.to_METRICWX(record)
#
#        data = WnsThread.__wns_umwandeln(self,record)
#        
#        zeilen=[]
#
#        for lkey in data:
#            zeilen.append("({} {})".format(lkey,data[lkey]))
#
#        trennz = '\n'
#        body = trennz.join(zeilen)
#
#        datei = open('/tmp/wns.txt','w')
#        datei.write(body)
#        datei.close()
#
#        if weewx.debug >= 2:
#            logdbg("txt: %s" % body)
#
#        return body, 'text/plain'

    def get_record(self, record, dbmanager):
        """Augment record data with additional data from the archive.
        Should return results in the same units as the record and the database.
        
        returns: A dictionary of weather values"""
    
        # run parent class
        _datadict = super(WnsThread,self).get_record(record,dbmanager)

        # actual time stamp
        _time_ts = _datadict['dateTime']
        _sod_ts = weeutil.weeutil.startOfDay(_time_ts)

        # 1 hour ago
        # We look for the database record nearest to 1 hour ago within +-5 min.
        try:
            _result = dbmanager.getSql(
                    "SELECT MIN(dateTime) FROM %s "
                    "WHERE dateTime>=? AND dateTime<=?"
                    % dbmanager.table_name, (_time_ts-3600.0,_time_ts-3300.0))
            if _result is None:
                _result = dbmanager.getSql(
                    "SELECT MAX(dateTime) FROM %s "
                    "WHERE dateTime>=? AND dateTime<=?"
                    % dbmanager.table_name, (_time_ts-3900.0,_time_ts-3600.0))
            if _result is not None:
                _ago1_ts = _result[0]
            else:
                _ago1_ts = None
        except weedb.OperationalError:
            _ago1_ts = None
        
        loginf("get_record dateTime %s, Tagesanfang %s, vor 1h %s" %
            (time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(_time_ts)),
            time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(_sod_ts)),
            time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(_ago1_ts))))

        try:
            # minimum and maximum temperature of the day
            # check for midnight, result is not valid then
            if ('outTempDayMax' not in _datadict and _sod_ts<_time_ts):
                _result = dbmanager.getSql(
                    "SELECT MIN(outTemp),MAX(outTemp),MIN(windchill),"
                    "MAX(UV) FROM %s "
                    "WHERE dateTime>? AND dateTime<=?"
                    % dbmanager.table_name, (_sod_ts,_time_ts))
                if _result is not None:
                    _datadict['outTempDayMin']=_result[0]
                    _datadict['outTempDayMax']=_result[1]
                    _datadict['windchillDayMin']=_result[2]
                    _datadict['UVDayMax']=_result[3]

            # temperature and barometer change of the last hour
            if _ago1_ts is not None:
                _result = dbmanager.getSql(
                    "SELECT outTemp,barometer FROM %s "
                    "WHERE dateTime=? and dateTime<=?"
                    % dbmanager.table_name, (_ago1_ts,_time_ts))
                if _result is not None:
                    if 'outTemp1h' not in _datadict:
                        _datadict['outTemp1h']=_result[0]
                    if 'barometer1h' not in _datadict:
                        _datadict['barometer1h']=_result[1]
                
                _result = dbmanager.getSql(
                    "SELECT MIN(windchill) FROM %s "
                    "WHERE dateTime>? and dateTime<=?"
                    % dbmanager.table_name, (_ago1_ts,_time_ts))
                if _result is not None:
                    if 'windchill1hMin' not in _datadict:
                        _datadict['windchill1hMin']=_result[0]

        except weedb.OperationalError as e:
          log.debug("%s: Database OperationalError '%s'",self.protocol_name,e)
        except (ValueError, TypeError):
            pass

        return _datadict
        
        
# Use this hook to test the uploader:
#   PYTHONPATH=bin python bin/user/wns.py

if __name__ == "__main__":
    weewx.debug = 2

    try:
        # WeeWX V4 logging
        weeutil.logger.setup('wns', {})
    except NameError:
        # WeeWX V3 logging
        syslog.openlog('wns', syslog.LOG_PID | syslog.LOG_CONS)
        syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))

    q = queue.Queue()
    t = WnsThread(q, api_key='123', station=0)
    t.start()
    r = {'dateTime': int(time.time() + 0.5),
         'usUnits': weewx.US,
         'outTemp': 32.5,
         'inTemp': 75.8,
         'outHumidity': 24,
         'windSpeed': 10,
         'windDir': 32}
    print(t.format_url(r))
    q.put(r)
    q.put(None)
    t.join(30)