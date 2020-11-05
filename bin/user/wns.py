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
import weewx.xtypes
from weeutil.weeutil import TimeSpan

VERSION = "0.2"

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
           "outTempMonthAvg":"group_temperature",
           "windchillDayMin":"group_temperature",
           "windchill1hMin":"group_temperature",
           "barometer1h":"group_pressure",
           "barometer1hDiff":"group_pressure",
           "barometer3hDiff":"group_pressure",
           "barometer24hDiff":"group_pressure",
           "pressure1hDiff":"group_pressure",
           "pressure3hDiff":"group_pressure",
           "pressure24hDiff":"group_pressure",
           "UVDayMax":"group_uv",
           "yesterdayRain":"group_rain",
           "rain3":"group_rain",
           "lastRainDate":"group_time",
           "dayET":"group_rain",
           "monthET":"group_rain",
           "yearET":"group_rain",
           "radiation1hMax":"group_radiation",
           "radiationDayMax":"group_radiation"})
        
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
                 'RRD05_':   ('rain','{:.1f}',1.0),
                 'RRD10_':   ('','{:.1f}',1.0),
                 'RRD1H_':   ('hourRain','{:.1f}',1.0),
                 'RRD3H_':   ('rain3','{:.1f}',1.0),
                 'RRD24H':   ('rain24','{:.1f}',1.0),
                 'RRD1D_':   ('dayRain','{:.1f}',1.0),
                 'WSAKT_':   ('windSpeed','{:.1f}',3.6),
                 'WRAKT_':   ('windDir','{:.0f}',1.0),
                 'WBAKT_':   ('windGust','{:.1f}',3.6),
                 'WSM10_':   ('windSpeed10','{:.1f}',1.0),
                 'WRM10_':   ('','{:.1f}',1.0),
                 'WSMX1H':   ('','{:.1f}',1.0),
                 'WSMX1D':   ('','{:.1f}',1.0),
                 'WBMX1D':   ('','{:.1f}',1.0),
                 'WCAKT_':   ('windchill','{:.1f}',1.0),
                 'WCMN1H':   ('windchill1hMin','{:.1f}',1.0),
                 'WCMN1D':   ('windchillDayMin','{:.1f}',1.0),
                 'LDAKT_':   ('barometer','{:.1f}',1.0),
                 'LDABS_':   ('pressure','{:.1f}',1.0),
                 'LDD1H_':   ('barometer1hDiff','{:.1f}',1.0),
                 'LDD3H_':   ('pressure3hDiff','{:.1f}',1.0),
                 'LDD24H':   ('pressure24hDiff','{:.1f}',1.0),
                 'EVA1D_':   ('dayET','{:.1f}',1.0),
                 'SOD1H_':   ('','{:.1f}',1.0),
                 'SOD1D_':   ('','{:.1f}',1.0),
                 'BEDGRA':   ('','{:.1f}',1.0),
                 'SSAKT_':   ('radiation','{:.0f}',1.0),
                 'SSMX1H':   ('radiation1hMax','{:.0f}',1.0),
                 'SSMX1D':   ('radiationDayMax','{:.0f}',1.0),
                 'UVINDX':   ('UV','{:.1f}',1.0),
                 'UVMX1D':   ('UVDayMax','{:.1f}',1.0),
                 'WOLKUG':   ('','{:.1f}',1.0),
                 'SIWEIT':   ('','{:.1f}',1.0),
                 'SNEHOE':   ('','{:.1f}',1.0),
                 'SNEDAT':   ('','date',1.0),
                 'SNEFGR':   ('','{:.1f}',1.0),
                 'T2M1M_':   ('outTempMonthAvg','{:.2f}',1.0),
                 'T2M1MA':   ('','{:.1f}',1.0),
                 'RRDATU':   ('lastRainDate','date',1.0),
                 'RRGEST':   ('yesterdayRain','{:.1f}',1.0),
                 'RRD1M_':   ('monthRain','{:.1f}',1.0),
                 'RRD1MR':   ('','{:.1f}',1.0),
                 'RRD1A_':   ('yearRain','{:.1f}',1.0),
                 'RRD1AR':   ('','{:.1f}',1.0),
                 'EVAD1M':   ('monthET','{:.1f}',1.0),
                 'EVAD1A':   ('yearET','{:.1f}',1.0),
                 'SOD1M_':   ('','{:.1f}',1.0),
                 'SOD1MR':   ('','{:.1f}',1.0),
                 'SOD1A_':   ('','{:.1f}',1.0),
                 'SOD1AR':   ('','{:.1f}',1.0),
                 'KLTSUM':   ('cooldegsum','{:.1f}',1.0),
                 'WRMSUM':   ('heatdegsum','{:.1f}',1.0),
                 'GRASUM':   ('growdegsum','{:.1f}',1.0),
                 'GRADAT':   ('','date',1.0),
                 'TSOI50':   ('','{:.1f}',1.0),
                 'TSOI10':   ('','{:.1f}',1.0),
                 'TSOI20':   ('','{:.1f}',1.0),
                 'WBMX1H':   ('','{:.1f}',3.6),
                 'SSSUMG':   ('radiationYesterdayIntegral','{:.0f}',1.0)
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

    def __get_change_time(self,record_m,value_name,diff_name):
        """calculate value change during a certain time period,
        use target unit"""
        try:
            __value_start_name = "%s%s" % (value_name,diff_name)
            __value_diff_name = "%Diff%" % (value_name,diff_name)
            if (value_name in record_m and _value_start_name in record_m):
                _result=record_m[value_name]-record_m[__value_start_name]
                return _result,__value_diff_name
        except (TypeError,ValueError) as e:
            logerr("diff %s %s: %s" % (value_name,diff_name,e))
        return None
    
    def __wns_umwandeln(self,record):    
        # convert to metric units
        record_m = weewx.units.to_METRICWX(record)

        # temperature change for the last 1 hour
        if ('outTempDiff1h' not in record_m and
           'outTemp' in record_m and 'outTemp1h' in record_m):
            try:
                record_m['outTempDiff1h']=record_m['outTemp']-record_m['outTemp1h']
            except (TypeError,ValueError) as e:
                logerr("outTemp calc 1h diff: %s" % e)

        # barometer change for the last 1 hour
        if ('barometer1hDiff' not in record_m and 
            'barometer' in record_m and 'barometer1h' in record_m):
            try:
                record_m['barometer1hDiff']=record_m['barometer']-record_m['barometer1h']
            except (TypeError,ValueError) as e:
                logerr("barometer calc 1h diff: %s" % e)

