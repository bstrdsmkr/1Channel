import os

# workaround for bug in Python imports
import datetime
# noinspection PyUnresolvedReferences
import _strptime
# noinspection PyUnresolvedReferences
import time

import xbmc
import xbmcgui
import xbmcaddon


ADDON = xbmcaddon.Addon(id='plugin.video.1channel')

try:
    DB_NAME = ADDON.getSetting('db_name')
    DB_USER = ADDON.getSetting('db_user')
    DB_PASS = ADDON.getSetting('db_pass')
    DB_ADDRESS = ADDON.getSetting('db_address')

    if ADDON.getSetting('use_remote_db') == 'true' and \
                    DB_ADDRESS is not None and \
                    DB_USER is not None and \
                    DB_PASS is not None and \
                    DB_NAME is not None:
        import mysql.connector as database

        try: xbmc.log('PrimeWire: Service: Loading MySQL as DB engine')
        except: pass
        DB = 'mysql'
    else:
        try: xbmc.log('PrimeWire: Service: MySQL not enabled or not setup correctly')
        except: pass
        raise ValueError('MySQL not enabled or not setup correctly')
except:
    try:
        from sqlite3 import dbapi2 as database

        try: xbmc.log('PrimeWire: Service: Loading sqlite3 as DB engine')
        except: pass
    except:
        from pysqlite2 import dbapi2 as database

        try: xbmc.log('PrimeWire: Service: Loading pysqlite2 as DB engine')
        except: pass
    DB = 'sqlite'
    db_dir = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')


def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    if minutes > 60:
        hours, minutes = divmod(minutes, 60)
        return "%02d:%02d:%02d" % (hours, minutes, seconds)
    else:
        return "%02d:%02d" % (minutes, seconds)


def ChangeWatched(imdb_id, video_type, name, season, episode, year='', watched=''):
    from metahandler import metahandlers

    metaget = metahandlers.MetaData(False)
    metaget.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)


