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
        return len(ret_str), ret_str

    def _get_percentage_complete(self, dl_len):
        assert self.conn_state.filesize != 0
        ret_str = str(dl_len * 100 / self.conn_state.filesize) + "%."
        return len(ret_str), ret_str

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
            ret_str = "%d %s." % (int(time_in_secs / mult_list[2]), \
                                      unit_list[3])
        return len(ret_str), ret_str

    def _get_pbar(self, width):
        ret_str = "["
        for i in range(self.n_conn):
            dots_list = ['=' for j in range((self.conn_state.progress[i] *
                                             width) /
                                            self.conn_state.chunks[i])]
            self.dots[i] = "".join(dots_list)
            if ret_str == "[":
                ret_str += self.dots[i]
            else:
                ret_str += "|" + self.dots[i]
            if len(self.dots[i]) < width:
                ret_str += '>'
                ret_str += "".join([' ' for i in range(width -
                                                       len(self.dots[i]) - 1)])

        ret_str += "]"
        return len(ret_str), ret_str

    def display_progress(self):
        dl_len = 0
        for rec in self.conn_state.progress:
            dl_len += rec

        assert(self.conn_state.elapsed_time > 0)
        avg_speed = dl_len / self.conn_state.elapsed_time

        ldr, drate = self._get_download_rate(avg_speed)
        lpc, pcomp = self._get_percentage_complete(dl_len)
        ltl, tleft = self._get_time_left((self.conn_state.filesize - dl_len) /
                                         avg_speed if avg_speed > 0 else 0)
        # term_width - #(|) + #([) + #(]) + #(strings) +
        # 6 (for spaces and periods)
        available_width = self._get_term_width() - (ldr + lpc +
                                                    ltl) - self.n_conn - 1 - 6
        lpb, pbar = self._get_pbar(available_width / self.n_conn)
        sys.stdout.flush()
        print "\r%s %s %s %s" % (drate, pcomp, tleft, pbar),

def report_bytes(bytes):
    if bytes == 0:
        return "0b"
    k = math.log(bytes, 1024)
    ret_str = "%.2f%s" % (bytes / (1024.0 ** int(k)), "bKMGTPEY"[int(k)])
    return ret_str

def get_block_size(fsize):
# This function copied from rapidleech source code
# http://rapidleech.googlecode.com/svn/trunk/classes/http.php
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

def get_file_size(url):
    request = urllib2.Request(url, None, std_headers)
    data = urllib2.urlopen(request)
    content_length = data.info()['Content-Length']
    # print content_length
    return int(content_length)

class FetchData(threading.Thread):

	def __init__(self, name, url, out_file, state_file,
				 start_offset, conn_state, filesize):
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
		self.filesize = filesize

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
		out_fd = os.open(self.out_file+".part", os.O_WRONLY)
		os.lseek(out_fd, self.start_offset, os.SEEK_SET)

		block_size = get_block_size(self.filesize)
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

def download(url, output_file, max_conns=4, max_speed=None, headers=std_headers):
	urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
	urllib2.install_opener(urllib2.build_opener(
			urllib2.HTTPCookieProcessor()))
	socket.setdefaulttimeout(120)         # 2 minutes
	fetch_threads = []
	try:
		print "Destination = %s" % output_file

		filesize = get_file_size(url)

		conn_state = ConnectionState(max_conns, filesize)
		#pbar = ProgressBar(max_conns, conn_state)

		# Checking if we have a partial download available and resume
		state_file = output_file + ".st"
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
		out_fd = os.open(output_file+".part", os.O_CREAT | os.O_WRONLY)

		start_offset = 0
		start_time = time.time()
		for i in range(max_conns):
			# each iteration should spawn a thread.
			# print start_offset, len_list[i]
			current_thread = FetchData(i, url, output_file, state_file,
									   start_offset + conn_state.progress[i],
									   conn_state, filesize)
			fetch_threads.append(current_thread)
			current_thread.start()
			start_offset += conn_state.chunks[i]

		while threading.active_count() > 1:
			#print "\n",progress
			end_time = time.time()
			conn_state.update_time_taken(end_time - start_time)
			start_time = end_time
			dwnld_sofar = conn_state.download_sofar()
			if max_speed != None and \
					(dwnld_sofar / conn_state.elapsed_time) > \
					(max_speed * 1024):
				print 'Throttling download speed'
				for th in fetch_threads:
					th.need_to_sleep = True
					th.sleep_timer = dwnld_sofar / (max_speed * \
						1024 - conn_state.elapsed_time)

			#pbar.display_progress()
			time.sleep(1)

		#pbar.display_progress()

		# at this point we are sure dwnld completed and can delete the
		# state file and move the dwnld to output file from .part file
		os.remove(state_file)
		os.rename(output_file+".part", output_file)

	except KeyboardInterrupt, k:
		for thread in fetch_threads:
			thread.need_to_quit = True

	except Exception, e:
		# TODO: handle other types of errors too.
		print e
		for thread in fetch_threads:
			thread._need_to_quit = True