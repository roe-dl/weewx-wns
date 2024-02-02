# Copyright 2020,2022,2023 Johanna Roedenbeck
# derived from Windy driver by Matthew Wall
# thanks to Gary and Tom Keffer from Weewx development group

"""
This is a weewx extension that uploads data to a WNS

http://wetternetz-sachsen.de

Minimal configuration

[StdRESTful]
    [[Wns]]
        enable = true
        server_url = 'http://www.wetternetz-sachsen.de/get_daten_23.php'
        station = station ID
        api_key = WNS-Kennung
        T5AKT_ = None
        SOD1D_ = None
        TSOI10 = None
        TSOI20 = None
        TSOI50 = None
        skip_upload = false
        log_url = false

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

VERSION = "0.8"

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


class Wns(weewx.restx.StdRESTful):
    DEFAULT_URL = 'http://www.wetternetz-sachsen.de/get_daten_23.php'

    def __init__(self, engine, cfg_dict):
        super(Wns, self).__init__(engine, cfg_dict)
        loginf("version is %s" % VERSION)
        site_dict = weewx.restx.get_site_dict(cfg_dict, 'Wns', 'api_key', 'station')
        if site_dict is None:
            return

        try:
            site_dict['manager_dict'] = weewx.manager.get_manager_dict_from_config(cfg_dict, 'wx_binding')
        except weewx.UnknownBinding:
            pass

        self.archive_queue = queue.Queue(5)
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
           "radiationDayMax":"group_radiation",
           "windSpeed1hMax":"group_speed",
           "windGust1hMax":"group_speed",
           "windSpeedDayMax":"group_speed",
           "windGustDayMax":"group_speed"})
        
    def new_archive_record(self, event):
        try:
            self.archive_queue.put(event.record,timeout=10)
        except queue.Full:
            logerr('Queue is full. Thread died?')


class WnsThread(weewx.restx.RESTThread):

    _DATA_MAP = [('T2AKT_',  'outTemp','','','{:.1f}'),
                 ('T2MIN_',  'outTempDayMin','','','{:.1f}'),
                 ('T2MAX_',  'outTempDayMax','','','{:.1f}'),
                 ('T2D1H_',  'outTempDiff1h','','','{:.1f}'),
                 ('T5AKT_',  '','','','{:.1f}'),
                 ('T5MIN_',  '','','','{:.1f}'),
                 ('LFAKT_',  'outHumidity','','','{:.0f}'),
                 ('RRD05_',  'rain','','','{:.1f}'),
                 ('RRD10_',  'rain10m','','','{:.1f}'),
                 ('RRD1H_',  'hourRain','','','{:.1f}'),
                 ('RRD3H_',  'rain3','','','{:.1f}'),
                 ('RRD24H',  'rain24','','','{:.1f}'),
                 ('RRD1D_',  'dayRain','','','{:.1f}'),
                 ('WSAKT_',  'windSpeed','','','{:.1f}'),        # km/h
                 ('WRAKT_',  'windDir','','','{:.0f}'),
                 ('WBAKT_',  'windGust','','','{:.1f}'),         # km/h
                 ('WSM10_',  'windSpeed10','','','{:.1f}'),      # km/h
                 ('WRM10_',  'windDir10','','','{:.0f}'),
                 ('WSMX1H',  'windSpeed','1h','max','{:.1f}'),   # km/h
                 ('WSMX1D',  'windSpeed','Day','max','{:.1f}'),  # km/h
                 ('WBMX1D',  'windGust','Day','max','{:.1f}'),   # km/h
                 ('WCAKT_',  'windchill','','','{:.1f}'),
                 ('WCMN1H',  'windchill1hMin','','','{:.1f}'),
                 ('WCMN1D',  'windchillDayMin','','','{:.1f}'),
                 ('LDAKT_',  'barometer','','','{:.1f}'),        # QFF mbar
                 ('LDABS_',  'pressure','','','{:.1f}'),
                 ('LDD1H_',  'barometer','1h','diff','{:.1f}'),
                 ('LDD3H_',  'barometer','3h','diff','{:.1f}'),
                 ('LDD24H',  'barometer','24h','diff','{:.1f}'),
                 ('EVA1D_',  'dayET','','','{:.1f}'),
                 ('SOD1H_',  '','','','{:.1f}'),
                 ('SOD1D_',  '','','','HH:MM'),
                 ('BEDGRA',  '','','','{:.1f}'),
                 ('SSAKT_',  'radiation','','','{:.0f}'),
                 ('SSMX1H',  'radiation1hMax','','','{:.0f}'),
                 ('SSMX1D',  'radiation','Day','max','{:.0f}'),
                 ('UVINDX',  'UV','','','{:.1f}'),
                 ('UVMX1D',  'UVDayMax','','','{:.1f}'),
                 ('WOLKUG',  'cloudbase','','','{:.0f}'),
                 ('SIWEIT',  '','','','{:.1f}'),
                 ('SNEHOE',  '','','','{:.1f}'),
                 ('SNEDAT',  '','','','date'),
                 ('SNEFGR',  '','','','{:.1f}'),
                 ('T2M1M_',  'outTempMonthAvg','','','{:.2f}'),
                 ('T2M1MA',  '','','','{:.1f}'),
                 ('RRDATU',  'lastRainDate','','','date'),
                 ('RRGEST',  'yesterdayRain','','','{:.1f}'),
                 ('RRD1M_',  'monthRain','','','{:.1f}'),
                 ('RRD1MR',  '','','','{:.1f}'),
                 ('RRD1A_',  'yearRain','','','{:.1f}'),
                 ('RRD1AR',  '','','','{:.1f}'),
                 ('EVAD1M',  'monthET','','','{:.1f}'),
                 ('EVAD1A',  'yearET','','','{:.1f}'),
                 ('SOD1M_',  '','','','{:.2f}'),
                 ('SOD1MR',  '','','','{:.1f}'),
                 ('SOD1A_',  '','','','{:.2f}'),
                 ('SOD1AR',  '','','','{:.1f}'),
                 ('KLTSUM',  'cooldegsum','','','{:.1f}'),
                 ('WRMSUM',  'heatdegsum','','','{:.1f}'),
                 ('GRASUM',  'GTS','','','{:.1f}'),
                 ('GRADAT',  'GTSdate','','','date'),
                 ('TSOI10',  '','','','{:.1f}'),
                 ('TSOI20',  '','','','{:.1f}'),
                 ('TSOI50',  '','','','{:.1f}'),
                 ('WBMX1H',  'windGust','1h','max','{:.1f}'), # km/h
                 ('SSSUMG',  'radiationYesterdayIntegral','','','{:.0f}')
                ]

    # Note: The units Wetternetz Sachsen requests are not fully covered 
    # by one of the standard unit systems. See function __wns_umwandeln()
    # for details.
    _UNIT_MAP = {'group_rain':'mm',
                 'group_rainrate':'mm_per_hour',
                 'group_speed':'km_per_hour'
                }
                 
    def __init__(self, q, api_key, station='WNS', server_url=Wns.DEFAULT_URL,
                 skip_upload=False, manager_dict=None,
                 post_interval=None, max_backlog=sys.maxsize, stale=None,
                 log_success=True, log_failure=True,
                 timeout=60, max_tries=3, retry_wait=5,
                 T5AKT_=None,SOD1D_=None,TSOI10=None,TSOI20=None,TSOI50=None,
                 log_url=False):
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
        self.log_url = to_bool(log_url)
        
        # set up column name for 5cm temperature from weewx.conf
        try:
          if T5AKT_ is not None and T5AKT_!='None' and T5AKT_!='':
              for i,v in enumerate(self._DATA_MAP):
                if v[0]=='T5AKT_':
                  self._DATA_MAP[i]=('T5AKT_',str(T5AKT_),'','',self._DATA_MAP[i][4])
                elif v[0]=='T5MIN_':
                  self._DATA_MAP[i]=('T5MIN_',str(T5AKT_),'Day','min',self._DATA_MAP[i][4])
        except (ValueError,TypeError) as e:
          logerr("config value T5AKT_ is invalid: %s" % e)
        
        # set up column name for sunshine duration from weewx.conf
        try:
            if SOD1D_ is not None and SOD1D_.lower()!='none' and SOD1D_!='':
                for i,v in enumerate(self._DATA_MAP):
                    if v[0]=='SOD1H_':
                        self._DATA_MAP[i] = (v[0],str(SOD1D_),'1h','sum',self._DATA_MAP[i][4])
                    if v[0]=='SOD1D_':
                        self._DATA_MAP[i] = (v[0],str(SOD1D_),'Day','sum',self._DATA_MAP[i][4])
                    if v[0]=='SOD1M_':
                        self._DATA_MAP[i] = (v[0],str(SOD1D_),'Month','sum',self._DATA_MAP[i][4])
                    if v[0]=='SOD1A_':
                        self._DATA_MAP[i] = (v[0],str(SOD1D_),'Year','sum',self._DATA_MAP[i][4])
        except (ValueError,TypeError) as e:
            logerr("config value SOD1D_ is invalid: %s" % e)
        # report field names to syslog
        loginf("Fields: %s" % ';'.join(v[0] for v in self._DATA_MAP))

        # set up column name for 10cm soil temperature from weewx.conf
        try:
          if TSOI10 is not None and TSOI10!='None' and TSOI10!='':
              for i,v in enumerate(self._DATA_MAP):
                if v[0]=='TSOI10':
                  self._DATA_MAP[i]=('TSOI10',str(TSOI10),'','',self._DATA_MAP[i][4])
        except (ValueError,TypeError) as e:
          logerr("config value TSOI10 is invalid: %s" % e)
        
        # set up column name for 20cm soil temperature from weewx.conf
        try:
          if TSOI20 is not None and TSOI20!='None' and TSOI20!='':
              for i,v in enumerate(self._DATA_MAP):
                if v[0]=='TSOI20':
                  self._DATA_MAP[i]=('TSOI20',str(TSOI20),'','',self._DATA_MAP[i][4])
        except (ValueError,TypeError) as e:
          logerr("config value TSOI20 is invalid: %s" % e)
        
        # set up column name for 50cm soil temperature from weewx.conf
        try:
          if TSOI50 is not None and TSOI50!='None' and TSOI50!='':
              for i,v in enumerate(self._DATA_MAP):
                if v[0]=='TSOI50':
                  self._DATA_MAP[i]=('TSOI50',str(TSOI50),'','',self._DATA_MAP[i][4])
        except (ValueError,TypeError) as e:
          logerr("config value TSOI50 is invalid: %s" % e)
        
        # report unit map to syslog
        __x=""
        for __i in self._UNIT_MAP:
            __x="%s %s:%s" % (__x,__i,self._UNIT_MAP[__i])
        loginf("Special units:%s" % __x)

        # initialize variables for GTS
        self.last_gts_date = None
        self.gts_date = None
        self.gts_value = None
        weewx.units.obs_group_dict.setdefault('GTS','group_degree_day')
        weewx.units.obs_group_dict.setdefault('GTSdate','group_time')
        
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

        #loginf("GTS umw archive %s" % record['GTS'])
        #loginf("GTS umw metric %s" % record_m['GTS'])

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

        __data = [
            #'STA_ID': self.station,
            #'STAKEN': self.api_key,
            'WNS_V2.3', # TMPVER
            "WEEWX_%s" % (weewx.__version__), # WSOVER
            time.strftime("%H:%M",
                          time.gmtime(record_m['dateTime'])), # ZEIT__
            time.strftime("%d.%m.%Y",
                          time.gmtime(record_m['dateTime'])), # DATUM_
            # If 'ZEIT__' is in UTC, 'UTCDIF' needs to be 0.
            # If UTCDIF is '--', 'ZEIT__' is interpreted as local time.
            '0' # UTCDIF
            ]

        for v in self._DATA_MAP:
            # key
            key = v[0]
            # archive column name
            rkey = "%s%s%s" % (v[1],
                               v[2].capitalize(),
                               v[3].capitalize())
            # format string
            fstr = v[4]
            
            if (rkey in record_m and record_m[rkey] is not None):
                try:
                    # Note: The units Wetternetz Sachsen requests are
                    # not fully covered by one of the standard unit systems.
                    
                    # get value with individual unit
                    __vt = weewx.units.as_value_tuple(record_m,rkey)
                    # if unit group (__vt[2]) is defined in _UNIT_MAP
                    # convert to new unit
                    if __vt[2] in self._UNIT_MAP:
                        logdbg("%s convert unit from %.3f %s %s" % (rkey,__vt[0],__vt[1],__vt[2]))
                        __vt=weewx.units.convert(__vt,self._UNIT_MAP[__vt[2]])
                        logdbg("%s converted unit to %.3f %s %s" % (rkey,__vt[0],__vt[1],__vt[2]))

                    if key in ['SOD1D_','SOD1M_','SOD1A_']:
                        __vt = weewx.units.convert(__vt,'hour')
                        
                    # sunshine duration during the last hour
                    if key=='SOD1H_':
                        __vt = weewx.units.convert(__vt,'minute')
                        # There is a maximum of 60 min. of sunshine during
                        # 1 hour. For the value of 65.0 see next comment.
                        if __vt[0]>65.0:
                            raise ValueError("more than 60 min. of sunshine during 1 hour")
                        # If the sunshine duration ist measured in ticks
                        # the reading can be a little bit above 60 min.
                        # That could confuse limit checking at the other
                        # side.
                        if __vt[0]>60.0:
                            __vt = (60.0,__vt[1],__vt[2])

                    # format value to string
                    if __vt[2]=='group_time':
                        # date or time values
                        __data.append(time.strftime("%d.%m.%Y",
                                               time.gmtime(record_m[rkey])))
                    elif fstr == 'HH:MM':
                        if __vt[1]!='minute':
                            __vt = weewx.units.convert(__vt,'minute')
                        hour,min = divmod(__vt[0],60)
                        __data.append('%.0f:%02.0f' % (hour,min))
                    else:
                        # numeric values
                        __data.append(fstr.format(__vt[0]))
                except (TypeError,ValueError,IndexError,KeyError) as e:
                    logerr("%s:%s: %s" % (key,rkey,e))
                    __data.append('--')
            else:
                __data.append('--')
        return __data

    def format_url(self, record):
        """Return an URL for doing a POST to wns"""
        
        # create Wetternetz Sachsen dataset
        __data = WnsThread.__wns_umwandeln(self,record)
        
        # values concatenated by ';'
        __body = ";".join(__data)

        # build URL
        url = '%s?var=%s;%s;%s' % (self.server_url, 
                          self.station, self.api_key, __body)

        if self.log_url:
            loginf("url %s" % url)
        elif weewx.debug >= 2:
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
                    "SELECT SUM(radiation*`interval`)/60.0, "
                    "MIN(usUnits),MAX(usUnits) FROM %s "
                    "WHERE dateTime>? AND dateTime<=?"
                    % dbmanager.table_name,timespan)
            if _result is not None:
                if not _result[1] == _result[2]:
                    logerr("calculate radation integral: inconsistent units")
                    return None
                if weewx.debug >= 2:
                    logdbg("radiation integral %.1f" % _result[0])
                return _result[0]
        except weedb.OperationalError as e:
            log.debug("calculate radiation integral %s: Database OperationalError '%s'",self.protocol_name,e)
        except (ValueError, TypeError) as e:
            logerr("calculate radiation integral: %s" % e)
        return None
    
    def calc_gts(self,time_ts,dbmanager):
        """calculate Grünlandtemperatursumme GTS"""
        
        # needed timestamps
        _sod_ts = weeutil.weeutil.startOfDay(time_ts) # start of day
        _soy_ts = weeutil.weeutil.archiveYearSpan(time_ts)[0] # start of year
        _feb_ts = _soy_ts + 2678400 # Feb 1
        _mar_ts = _feb_ts + 2419200 # Mar 1 (or Feb 29 in leap year)
        _end_ts = _mar_ts + 7948800 # Jun 1 (or May 31 in leap year)
        
        # initialize if program start or new year
        if self.last_gts_date is None or self.last_gts_date < _soy_ts:
            self.last_gts_date = _soy_ts
            self.gts_value = None
            self.gts_date = None
            loginf("GTS initialized %s" %
                   time.strftime("%Y-%m-%d",
                                     time.localtime(_soy_ts)))
        
        # calculate
        # This runs one loop for every day since New Year at program 
        # start and after that once a day one loop, only. After May 31th
        # no loop is executed.
        _loop_ct=0
        while self.last_gts_date < _sod_ts and self.last_gts_date < _end_ts:
            # the day the average is calculated for
            _today = TimeSpan(self.last_gts_date,self.last_gts_date+86400)
            # calculate the average of the outside temperature
            _result = weewx.xtypes.get_aggregate('outTemp',_today,'avg',dbmanager)
            # convert to centrigrade
            if _result is not None:
                _result = weewx.units.convert(_result,'degree_C')
            # check condition and add to sum
            if _result is not None and _result[0] is not None:
                if self.gts_value is None:
                    self.gts_value=0
                _dayavg = _result[0]
                if _dayavg > 0:
                    if self.last_gts_date < _feb_ts:
                        _dayavg *= 0.5
                    elif self.last_gts_date < _mar_ts:
                        _dayavg *= 0.75
                    self.gts_value += _dayavg
                    if self.gts_value >= 200 and self.gts_date is None:
                        self.gts_date = self.last_gts_date
            # next day
            self.last_gts_date += 86400
            _loop_ct+=1
        
        if _loop_ct>0:
            loginf("GTS %s, %s loops" % (self.gts_value,_loop_ct))
        else:
            logdbg("GTS %s, %s loops" % (self.gts_value,_loop_ct))

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
        
        # debugging output to syslog
        if weewx.debug >= 2:
            logdbg("get_record dateTime %s, Tagesanfang %s, vor 1h %s" %
                (time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(_time_ts)),
                time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(_sod_ts)),
                time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.gmtime(_ago1_ts))))

        # get midnight-to-midnight time span according to Tom Keffer
        daytimespan = weeutil.weeutil.archiveDaySpan(_time_ts)
        # yesterday
        yesterdaytimespan = weeutil.weeutil.archiveDaySpan(_time_ts, days_ago=1)
        # get actual month
        monthtimespan = weeutil.weeutil.archiveMonthSpan(_time_ts)
        # get actual year
        yeartimespan = weeutil.weeutil.archiveYearSpan(_time_ts)
        # last 1, 3, 24 hours
        h1timespan = TimeSpan(_time_ts-3600,_time_ts)
        h3timespan = TimeSpan(_time_ts-10800,_time_ts)
        h24timespan = TimeSpan(_time_ts-86400,_time_ts)
        # last 10 minutes
        m10timespan = TimeSpan(_time_ts-600,_time_ts)
        
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
                
        # Grünlandtemperatursumme
        if 'GTS' not in _datadict:
            try:
                WnsThread.calc_gts(self,_time_ts,dbmanager)
                if self.gts_value is not None:
                    _datadict['GTS']=weewx.units.convertStd(
                      (self.gts_value,'degree_C_day','group_degree_day'),
                      _datadict['usUnits'])[0]
                if self.gts_date is not None:
                    _datadict['GTSdate']=self.gts_date
            except (ValueError,TypeError,IndexError) as e:
                logerr("GTS %s" % e)

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
            # rain sum of the last 10 minutes
            if 'rain10m' not in _datadict:
                _rain_sum = weewx.xtypes.get_aggregate('rain',m10timespan,'sum',dbmanager)
                _datadict['rain10m'] = weewx.units.convertStd(_rain_sum,_datadict['usUnits'])[0]
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
        
        # aggregation values
        for i,v in enumerate(self._DATA_MAP):
            # key
            __key=v[0]
            # field name
            __obs=v[1]
            # time span
            __tim=v[2]
            # aggregation type
            __agg=v[3]
            # aggregation field name
            __rky="%s%s%s" % (__obs,__tim,__agg.capitalize())
            # get aggregation if __tim and __agg are not empty
            if __tim!='' and __agg!='' and __rky not in _datadict:
                try:
                    # time span
                    if __tim=='1h':
                        __tts=h1timespan # 1 hour back from now
                    elif __tim=='3h':
                        __tts=h3timespan # 3 hours back from now
                    elif __tim=='24h':
                        __tts=h24timespan # 24 hours back from now
                    elif __tim=='Day':
                        __tts=daytimespan # the actual day local time
                    elif __tim=='Yesterday':
                        __tts=yesterdaytimespan # yesterday
                    elif __tim=='Month':
                        __tts=monthtimespan # the month the actual day is in
                    elif __tim=='Year':
                        __tts=yeartimespan # the year the actual day is in
                    else:
                        __tts=None
                    # get aggregate value
                    __result = weewx.xtypes.get_aggregate(__obs,__tts,__agg.lower(),dbmanager)
                    # register name with unit group if necessary
                    weewx.units.obs_group_dict.setdefault(__rky,__result[2])
                    # convert to unit system of _datadict
                    _datadict[__rky] = weewx.units.convertStd(__result,_datadict['usUnits'])[0]
                except Exception as e:
                    logerr("%s.%s.%s %s" % (__obs,__tim,__agg,e))
                
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
        
    def check_response(self,response):
        """Check the response from a HTTP post.
        
        check_response() is called in case, the http call returned
        success, only. That is for 200 <= response.code <= 299"""
    
        super(WnsThread,self).check_response(response)
        
        #for line in response:
        #    loginf("response %s" % line)
        #raise FailedPost()
        
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