class Service(xbmc.Player):
    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self, *args, **kwargs)
        self.reset()

        self.last_run = 0
        hours_list = [2, 5, 10, 15, 24]
        selection = int(ADDON.getSetting('subscription-interval'))
        self.hours = hours_list[selection]
        self.DB = ''
        try: xbmc.log('PrimeWire: Service starting...')
        except: pass

    def reset(self):
        try: xbmc.log('PrimeWire: Service: Resetting...')
        except: pass
        win = xbmcgui.Window(10000)
        win.clearProperty('1ch.playing.title')
        win.clearProperty('1ch.playing.year')
        win.clearProperty('1ch.playing.imdb')
        win.clearProperty('1ch.playing.season')
        win.clearProperty('1ch.playing.episode')

        self._totalTime = 999999
        self._lastPos = 0
        self._sought = False
        self.tracking = False
        self.imdbnum = ''
        self.video_type = ''
        self.title = ''
        self.season = ''
        self.episode = ''
        self.year = ''

    def check(self):
        win = xbmcgui.Window(10000)
        if win.getProperty('1ch.playing.title'):
            return True
        else:
            return False

    def onPlayBackStarted(self):
        try: xbmc.log('PrimeWire: Service: Playback started')
        except: pass
        self.tracking = self.check()
        if self.tracking:
            try: xbmc.log('PrimeWire: Service: tracking progress...')
            except: pass
            win = xbmcgui.Window(10000)
            self.title = win.getProperty('1ch.playing.title')
            self.imdb = win.getProperty('1ch.playing.imdb')
            self.season = win.getProperty('1ch.playing.season')
            self.year = win.getProperty('1ch.playing.year')
            self.episode = win.getProperty('1ch.playing.episode')
            if self.season or self.episode:
                self.video_type = 'tvshow'
            else:
                self.video_type = 'movie'
            self._totalTime = self.getTotalTime()
            sql = 'SELECT bookmark FROM bookmarks WHERE video_type=? AND title=? AND season=? AND episode=? AND year=?'
            if DB == 'mysql':
                sql = sql.replace('?', '%s')
                db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
            else:
                db = database.connect(db_dir)
            cur = db.cursor()
            cur.execute(sql, (self.video_type, unicode(self.title, 'utf-8'), self.season, self.episode, self.year))
            bookmark = cur.fetchone()
            db.close()
            if bookmark:
                bookmark = float(bookmark[0])
                if not (self._sought and (bookmark - 30 > 0)):
                    question = 'Resume %s from %s?' % (self.title, format_time(bookmark))
                    resume = xbmcgui.Dialog()
                    resume = resume.yesno(self.title, '', question, '', 'Start from beginning', 'Resume')
                    if resume: self.seekTime(bookmark)
                    self._sought = True

    def onPlayBackStopped(self):
        try: xbmc.log('PrimeWire: Playback Stopped')
        except: pass
        if self.tracking:
            playedTime = int(self._lastPos)
            watched_values = [.7, .8, .9]
            min_watched_percent = watched_values[int(ADDON.getSetting('watched-percent'))]
            percent = int((playedTime / self._totalTime) * 100)
            pTime = format_time(playedTime)
            tTime = format_time(self._totalTime)
            try: xbmc.log('PrimeWire: Service: %s played of %s total = %s%%' % (pTime, tTime, percent))
            except: pass
            if playedTime == 0 and self._totalTime == 999999:
                raise RuntimeError('XBMC silently failed to start playback')
            elif ((playedTime / self._totalTime) > min_watched_percent) and (
                        self.video_type == 'movie' or (self.season and self.episode)):
                try: xbmc.log('PrimeWire: Service: Threshold met. Marking item as watched')
                except: pass
                if self.video_type == 'movie':
                    videotype = 'movie'
                else:
                    videotype = 'episode'
                ChangeWatched(self.imdb, videotype, self.title, self.season, self.episode, self.year, watched=7)
                sql = 'DELETE FROM bookmarks WHERE video_type=? AND title=? AND season=? AND episode=? AND year=?'
                if DB == 'mysql':
                    sql = sql.replace('?', '%s')
                    db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
                else:
                    db = database.connect(db_dir)
                cur = db.cursor()
                cur.execute(sql, (self.video_type, unicode(self.title, 'utf-8'), self.season, self.episode, self.year))
                db.commit()
                db.close()
            else:
                try: xbmc.log('PrimeWire: Service: Threshold not met. Saving bookmark')
                except: pass
                sql = 'REPLACE INTO bookmarks (video_type, title, season, episode, year, bookmark) VALUES(?,?,?,?,?,?)'
                if DB == 'mysql':
                    sql = sql.replace('?', '%s')
                    db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
                else:
                    sql = 'INSERT or ' + sql
                    db = database.connect(db_dir)
                cur = db.cursor()
                cur.execute(sql, (self.video_type, unicode(self.title, 'utf-8'), self.season,
                                  self.episode, self.year, playedTime))
                db.commit()
                db.close()
        self.reset()

    def onPlayBackEnded(self):
        try: xbmc.log('PrimeWire: Playback completed')
        except: pass
        self.onPlayBackStopped()


monitor = Service()
while not xbmc.abortRequested:
    if ADDON.getSetting('auto-update-subscriptions') == 'true':
        now = datetime.datetime.now()
        last_run = ADDON.getSetting('last_run')
        last_run = datetime.datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S.%f")
        elapsed = now - last_run
        threshold = datetime.timedelta(hours=monitor.hours)
        if elapsed > threshold:
            is_scanning = xbmc.getCondVisibility('Library.IsScanningVideo')
            if not (monitor.isPlaying() or is_scanning):
                try: xbmc.log('PrimeWire: Service: Updating subscriptions')
                except: pass
                builtin = 'RunPlugin(plugin://plugin.video.1channel/?mode=update_subscriptions)'
                xbmc.executebuiltin(builtin)
                ADDON.setSetting('last_run', now.strftime("%Y-%m-%d %H:%M:%S.%f"))
            else:
                try: xbmc.log('PrimeWire: Service: Busy... Postponing subscription update')
                except: pass
    while monitor.tracking and monitor.isPlayingVideo():
        monitor._lastPos = monitor.getTime()
        xbmc.sleep(1000)
    xbmc.sleep(1000)
try: xbmc.log('PrimeWire: Service: shutting down...')
except: pass
