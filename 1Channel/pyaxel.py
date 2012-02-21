import cPickle
import math
import os
import socket
import sys
import threading
import time
import urllib2

std_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 6.1; '
        'en-US; rv:1.9.2) Gecko/20100115 Firefox/3.6',
    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
    'Accept': 'text/xml,application/xml,application/xhtml+xml,'
        'text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5',
    'Accept-Language': 'en-us,en;q=0.5',
}

# This function copied from rapidleech source code
# http://rapidleech.googlecode.com/svn/trunk/classes/http.php
def get_chunk_size(fsize):
	if fsize <= 1024 * 1024:
		return 4096;
	elif fsize <= 1024 * 1024 * 10:
		return 4096 * 10;		
	elif fsize <= 1024 * 1024 * 40:
		return 4096 * 30;		
	elif fsize <= 1024 * 1024 * 80:
		return 4096 * 47;		
	elif fsize <= 1024 * 1024 * 120:
		return 4096 * 65;		
	elif fsize <= 1024 * 1024 * 150:
		return 4096 * 70;		
	elif fsize <= 1024 * 1024 * 200:
		return 4096 * 85;		
	elif fsize <= 1024 * 1024 * 250:
		return 4096 * 100;		
	elif fsize <= 1024 * 1024 * 300:
		return 4096 * 115;		
	elif fsize <= 1024 * 1024 * 400:
		return 4096 * 135;		
	elif fsize <= 1024 * 1024 * 500:
		return 4096 * 170;		
	elif fsize <= 1024 * 1024 * 1000:
		return 4096 * 200;		
	return 4096 * 210;

def general_configuration():
		# General configuration
		urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
		urllib2.install_opener(urllib2.build_opener(
				urllib2.HTTPCookieProcessor()))
		socket.setdefaulttimeout(120)         # 2 minutes
		
def get_file_size(url):
		#print 'd-making header request'
		request = urllib2.Request(url, None, std_headers)
		data = urllib2.urlopen(request)
		#print 'd-header request completed'
		content_length = data.info()['Content-Length']
		return int(content_length)
		
#General function to pretty print byte size
def report_bytes(bytes):
		if bytes == 0:
			return "0b"
		k = math.log(bytes, 1024)
		ret_str = "%.2f%s" % (bytes / (1024.0 ** int(k)), "bKMGTPEY"[int(k)])
		return ret_str
		
class ConnectionState:
    def __init__(self, n_conn, filesize):
        self.n_conn = n_conn
        self.filesize = filesize
        self.progress = [0 for i in range(n_conn)]
        self.elapsed_time = 0
        self.chunks = [(filesize / n_conn) for i in range(n_conn)]
        self.chunks[0] += filesize % n_conn

    def download_sofar(self):
        dwnld_sofar = 0
        for rec in self.progress:
            dwnld_sofar += rec
        return dwnld_sofar

    def update_time_taken(self, elapsed_time):
        self.elapsed_time += elapsed_time

    def update_data_downloaded(self, fetch_size, conn_id):
        self.progress[conn_id] += fetch_size

    def resume_state(self, in_fd):
        try:
            saved_obj = cPickle.load(in_fd)
        except cPickle.UnpicklingError:
            print "State file is corrupted"
            #now start download from the beginning
            return 

        self.n_conn = saved_obj.n_conn
        self.filesize = saved_obj.filesize
        self.progress = saved_obj.progress
        self.chunks = saved_obj.chunks
        self.elapsed_time = saved_obj.elapsed_time

    def save_state(self, out_fd):
        #out_fd will be closed after save_state() is completed
        #to ensure that state is written onto the disk
        cPickle.dump(self, out_fd)

