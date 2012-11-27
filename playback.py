import os
import Queue
import sys
import threading
import time
import xbmc
import xbmcgui
from t0mm0.common.addon import Addon
from metahandler import metahandlers

addon = Addon('plugin.video.1channel', sys.argv)
try:
	DB_NAME = 	 addon.get_setting('db_name')
	DB_USER = 	 addon.get_setting('db_user')
	DB_PASS = 	 addon.get_setting('db_pass')
	DB_ADDRESS = addon.get_setting('db_address')

	if  addon.get_setting('use_remote_db')=='true' and \
		DB_ADDRESS is not None and \
		DB_USER	   is not None and \
		DB_PASS    is not None and \
		DB_NAME    is not None:
		import mysql.connector as database
		addon.log('Loading MySQL as DB engine')
		DB = 'mysql'
	else:
		addon.log('MySQL not enabled or not setup correctly')
		raise ValueError('MySQL not enabled or not setup correctly')
except:
	try: 
		from sqlite3 import dbapi2 as database
		addon.log('Loading sqlite3 as DB engine')
	except: 
		from pysqlite2 import dbapi2 as database
		addon.log('pysqlite2 as DB engine')
	DB = 'sqlite'
	db_dir = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')

# Interval in millis to sleep when we're waiting around for 
# async xbmc events to take complete
SLEEP_MILLIS = 250

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
		xbmc.Player.__init__(self, xbmc.PLAYER_CORE_AUTO)
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
		sql = 'SELECT bookmark FROM bookmarks WHERE video_type=? AND title=? AND season=? AND episode=? AND year=?'
		if DB == 'mysql':
			sql = sql.replace('?','%s')
			db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
		else:
			db = database.connect(DB)
		cur = db.cursor()
		cur.execute(sql, (self.video_type, self.title, self.season, self.episode, self.year))
		bookmark = cur.fetchone()
		db.close()
		if bookmark:
			bookmark = float(bookmark[0])
			if not (self._sought and (bookmark-30 > 0)):
				question = 'Resume %s from %s?' %(self.title, format_time(bookmark))
				resume = xbmcgui.Dialog()
				resume = resume.yesno(self.title,'',question,'','Start from beginning','Resume')
				if resume: self.seekTime(bookmark)
				self._sought = True

	def onPlayBackStopped(self):
		addon.log('onPlayBackStopped')
		self._playbackLock.clear()

		playedTime = int(self._lastPos)
		watched_values = [.7, .8, .9]
		min_watched_percent = watched_values[int(addon.get_setting('watched-percent'))]
		addon.log('playedTime / totalTime : %s / %s = %s' % (playedTime, self._totalTime, playedTime/self._totalTime))
		if playedTime == 0 and self._totalTime == 999999:
			raise PlaybackFailed('XBMC silently failed to start playback')
		elif (((playedTime/self._totalTime) > min_watched_percent) and (self.video_type == 'movie' or (self.season and self.episode))):
			addon.log('Threshold met. Marking item as watched')
			self.ChangeWatched(self.imdbnum, self.video_type, self.title, self.season, self.episode, self.year, watched=7)
			sql = 'DELETE FROM bookmarks WHERE video_type=? AND title=? AND season=? AND episode=? AND year=?'
			if DB == 'mysql':
				sql = sql.replace('?','%s')
				db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
			else:
				db = database.connect(db_dir)
			cur = db.cursor()
			cur.execute(sql, (self.video_type, self.title, self.season, self.episode, self.year))
			db.commit()
			db.close()
		else:
			addon.log('Threshold not met. Saving bookmark')
			sql = 'REPLACE INTO bookmarks (video_type, title, season, episode, year, bookmark) VALUES(?,?,?,?,?,?)'
			if DB == 'mysql':
				sql = sql.replace('?','%s')
				db = database.connect(DB_NAME, DB_USER, DB_PASS, DB_ADDRESS, buffered=True)
			else:
				sql = 'INSERT or ' + sql
				db = database.connect(db_dir)
			cur = db.cursor()
			cur.execute(sql, (self.video_type, self.title, self.season,
							  self.episode, self.year, playedTime))
			db.commit()
			db.close()

	def onPlayBackEnded(self):
		self.onPlayBackStopped()
		addon.log('onPlayBackEnded')

	def _trackPosition(self):
		while self._playbackLock.isSet():
			try:
				self._lastPos = self.getTime()
			except:
				addon.log_debug('Error while trying to set playback time')
			addon.log_debug('Inside Player. Tracker time = %s' % self._lastPos)
			xbmc.sleep(SLEEP_MILLIS)
		addon.log('Position tracker ending with lastPos = %s' % self._lastPos)

	def ChangeWatched(self, imdb_id, video_type, name, season, episode, year='', watched='', refresh=False):
		# print "Change Watched: ", imdb_id, video_type, name, season, episode, year
		metaget=metahandlers.MetaData(False)
		metaget.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)

class PlaybackFailed(Exception):
	'''Raised to indicate that xbmc silently failed to play the stream'''