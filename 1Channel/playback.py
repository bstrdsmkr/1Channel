import os
import Queue
import sys
import threading
import time
import xbmc
import xbmcgui
from t0mm0.common.addon import Addon
from metahandler import metahandlers

import trace

# Interval in millis to sleep when we're waiting around for 
# async xbmc events to take complete
SLEEP_MILLIS = 250
addon = Addon('plugin.video.1channel', sys.argv)

# =============================================================================
class Player(xbmc.Player):

	def __init__(self, imdbnum, videotype, title, season, episode, year):
		xbmc.Player.__init__(self)
		self._playbackLock = threading.Event()
		self._playbackLock.set()
		# self._tracker = PositionTracker(self)
		self._totalTime = 999999
		self._lastPos = 0
		self.imdbnum = imdbnum
		self.videotype = videotype
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

	def onPlayBackStopped(self):
		addon.log('> onPlayBackStopped')
		self._playbackLock.clear()

		playedTime = self._lastPos
		watched_values = [.7, .8, .9]
		min_watched_percent = watched_values[int(addon.get_setting('watched-percent'))]
		addon.log('playedTime / totalTime : %s / %s = %s' % (playedTime, self._totalTime, playedTime/self._totalTime))
		if ((playedTime/self._totalTime) > min_watched_percent):
			self.ChangeWatched(self.imdbnum, self.videotype, self.title, self.season, self.episode, self.year, watched=7)
			addon.log('Threshold met. Marking item as watched')
		else: addon.log('Threshold not met. Not changing watched status')

	def onPlayBackEnded(self):
		self.onPlayBackStopped()
		addon.log('onPlayBackEnded')

	def _trackPosition(self):
		while self._playbackLock.isSet():
			self._lastPos = self.getTime()
			addon.log_debug('Inside Player. Tracker time = %s' % self._lastPos)
			xbmc.sleep(SLEEP_MILLIS)
		addon.log('Position tracker ending with lastPos = %s' % self._lastPos)

	def ChangeWatched(self, imdb_id, videoType, name, season, episode, year='', watched='', refresh=False):
		metaget=metahandlers.MetaData(False)
		metaget.change_watched(videoType, name, imdb_id, season=season, episode=episode, year=year, watched=watched)

# =============================================================================
# class PositionTracker(object):
	# """
	# Tracks the last position of the player. This is necessary because 
	# Player.getTime() is not valid after the callback to 
	# Player.onPlayBackStopped().  
	# """

	# HISTORY_SECS = 5  # Number of seconds of history to keep around

	# def __init__(self, player):
		# self._player = player
		# self._history = BoundedEvictingQueue((1000/SLEEP_MILLIS) * self.HISTORY_SECS)
		# self._tracker = KThread(name='Position Tracker', target = self._trackPosition)
		# self._tracker.setDaemon(True)
		# addon = Addon('plugin.video.1channel', sys.argv)

	# def onPlayBackStarted(self):
		# addon.log('Starting position tracker...')
		# self._tracker.start()

	# def onPlayBackStopped(self):
		# if self._tracker.isAlive():
			# addon.log('Position tracker stop called. Still alive = %s' % self._tracker.isAlive())
		# else:
			# addon.log('Position tracker thread already dead.')

	# def onPlayBackEnded(self):
		# self.onPlayBackStopped()

	# def getLastPosition(self):
		# return self._player._lastPos

	# def _trackPosition(self):
		# """Method run in a separate thread. Tracks last position of player as long as it is playing"""
		# addon.log('Position tracker starting loop')
		# while self._player.isPlaying():
			# self._player._lastPos = self._player.getTime()
			# self._history.put(TrackerSample(time.time(), self._player._lastPos))
			# addon.log_debug('Tracker time = %s' % self._player._lastPos)
			# xbmc.sleep(SLEEP_MILLIS)
		# print 'Position tracker thread exiting with lastPos = %s' % self.getLastPosition()


# =============================================================================
# class TrackerSample(object):
    
    # def __init__(self, time, pos):
        # self.time = time
        # self.pos  = pos
    
    # def __repr__(self):
        # return 'Sample {time = %s, pos = %s}' % (self.time, self.pos)

# =============================================================================
# class BoundedEvictingQueue(object):
    # """
    # Queue with a fixed size that evicts objects in FIFO order when capacity
    # has been reached. 
    # """

    # def __init__(self, size):
        # self._queue = Queue.Queue(size)
        
    # def empty(self):
        # return self._queue.empty()
    
    # def qsize(self):
        # return self._queue.qsize()
    
    # def full(self):
        # return self._queue.full()
    
    # def put(self, item):
        # if self._queue.full():
            # self._queue.get()
        # self._queue.put(item, False, None)
        
    # def get(self):
        # return self._queue.get(False, None)

# =============================================================================
# class KThread(threading.Thread):
	# """A subclass of threading.Thread, with a kill()
	# method."""
	# def __init__(self, *args, **keywords):
		# threading.Thread.__init__(self, *args, **keywords)
		# self.killed = False

	# def start(self):
		# """Start the thread."""
		# self.__run_backup = self.run
		# self.run = self.__run # Force the Thread to install our trace.
		# threading.Thread.start(self)

	# def __run(self):
		# """Hacked run function, which installs the
		# trace."""
		# sys.settrace(self.globaltrace)
		# self.__run_backup()
		# self.run = self.__run_backup

	# def globaltrace(self, frame, why, arg):
		# if why == 'call':
			# return self.localtrace
		# else:
			# return None

	# def localtrace(self, frame, why, arg):
		# if self.killed:
			# if why == 'line':
				# addon.log('Killing position tracker')
				# raise SystemExit()
		# return self.localtrace

	# def kill(self):
		# self.killed = True