#        datei = open('/tmp/wns.txt','w')
#        for key in record_m:
#            fstr="{:.1f}"
#            try:
#                datei.write("%s %s\n" % (key,fstr.format(record_m[key])))
#            except:
#                pass
#        datei.close()

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
            if (rkey in record_m and record_m[rkey] is not None):
                try:
                    if fstr == 'date':
                        __data[key] = time.strftime("%d.%m.%Y",
                                               time.gmtime(record_m[rkey]))
                    else:
                        __data[key] = fstr.format(record_m[rkey]*fakt)
                except (TypeError, ValueError) as e:
                    logerr("%s:%s: %s" % (key,rkey,e))
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

    def calc_radiation_integral(self,timespan,dbmanager):
        """calculate radiation sum over time
        
        radiation: actual radiation in Watt per square meter
        interval:  registration interval as per database record in minutes
        
        """
        
        try:
            _result = dbmanager.getSql(
                    "SELECT SUM(radiation*interval)/60.0, "
                    "MIN(usUnits),MAX(usUnits) FROM %s "
                    "WHERE dateTime>? AND dateTime<=?"
                    % dbmanager.table_name,timespan)
            if _result is not None:
                if not _result[1] == _result[2]:
                    logerr("calculate radation integral: inconsistent units")
                    return None
                return _result[0]
        except weedb.OperationalError as e:
            log.debug("calculate radiation integral %s: Database OperationalError '%s'",self.protocol_name,e)
        except (ValueError, TypeError) as e:
            logerr("calculate radiation integral: %s" % e)
        return None
        
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
        # example:
        #   _time_ts = 15:35
        #   _ago_ts = 14:35 (if a record exists at that time, otherwise
        #             the time stamp of the nearest record)
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

        # get midnight-to-midnight time span according to Tom Keffer
        daytimespan = weeutil.weeutil.archiveDaySpan(_time_ts)
        # yesterday
        yesterdaytimespan = weeutil.weeutil.archiveDaySpan(_time_ts,1,1)
        # get actual month
        monthtimespan = weeutil.weeutil.archiveMonthSpan(_time_ts)
        # get actual year
        yeartimespan = weeutil.weeutil.archiveYearSpan(_time_ts)
        # last 1, 3, 24 hours
        h1timespan = TimeSpan(_time_ts-3600,_time_ts)
        h3timespan = TimeSpan(_time_ts-10800,_time_ts)
        h24timespan = TimeSpan(_time_ts-86400,_time_ts)
        
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
                    "SELECT outTemp,barometer,pressure FROM %s "
                    "WHERE dateTime=? and dateTime<=?"
                    % dbmanager.table_name, (_ago1_ts,_time_ts))
                if _result is not None:
                    if 'outTemp1h' not in _datadict:
                        _datadict['outTemp1h']=_result[0]
                    if 'barometer1h' not in _datadict:
                        _datadict['barometer1h']=_result[1]
                    if 'pressure1h' not in _datadict:
                        _datadict['pressure1h']=_result[2]
                
                _result = dbmanager.getSql(
                    "SELECT MIN(windchill),MAX(radiation) FROM %s "
                    "WHERE dateTime>? and dateTime<=?"
                    % dbmanager.table_name, (_ago1_ts,_time_ts))
                if _result is not None:
                    if 'windchill1hMin' not in _datadict:
                        _datadict['windchill1hMin']=_result[0]
                    if 'radiation1hMax' not in _datadict:
                        _datadict['radiation1hMax']=_result[1]

            _result = dbmanager.getSql(
                    "SELECT MAX(dateTime) FROM %s "
                    "WHERE rain>0.0 AND dateTime<=? AND dateTime<=?"
                    % dbmanager.table_name,(_time_ts,_time_ts))
            if _result is not None:
                if 'lastRainDate' not in _datadict:
                    _datadict['lastRainDate']=_result[0]
            
        except weedb.OperationalError as e:
            log.debug("%s: Database OperationalError '%s'",self.protocol_name,e)
        except (ValueError, TypeError):
            pass

        # calculate yesterday radation integral
        # Watt hour per square meter
        _result = WnsThread.calc_radiation_integral(self,yesterdaytimespan,dbmanager)
        if _result is not None:
            _datadict['radiationYesterdayIntegral']=_result
                
        try:
            # temperature average of the month
            _temp_avg = weewx.xtypes.get_aggregate('outTemp',monthtimespan,'avg',dbmanager)
            _datadict['outTempMonthAvg'] = weewx.units.convertStd(_temp_avg,_datadict['usUnits'])[0]
        except Exception as e:
            logerr("outTempMonthAvg %s" % e)

        try:            
            # rain sum of yesterday
            if 'yesterdayRain' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('rain',yesterdaytimespan,'sum',dbmanager)
                _datadict['yesterdayRain'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
            # rain sum of month
            # (It should already exist.)
            if 'monthRain' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('rain',monthtimespan,'sum',dbmanager)
                _datadict['monthRain'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
            # rain sum of year
            # (I should already exist.)
            if 'yearRain' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('rain',yeartimespan,'sum',dbmanager)
                _datadict['yearRain'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
            # rain sum of the last 3 hours
            if 'rain3' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('rain',h3timespan,'sum',dbmanager)
                _datadict['rain3'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
        except Exception as e:
            logerr("rain %s" % e)
        
        try:
            # evapotranspiration today sum
            if 'dayET' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('ET',daytimespan,'sum',dbmanager)
                _datadict['dayET'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
            # evapotranspiration month sum
            if 'monthET' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('ET',monthtimespan,'sum',dbmanager)
                _datadict['monthET'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
            # evapotranspiration year sum
            if 'yearET' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('ET',yeartimespan,'sum',dbmanager)
                _datadict['yearET'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
        except Exception as e:
            logerr("ET %s" % e)
        
        try:
            # radiation, today maximum
            if 'radiationDayMax' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('radiation',daytimespan,'max',dbmanager)
                _datadict['radiationDayMax'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
        except Exception as e:
            logerr("radiation %s" % e)

        try:
            # difference values require all measuring units to be 0
            # at the same point
            if 'barometer1hDiff' not in _datadict:
                __result = weewx.xtypes.get_aggregate('barometer',h1timespan,'diff',dbmanager)
                _datadict['barometer1hDiff'] = weewx.units.convertStd(__result,_datadict['usUnits'])[0]
            if 'barometer3hDiff' not in _datadict:
                __result = weewx.xtypes.get_aggregate('barometer',h3timespan,'diff',dbmanager)
                _datadict['barometer3hDiff'] = weewx.units.convertStd(__result,_datadict['usUnits'])[0]
            if 'barometer24hDiff' not in _datadict:
                __result = weewx.xtypes.get_aggregate('barometer',h24timespan,'diff',dbmanager)
                _datadict['barometer24hDiff'] = weewx.units.convertStd(__result,_datadict['usUnits'])[0]
        except Exception as e:
            logerr("barometer %s" % e)
        
        try:
            # difference values require all measuring units to be 0
            # at the same point
            if 'pressure1hDiff' not in _datadict:
                __result = weewx.xtypes.get_aggregate('pressure',h1timespan,'diff',dbmanager)
                _datadict['pressure1hDiff'] = weewx.units.convertStd(__result,_datadict['usUnits'])[0]
            if 'pressure3hDiff' not in _datadict:
                __result = weewx.xtypes.get_aggregate('pressure',h3timespan,'diff',dbmanager)
                _datadict['pressure3hDiff'] = weewx.units.convertStd(__result,_datadict['usUnits'])[0]
            if 'pressure24hDiff' not in _datadict:
                __result = weewx.xtypes.get_aggregate('pressure',h24timespan,'diff',dbmanager)
                _datadict['pressure24hDiff'] = weewx.units.convertStd(__result,_datadict['usUnits'])[0]
        except Exception as e:
            logerr("pressure %s" % e)
        
#        try:
#            # growing day sum
#            _soy_ts=yeartimespan.start()
#            _may_ts=_soy_ts+13046400;
#            growtimespan=TimeSpan(_soy_ts,_may_ts)
#            __result = weewx.xtypes.get_aggregate('growdeg',growtimespan,'sum',dbmanager)
#            _datadict['growdegsum']=weewx.units.convertStd(__result,_datadict['usUnits'])[0]
#            if _time_ts>_may_ts:
#                heattimespan=TimeSpan(_may_ts,_may_ts+7948800)
#        except Exception as e:
#            logerr("heatdeg cooldeg growdeg %s" % e)
            
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