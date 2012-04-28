import os
import Queue
import sys
import threading
import time
import xbmc
import xbmcgui
from t0mm0.common.addon import Addon
from metahandler import metahandlers

try:
	from sqlite3 import dbapi2 as sqlite
	print "Loading sqlite3 as DB engine"
except:
	from pysqlite2 import dbapi2 as sqlite
	print "Loading pysqlite2 as DB engine"

# Interval in millis to sleep when we're waiting around for 
# async xbmc events to take complete
SLEEP_MILLIS = 250
DB = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')
addon = Addon('plugin.video.1channel', sys.argv)

def format_time(seconds):
	minutes,seconds = divmod(seconds, 60)
	if minutes > 60:
		hours,minutes = divmod(minutes, 60)
		return "%02d:%02d:%02d" % (hours, minutes, seconds)
	else:
		return "%02d:%02d" % (minutes, seconds)

# =============================================================================
class Player(xbmc.Player):

	def __init__(self, imdbnum, video_type, title, season, episode, year):
		xbmc.Player.__init__(self)
		self._playbackLock = threading.Event()
		self._playbackLock.set()
		self._totalTime = 999999
		self._lastPos = 0
		self._sought = False
		self.imdbnum = imdbnum
		self.video_type = video_type
		self.title = title
		self.season = season
		self.episode = episode
		self.year = year
		addon.log('Player created')

	def __del__(self):
		addon.log("\n\n\n\n\t\tGC'ing player\n\n\n")

	def onPlayBackStarted(self):
		addon.log('Beginning Playback')
		self._totalTime = self.getTotalTime()
		self._tracker = threading.Thread(target=self._trackPosition)
		self._tracker.start()
		db = sqlite.connect(DB)
		bookmark = db.execute('SELECT bookmark FROM bookmarks WHERE video_type=? AND title=? AND season=? AND episode=? AND year=?', (self.video_type, self.title, self.season, self.episode, self.year)).fetchone()
		db.close()
		if not self._sought and bookmark[0] and bookmark[0]-30 > 0:
			question = 'Resume %s from %s?' %(self.title, format_time(bookmark))
			resume = xbmcgui.Dialog()
			resume = resume.yesno(self.title,'',question,'','Start from beginning','Resume')
			if resume: self.seekTime(bookmark)
			self._sought = True


	def onPlayBackStopped(self):
		addon.log('> onPlayBackStopped')
		self._playbackLock.clear()

		playedTime = self._lastPos
		watched_values = [.7, .8, .9]
		min_watched_percent = watched_values[int(addon.get_setting('watched-percent'))]
		addon.log('playedTime / totalTime : %s / %s = %s' % (playedTime, self._totalTime, playedTime/self._totalTime))
		if playedTime == 0 and self._totalTime == 999999:
			raise PlaybackFailed('XBMC silently failed to start playback')
		elif ((playedTime/self._totalTime) > min_watched_percent):
			addon.log('Threshold met. Marking item as watched')
			self.ChangeWatched(self.imdbnum, self.video_type, self.title, self.season, self.episode, self.year, watched=7)
			db = sqlite.connect(DB)
			db.execute('DELETE FROM bookmarks WHERE video_type=? AND title=? AND season=? AND episode=? AND year=?', (self.video_type, self.title, self.season, self.episode, self.year))
			db.commit()
			db.close()
		else:
			addon.log('Threshold not met. Saving bookmark')
			db = sqlite.connect(DB)
			db.execute('INSERT OR REPLACE INTO bookmarks (video_type, title, season, episode, year, bookmark) VALUES(?,?,?,?,?,?)',
					  (self.video_type, self.title, self.season, self.episode, self.year, playedTime))
			db.commit()
			db.close()

	def onPlayBackEnded(self):
		self.onPlayBackStopped()
		addon.log('onPlayBackEnded')

	def _trackPosition(self):
		while self._playbackLock.isSet():
			self._lastPos = self.getTime()
			addon.log_debug('Inside Player. Tracker time = %s' % self._lastPos)
			xbmc.sleep(SLEEP_MILLIS)
		addon.log('Position tracker ending with lastPos = %s' % self._lastPos)

	def ChangeWatched(self, imdb_id, video_type, name, season, episode, year='', watched='', refresh=False):
		metaget=metahandlers.MetaData(False)
		metaget.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)

class PlaybackFailed(Exception):
	'''Raised to indicate that xbmc silently failed to play the stream'''