import os
import Queue
import sys
import threading
import time
import xbmc
import xbmcgui
from t0mm0.common.addon import Addon
from metahandler import metahandlers

# Interval in millis to sleep when we're waiting around for 
# async xbmc events to take complete
SLEEP_MILLIS = 250
addon = Addon('plugin.video.1channel', sys.argv)

# =============================================================================
class Player(xbmc.Player):

	def __init__(self):
		xbmc.Player.__init__(self)    
		self._active = True
		self._watched = False

	def __del__(self):
		addon.debug_log("\n\n\n\n\t\tGC'ing player\n\n\n")

	def play(self, item):
		assert not self.isPlaying(), 'Player is already playing a video'
		self._reset()

		xbmc.Player.play(self, item)
		self._waitForPlaybackCompleted()
		self._active = False
		return self._watched

	def getTracker(self):
		return self._tracker

	# Callbacks ---------------------------------------------------------------

	def onPlayBackStarted(self):
		if self._active:
			self._tracker.onPlayBackStarted()
			self._totalTime = self.getTotalTime()
			print '< onPlayBackStarted'

			
	def onPlayBackStopped(self):
		if self._active:
			try:
				try:
					print '> onPlayBackStopped'
					self._tracker.onPlayBackStopped()
				finally:
					self._playbackCompletedLock.set()
					print '< onPlayBackStopped'
			except:
				# Called on a separate thread -- log exceptions instead of raising them
				print 'onPlayBackStopped catchall'
			
	def onPlayBackEnded(self):
		if self._active:
			print 'self._active: %s' % self._active
			addon.log_debug('> onPlayBackEnded')
			self._tracker.onPlayBackStopped()

			playedTime = self._tracker.getLastPosition()
			watched_values = [.7, .8, .9]
			min_watched_percent = watched_values[int(addon.get_setting('watched-percent'))]
			if ((playedTime/self._totalTime) > min_watched_percent):
				print '******** playedTime / totalTime : %s / %s = %s' % (playedTime, self._totalTime, playedTime/self._totalTime)
				self._watched = True

			self._playbackCompletedLock.set()
			print '< onPlayBackEnded'


	# Private -----------------------------------------------------------------

	def _reset(self):
		self._playbackCompletedLock = threading.Event()
		self._playbackCompletedLock.clear()
		self._tracker = PositionTracker(self)
		self._totalTime = 1
		
	def _waitForPlaybackCompleted(self):
		while not self._playbackCompletedLock.isSet():
			#Addon.log_debug('Waiting for playback completed...')
			xbmc.sleep(SLEEP_MILLIS)

# =============================================================================
class PositionTracker(object):
    """
    Tracks the last position of the player. This is necessary because 
    Player.getTime() is not valid after the callback to 
    Player.onPlayBackStopped().  
    """
    
    HISTORY_SECS = 5  # Number of seconds of history to keep around

    def __init__(self, player):
        self._player = player
        self._lastPos = 0.0
        self._tracker = BoundedEvictingQueue((1000/SLEEP_MILLIS) * self.HISTORY_SECS)
        self._history = []
        
    def onPlayBackStarted(self):
        #addon.log_debug('Starting position tracker...')
        self._tracker = threading.Thread(
            name='Position Tracker', 
            target = self._trackPosition)
        self._tracker.start()
    
    def onPlayBackStopped(self):
        if self._tracker.isAlive():
            print 'Position tracker stop called. Still alive = %s' % self._tracker.isAlive()
        else:
            print 'Position tracker thread already dead.'

    def onPlayBackEnded(self):
        self.onPlayBackStopped()
        
    def getHistory(self, howFarBack):
        """Returns a list of the TrackerSamples from 'howFarBack' seconds ago to."""
        endPos = self._lastPos
        startPos = endPos - howFarBack
        slice = []
        for sample in self._history:
            if startPos <= sample.pos and sample.pos <= endPos:
                slice.append(sample)
        print 'Tracker history for %s secs = [%s] %s' % (howFarBack, len(slice), slice)
        return slice
    
    def getLastPosition(self):
        return self._lastPos
    
    def _trackPosition(self):
		"""Method run in a separate thread. Tracks last position of player as long as it is playing"""
		while self._player.isPlaying():
			self._lastPos = self._player.getTime()
			self._history.append(TrackerSample(time.time(), self._lastPos))
			addon.log_debug('Tracker time = %s' % self._lastPos)
			xbmc.sleep(SLEEP_MILLIS)
		print 'Position tracker thread exiting with lastPos = %s' % self.getLastPosition()


# =============================================================================
class TrackerSample(object):
    
    def __init__(self, time, pos):
        self.time = time
        self.pos  = pos
    
    def __repr__(self):
        return 'Sample {time = %s, pos = %s}' % (self.time, self.pos)

# =============================================================================
class BoundedEvictingQueue(object):
    """
    Queue with a fixed size that evicts objects in FIFO order when capacity
    has been reached. 
    """

    def __init__(self, size):
        self._queue = Queue.Queue(size)
        
    def empty(self):
        return self._queue.empty()
    
    def qsize(self):
        return self._queue.qsize()
    
    def full(self):
        return self._queue.full()
    
    def put(self, item):
        if self._queue.full():
            self._queue.get()
        self._queue.put(item, False, None)
        
    def get(self):
        return self._queue.get(False, None)
