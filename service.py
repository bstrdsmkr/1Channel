"""
    1Channel XBMC Addon
    Copyright (C) 2014 Bstrdsmkr, tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import json
import xbmc
import xbmcgui
import xbmcaddon
import utils
from utils import MODES
from db_utils import DB_Connection

ADDON = xbmcaddon.Addon(id='plugin.video.1channel')
utils.log('Service: Installed Version: %s' % (ADDON.getAddonInfo('version')))

db_connection = DB_Connection()
db_connection.init_database()

class Service(xbmc.Player):
    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self, *args, **kwargs)
        self.reset()

        self.last_run = 0
        self.DB = ''
        utils.log('Service: starting...')

    def reset(self):
        utils.log('Service: Resetting...')
        win = xbmcgui.Window(10000)
        win.clearProperty('1ch.playing.title')
        win.clearProperty('1ch.playing.year')
        win.clearProperty('1ch.playing.imdb')
        win.clearProperty('1ch.playing.season')
        win.clearProperty('1ch.playing.episode')
        win.clearProperty('1ch.playing.url')

        self._totalTime = 999999
        self._lastPos = 0
        self.tracking = False
        self.video_type = ''
        self.win = xbmcgui.Window(10000)
        self.win.setProperty('1ch.playing', '')
        self.meta = ''
        self.primewire_url = ''
        self.imdb_id = None

    def onPlayBackStarted(self):
        utils.log('Service: Playback started')
        meta = self.win.getProperty('1ch.playing')
        if meta:  # Playback is ours
            utils.log('Service: tracking progress...')
            self.tracking = True
            self.meta = json.loads(meta)
            self.video_type = 'tvshow' if 'episode' in self.meta else 'movie'
            if not 'year'    in self.meta: self.meta['year'] = ''
            if not 'season'  in self.meta: self.meta['season'] = ''
            if not 'episode' in self.meta: self.meta['episode'] = ''
            self.primewire_url = self.win.getProperty('1ch.playing.url')
            if 'imdb_id' in self.meta:
                self.imdb_id = self.meta['imdb_id']
            elif self.win.getProperty('1ch.playing.imdb'):
                self.imdb_id = self.win.getProperty('1ch.playing.imdb')
            else:
                self.imdb_id = None

            self._totalTime = 0
            while self._totalTime == 0:
                xbmc.sleep(1000)
                self._totalTime = self.getTotalTime()
                utils.log("Total Time: %s" % (self._totalTime), xbmc.LOGDEBUG)

    def onPlayBackStopped(self):
        utils.log('Service: Playback Stopped')
        # Is the item from our addon?
        if self.tracking:
            download_id = self.win.getProperty('download_id')
            if download_id:
                utils.log('Service: Stopping Axel Download: %s' % (download_id), xbmc.LOGDEBUG)
                import axelproxy as proxy
                axelhelper = proxy.ProxyHelper()
                axelhelper.stop_download(download_id)

            playedTime = int(self._lastPos)
            min_watched_percent = int(ADDON.getSetting('watched-percent'))
            try: percent_played = int((playedTime / self._totalTime) * 100)
            except: percent_played = 0  # guard div by zero
            pTime = utils.format_time(playedTime)
            tTime = utils.format_time(self._totalTime)
            utils.log('Service: Played %s of %s total = %s%%/%s%%' % (pTime, tTime, percent_played, min_watched_percent))
            videotype = 'movie' if self.video_type == 'movie' else 'episode'
            if playedTime == 0 and self._totalTime == 999999:
                raise RuntimeError('XBMC silently failed to start playback')
            elif (percent_played >= min_watched_percent):
                if (self.video_type == 'movie' or (self.meta['season'] and self.meta['episode'])):
                    utils.log('Service: Threshold met. Marking item as watched', xbmc.LOGDEBUG)
                    video_title = self.meta['title'] if self.video_type == 'movie' else self.meta['TVShowTitle']
                    dbid = self.meta['DBID'] if 'DBID' in self.meta else ''
                    builtin = 'RunPlugin(plugin://plugin.video.1channel/?mode=%s&imdbnum=%s&video_type=%s&title=%s&season=%s&episode=%s&year=%s&primewire_url=%s&dbid=%s&watched=%s)'
                    xbmc.executebuiltin(builtin % (MODES.CH_WATCH, self.imdb_id, videotype, video_title.strip(), self.meta['season'], self.meta['episode'], self.meta['year'], self.primewire_url, dbid, True))
                db_connection.clear_bookmark(self.primewire_url)
            elif playedTime > 0:
                utils.log('Service: Threshold not met. Setting bookmark on %s to %s seconds' % (self.primewire_url, playedTime), xbmc.LOGDEBUG)
                db_connection.set_bookmark(self.primewire_url, playedTime)
        self.reset()

    def onPlayBackEnded(self):
        utils.log('Service: Playback completed')
        self.onPlayBackStopped()

monitor = Service()
utils.do_startup_task(MODES.UPD_SUBS)
utils.do_startup_task(MODES.MOVIE_UPDATE)
utils.do_startup_task(MODES.BACKUP_DB)

while not xbmc.abortRequested:
    isPlaying = monitor.isPlaying()
    utils.do_scheduled_task(MODES.UPD_SUBS, isPlaying)
    utils.do_scheduled_task(MODES.MOVIE_UPDATE, isPlaying)
    utils.do_scheduled_task(MODES.BACKUP_DB, isPlaying)

    if monitor.tracking and monitor.isPlayingVideo():
        monitor._lastPos = monitor.getTime()

    xbmc.sleep(1000)
utils.log('Service: shutting down...')
