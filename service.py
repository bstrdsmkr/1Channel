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
import datetime
import _strptime # fix bug in python import
import json
import xbmc
import xbmcgui
import xbmcaddon
import utils
from db_utils import DB_Connection

db_connection = DB_Connection()
db_connection.init_database()

hours_list = [2, 5, 10, 15, 24]

ADDON = xbmcaddon.Addon(id='plugin.video.1channel')

# temporary method to migrate from old watched setting to new one
def mig_watched_setting():
    new_values=[70, 80, 90]
    watched=int(ADDON.getSetting('watched-percent'))
    if 0 <= watched <= 2:
        print "setting: %s, %s" % (watched, new_values[watched])
        ADDON.setSetting('watched-percent', str(new_values[watched]))

def ChangeWatched(imdb_id, video_type, name, season, episode, year='', watched=''):
    from metahandler import metahandlers

    metaget = metahandlers.MetaData(False)
    metaget.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)

class Service(xbmc.Player):
    def __init__(self, *args, **kwargs):
        xbmc.Player.__init__(self, *args, **kwargs)
        self.reset()

        self.last_run = 0
        self.DB = ''
        xbmc.log('PrimeWire: Service starting...')


    def reset(self):
        xbmc.log('PrimeWire: Service: Resetting...')
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
        self.primewire_url=''


    def onPlayBackStarted(self):
        xbmc.log('PrimeWire: Service: Playback started')
        meta = self.win.getProperty('1ch.playing')
        if meta: #Playback is ours
            xbmc.log('PrimeWire: Service: tracking progress...')
            self.tracking = True
            self.meta = json.loads(meta)
            self.video_type = 'tvshow' if 'episode' in self.meta else 'movie'
            if not 'year'    in self.meta: self.meta['year']    = ''
            if not 'imdb'    in self.meta: self.meta['imdb']    = None
            if not 'season'  in self.meta: self.meta['season']  = ''
            if not 'episode' in self.meta: self.meta['episode'] = ''
            self.primewire_url = self.win.getProperty('1ch.playing.url')

            self._totalTime=0
            while self._totalTime == 0:
                xbmc.sleep(1000)
                self._totalTime = self.getTotalTime()
                xbmc.log("Total Time: %s"   % (self._totalTime))

    def onPlayBackStopped(self):
        xbmc.log('PrimeWire: Playback Stopped')
        #Is the item from our addon?
        if self.tracking:
            DBID = self.meta['DBID'] if 'DBID' in self.meta else None
            playedTime = int(self._lastPos)
            min_watched_percent = int(ADDON.getSetting('watched-percent'))
            percent_played = int((playedTime / self._totalTime) * 100)
            pTime = utils.format_time(playedTime)
            tTime = utils.format_time(self._totalTime)
            xbmc.log('PrimeWire: Service: Played %s of %s total = %s%%/%s%%' % (pTime, tTime, percent_played, min_watched_percent))
            videotype = 'movie' if self.video_type == 'movie' else 'episode'
            if playedTime == 0 and self._totalTime == 999999:
                raise RuntimeError('XBMC silently failed to start playback')
            elif (percent_played >= min_watched_percent) and (
                        self.video_type == 'movie' or (self.meta['season'] and self.meta['episode'])):
                xbmc.log('PrimeWire: Service: Threshold met. Marking item as watched')
                # meta['DBID'] only gets set for strms in default.py
                if DBID:
                    if videotype == 'episode':
                        cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodeDetails", "params": {"episodeid": %s, "properties": ["playcount"]}, "id": 1}'
                        cmd = cmd %(DBID)
                        result = json.loads(xbmc.executeJSONRPC(cmd))
                        cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid": %s, "playcount": %s}, "id": 1}'
                        playcount = int(result['result']['episodedetails']['playcount']) + 1
                        cmd = cmd %(DBID, playcount)
                        result = xbmc.executeJSONRPC(cmd)
                        xbmc.log('PrimeWire: Marking episode .strm as watched: %s' %result)
                    if videotype == 'movie':
                        cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", "params": {"movieid": %s, "properties": ["playcount"]}, "id": 1}'
                        cmd = cmd %(DBID)
                        result = json.loads(xbmc.executeJSONRPC(cmd))
                        cmd = '{"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {"movieid": %s, "playcount": %s}, "id": 1}'
                        playcount = int(result['result']['moviedetails']['playcount']) + 1
                        cmd = cmd %(DBID, playcount)
                        result = xbmc.executeJSONRPC(cmd)
                        xbmc.log('PrimeWire: Marking movie .strm as watched: %s' %result)
                video_title = self.meta['title'] if self.video_type == 'movie' else self.meta['TVShowTitle']
                ChangeWatched(self.meta['imdb'], videotype,video_title.strip(), self.meta['season'], self.meta['episode'], self.meta['year'], watched=7)
                db_connection.clear_bookmark(self.primewire_url)
            elif playedTime>0:
                xbmc.log('PrimeWire: Service: Threshold not met. Setting bookmark on %s to %s seconds' % (self.primewire_url,playedTime))
                db_connection.set_bookmark(self.primewire_url,playedTime)
        self.reset()

    def onPlayBackEnded(self):
        xbmc.log('PrimeWire: Playback completed')
        self.onPlayBackStopped()
        