class ProgressBar:
    def __init__(self, n_conn, conn_state):
        self.n_conn = n_conn
        self.dots = ["" for i in range(n_conn)]
        self.conn_state = conn_state

    def _get_term_width(self):
        term_rows, term_cols = map(int, os.popen('stty size', \
                                                     'r').read().split())
        return term_cols

    def _get_download_rate(self, bytes):
        ret_str = report_bytes(bytes)
        ret_str += "/s."
        return ret_str

    def _get_percentage_complete(self, dl_len):
        assert self.conn_state.filesize != 0
        ret_str = str(dl_len * 100 / self.conn_state.filesize)
        return ret_str

    def _get_time_left(self, time_in_secs):
        ret_str = ""
        mult_list = [60, 60 * 60, 60 * 60 * 24]
        unit_list = ["second(s)", "minute(s)", "hour(s)", "day(s)"]
        for i in range(len(mult_list)):
            if time_in_secs < mult_list[i]:
                pval = int(time_in_secs / (mult_list[i - 1] if i > 0 else 1))
                ret_str = "%d %s" % (pval, unit_list[i])
                break
        if len(ret_str) == 0:
            ret_str = "%d %s" % (int(time_in_secs / mult_list[2]), \
                                      unit_list[3])
        return ret_str

    def display_progress(self):
        dl_len = 0
        for rec in self.conn_state.progress:
            dl_len += rec

        assert(self.conn_state.elapsed_time > 0)
        avg_speed = dl_len / self.conn_state.elapsed_time
        drate = self._get_download_rate(avg_speed)
        pcomp = self._get_percentage_complete(dl_len)
        tleft = self._get_time_left((self.conn_state.filesize - dl_len) /
                                         avg_speed if avg_speed > 0 else 0)
        return {
			"speed":drate, 
			"status":pcomp, 
			"time":tleft,
			}

class FetchData(threading.Thread):

	def __init__(self, name, url, out_file, state_file,
				 start_offset, conn_state):
		threading.Thread.__init__(self)
		self.name = name
		self.url = url
		self.out_file = out_file
		self.state_file = state_file
		self.start_offset = start_offset
		self.conn_state = conn_state
		self.length = conn_state.chunks[name] - conn_state.progress[name]
		self.sleep_timer = 0
		self.need_to_quit = False
		self.need_to_sleep = False
		

	def run(self):
		# Ready the url object
		print "Running thread with %d-%d" % (self.start_offset, self.length)
		request = urllib2.Request(self.url, None, std_headers)
		if self.length == 0:
			return
		request.add_header('Range', 'bytes=%d-%d' % (self.start_offset,
													 self.start_offset + \
													 self.length))
		while 1:
			try:
				data = urllib2.urlopen(request)
			except urllib2.URLError, u:
				print "Connection", self.name, " did not start with", u
			else:
				break

		# Open the output file
		#out_fd = os.open(self.out_file+".part", os.O_WRONLY)
		out_fd = os.open(self.out_file, os.O_WRONLY)
		os.lseek(out_fd, self.start_offset, os.SEEK_SET)
		#Use an optimal blocksize
		block_size = get_chunk_size(self.length)
		#indicates if connection timed out on a try
		while self.length > 0:
			if self.need_to_quit:
				return

			if self.need_to_sleep:
				time.sleep(self.sleep_timer)
				self.need_to_sleep = False

			if self.length >= block_size:
				fetch_size = block_size
			else:
				fetch_size = self.length
			try:
				data_block = data.read(fetch_size)
				if len(data_block) == 0:
					print "Connection %s: [TESTING]: 0 sized block" + \
						" fetched." % (self.name)
				if len(data_block) != fetch_size:
					print "Connection %s: len(data_block) != fetch_size" + \
						", but continuing anyway." % (self.name)
					self.run()
					return

			except socket.timeout, s:
				print "Connection", self.name, "timed out with", s
				self.run()
				return

			else:
				retry = 0

			#assert(len(data_block) == fetch_size)
			self.length -= fetch_size
			self.conn_state.update_data_downloaded(fetch_size, int(self.name))
			os.write(out_fd, data_block)
			self.start_offset += len(data_block)
			#saving state after each blk of dwnld
			state_fd = file(self.state_file, "wb")
			self.conn_state.save_state(state_fd)
			state_fd.close()