mig_watched_setting() # migrate from old 0, 1, 2 setting to actual value
monitor = Service()

if ADDON.getSetting('auto-update-movies-startup') == 'true' and not xbmc.abortRequested:
    xbmc.log('PrimeWire: Starting...Updating Movie Categories')
    now = datetime.datetime.now()
    xbmc.executebuiltin('RunPlugin(plugin://plugin.video.1channel/?mode=MovieAutoUpdate)')
    ADDON.setSetting('auto-update-movies-last-run', now.strftime("%Y-%m-%d %H:%M:%S.%f"))

if ADDON.getSetting('during-startup') == 'true' and not xbmc.abortRequested:
    xbmc.log('PrimeWire: Starting...Updating Subscriptions')
    now = datetime.datetime.now()
    xbmc.executebuiltin('RunPlugin(plugin://plugin.video.1channel/?mode=update_subscriptions)')
    ADDON.setSetting('last_run', now.strftime("%Y-%m-%d %H:%M:%S.%f"))

while not xbmc.abortRequested:
    now = datetime.datetime.now()
    if ADDON.getSetting('auto-update-subscriptions') == 'true':
        last_run = ADDON.getSetting('last_run')
        hours = hours_list[int(ADDON.getSetting('subscription-interval'))]

        last_run = datetime.datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S.%f")
        elapsed = now - last_run
        threshold = datetime.timedelta(hours=hours)
        #xbmc.log("Update Status: %s of %s" % (elapsed,threshold))
        if elapsed > threshold:
            is_scanning = xbmc.getCondVisibility('Library.IsScanningVideo')
            if not is_scanning:
                during_playback = ADDON.getSetting('during-playback')
                if during_playback == 'true' or not monitor.isPlaying():
                    xbmc.log('PrimeWire: Service: Updating subscriptions')
                    builtin = 'RunPlugin(plugin://plugin.video.1channel/?mode=update_subscriptions)'
                    xbmc.executebuiltin(builtin)
                    ADDON.setSetting('last_run', now.strftime("%Y-%m-%d %H:%M:%S.%f"))
                else:
                    xbmc.log('PrimeWire: Service: Playing... Busy... Postponing subscription update')
            else:
                xbmc.log('PrimeWire: Service: Scanning... Busy... Postponing subscription update')

    if ADDON.getSetting('auto-update-movies') == 'true':
        last_run = ADDON.getSetting('auto-update-movies-last-run')
        last_run = datetime.datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S.%f")
        elapsed = now - last_run
        update_interval = hours_list[int(ADDON.getSetting('auto-update-movies-interval'))]

        threshold = datetime.timedelta(hours=update_interval)
        if elapsed > threshold:
            is_scanning = xbmc.getCondVisibility('Library.IsScanningVideo')
            if not (monitor.isPlaying() or is_scanning):
                xbmc.log('PrimeWire: Service: Updating movies')
                xbmc.executebuiltin('RunPlugin(plugin://plugin.video.1channel/?mode=MovieAutoUpdate)')
                ADDON.setSetting('auto-update-movies-last-run', now.strftime("%Y-%m-%d %H:%M:%S.%f"))
            else:
                xbmc.log('PrimeWire: Service: Busy... Postponing movies update')

    if monitor.tracking and monitor.isPlayingVideo():
        monitor._lastPos = monitor.getTime()

    xbmc.sleep(1000)
xbmc.log('PrimeWire: Service: shutting down...')