#Test an entire thread list for alive status
#A thread list is alive if at least one of them is alive
def is_thread_list_alive(list):
	for t in list:
		if t.is_alive() == True :
			return True
	return False

class Download(threading.Thread):
	fetch_threads = []
	complete = False
	progress = None
	def __init__(self,url,output_file,num_connections=4,callback=None):
		self.callback = callback
		self.url = url
		self.output_file = output_file
		self.num_connections = num_connections

		threading.Thread.__init__(self)
	def run(self):
		try:
			print "Saving download to: %s" % self.output_file
			#print 'd-trying to get filesize'
			
			filesize = get_file_size(self.url)
			#print 'd-Got filesize = ', filesize
			
			conn_state = ConnectionState(self.num_connections, filesize)
			#pbar = ProgressBar(self.num_connections, conn_state)
		
			#print 'd-connection state , progress bar created'
			
			# Checking if we have a partial download available and resume
			state_file = self.output_file + ".st"
			try:
				os.stat(state_file)
			except OSError, o:
				#statefile is missing for all practical purposes
				pass
			else:
				state_fd = file(state_file, "r")
				conn_state.resume_state(state_fd)
				state_fd.close()

			print "Need to fetch %s" % report_bytes(conn_state.filesize - sum(conn_state.progress))
			
			#create output file with a .part extension to indicate partial download
			#out_fd = os.open(self.output_file+".part", os.O_CREAT | os.O_WRONLY)
			out_fd = os.open(self.output_file, os.O_CREAT | os.O_WRONLY)
			#print 'd-open result ', out_fd
			#debug

			start_offset = 0
			start_time = time.time()
			for i in range(self.num_connections):
				# each iteration should spawn a thread.
				# print start_offset, len_list[i]
				current_thread = FetchData(i, self.url, self.output_file, state_file,
										   start_offset + conn_state.progress[i],
										   conn_state)
				self.fetch_threads.append(current_thread)
				current_thread.start()
				start_offset += conn_state.chunks[i]
			#This loop runs while the file is being downloaded
			#and updates the progress of the file download
			#a thread list remains alive till any of its members is alive
			while is_thread_list_alive(self.fetch_threads):
				end_time = time.time()
				conn_state.update_time_taken(end_time - start_time)
				start_time = end_time
				''' This is the sleep routine for putting sleep limits
					Disabled for now
				dwnld_sofar = conn_state.download_sofar()
				if options.max_speed != None and \
						(dwnld_sofar / conn_state.elapsed_time) > \
						(options.max_speed * 1024):
					for th in fetch_threads:
						th.need_to_sleep = True
						th.sleep_timer = dwnld_sofar / (options.max_speed * \
							1024 - conn_state.elapsed_time)
				'''
				#self.progress = pbar.display_progress()
				
				time.sleep(1)	#Doesnt make sense to eat up resources in updating progress
				
			# at this point we are sure dwnld completed and can delete the
			# state file and move the dwnld to output file from .part file
			for thread in self.fetch_threads:
				print 'Waiting for thread to exit'
				thread.join()
			self.complete = True
			print 'Deleting state file'
			os.remove(state_file)
			#os.rename(self.output_file+".part", self.output_file)
			os.rename(self.output_file+".part", self.output_file)
			if  self.callback != None:
				self.callback(self.url,self.output_file,self.num_connections)
			#print 'd-tc' , threading.active_count()
			
		except KeyboardInterrupt, k:
			for thread in self.fetch_threads:
				thread.need_to_quit = True

		except Exception, e:
			# TODO: handle other types of errors too.
			print e
			for thread in self.fetch_threads:
				thread._need_to_quit = True
	#Make threads quit
	def quit(self):
		for thread in self.fetch_threads:
				thread.need_to_quit = True