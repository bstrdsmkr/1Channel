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

def stream(self, url, savfile='', headers=std_headers, max_conns=4,
			 block_size=265*1024, chunk_size=1024*1024, max_retries=10):
    try:
        urllib_conf()
        url = args[0]
        download(url, self.savfile)

    except KeyboardInterrupt, k:
        sys.exit(1)

    except Exception, e:
        # TODO: handle other types of errors too.
        print e

class FileWriter:
    def __init__(self, filename):
        try:
            self.fd = os.open(filename,
                              os.O_CREAT | os.O_WRONLY)
        except OSError, e:
            # TODO: stop all threads and exit
            print 'Error opening file: %s' % e.message

    def seek(self, offset):
        try:
            os.lseek(self.fd, offset, os.SEEK_SET)
        except OSError, e:
            print "Seek error: %s" % (e.message)

    def write(self, block):
        try:
            os.write(self.fd, block)
        except OSError, e:
            print "Write error: %s" % (e.message)

    def close(self):
        try:
            os.close(self.fd)
        except OSError, e:
            print "File close error: %s" % (e.message)

class DownloadState:
    def __init__(self, n_conn, url, filesize, filename):
        self.n_conn = n_conn
        self.filesize = filesize
        self.filename = filename
        self.url = url
        self.continue_offset = 0
        self.todo_ranges = []
        self.inprogress_ranges = {}
        self.inprogress_lock = threading.Lock()
        self.elapsed_time = 0

    def update_inprogress_entry(self, thread_id, byte_offsets):
        self.inprogress_lock.acquire()
        self.inprogress_ranges[thread_id] = byte_offsets
        self.inprogress_lock.release()

    def delete_inprogress_entry(self, thread_id):
        self.inprogress_lock.acquire()
        del self.inprogress_ranges[thread_id]
        self.inprogress_lock.release()

    def write_state(self):
        pass

class JobTracker:
	def __init__(self, download_state, block_size, chunk_size):
		self.download_state = download_state
		filesize = download_state.filesize
		self.job_count = (filesize + block_size - 1) / block_size
		self.next_todo_job = 0
		self.lock = threading.Lock()
		self.chunk_size = chunk_size

	def __get_next_chunk(self):
		start = self.download_state.continue_offset
		lefttogo = self.download_state.filesize - start
		length = min(self.chunk_size, lefttogo)
		print 'Chunk length: %s' % report_bytes(length)
		print 'Chunk size: %s' % report_bytes(self.chunk_size)
		print 'Filesize: %s' % report_bytes(self.download_state.filesize)
		print 'Start: %s' % report_bytes(start)
		print 'Left to go: %s' % report_bytes(lefttogo)
		if length <= 0:
			return False
		end = start + length - 1
		self.download_state.continue_offset += length
		return (start, end)

	def get_next_job(self):
		self.lock.acquire()
		if self.download_state.todo_ranges:
			r = self.download_state.todo_ranges.pop()
			print 'Get next Job returning:', r
		else:
			r = self.__get_next_chunk()
			print 'Get next Job returning:', r
		self.lock.release()
		return r

class Worker(threading.Thread):
	def __init__(self, name, download_state, job_tracker,
				 max_retries, block_size, headers):
		threading.Thread.__init__(self, name=name)
		self.download_state = download_state
		self.job_tracker = job_tracker
		self.start_offset = 0
		self.end_offset = 0
		self.fwriter = FileWriter(download_state.filename + ".part")
		self._need_to_quit = False
		self.isFailing = False
		self.max_retries = max_retries
		self.block_size = block_size
		self.headers = headers

	def __update_offsets(self, job):
		self.start_offset, self.end_offset = job

	def __download_range(self):
		attempts = 0
		remote_file = None
		data_block = None
		while attempts < self.max_retries:
			try:
				print 'Requesting byte range: %d-%d' % (self.start_offset,self.end_offset)
				request = urllib2.Request(self.download_state.url, None, self.headers)
				request.add_header('Range', 'bytes=%d-%d' % (self.start_offset,
															 self.end_offset))
				remote_file = urllib2.urlopen(request)
				self.fwriter.seek(self.start_offset)
				bytes_read = 0
				while True:
					data_block = remote_file.read(self.block_size)
					if not data_block:
						self.download_state.delete_inprogress_entry(self.name)
						return
					bytes_read += len(data_block)
					self.fwriter.write(data_block)
					self.download_state.update_inprogress_entry(self.name,
						(self.start_offset + bytes_read, self.end_offset))
					if self._need_to_quit:
						return
			except urllib2.URLError:
				attempts += 1
			except IOError:
				self.start_offset += bytes_read
				attempts += 1
		if attempts >= self.max_retries:
			self.isFailing = True

	def run(self):
		job = self.job_tracker.get_next_job()
		while job:
			print 'Job:', job
			self.__update_offsets(job)
			self.__download_range()
			self.download_state.write_state()
			if self._need_to_quit or self.isFailing:
				break
			job = self.job_tracker.get_next_job()
		self.fwriter.close()
		print 'Leaving run loop'

def get_file_size(url, headers):
    request = urllib2.Request(url, None, headers)
    data = urllib2.urlopen(request)
    content_length = data.info()['Content-Length']
    print 'Get file size: %s' % content_length
    return int(content_length)

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

def report_bytes(bytes):
    if bytes == 0:
        return "0b"
    k = math.log(bytes, 1024)
    ret_str = "%0.2f%s" % (bytes / (1024.0 ** int(k)), "bKMGTPEY"[int(k)])
    return ret_str

def download(url, output_file, headers=std_headers, max_conns=4,
			 chunk_size=1024*1024, max_retries=10):
	fetch_threads = []
	try:
		print "Saving stream as: ", output_file

		filesize = get_file_size(url,headers)
		print "Need to fetch %s bytes" % report_bytes(filesize)
		block_size = get_block_size(filesize)
		print 'Setting block_size to: %s' % report_bytes(block_size)

		download_state = DownloadState(max_conns, url,
									   filesize, output_file)
		job_tracker = JobTracker(download_state, block_size, chunk_size)

		for i in range(max_conns):
			current_thread = Worker(i, download_state, job_tracker,
									max_retries, block_size, headers)
			fetch_threads.append(current_thread)
			current_thread.start()

		isFailing = False
		while threading.active_count() > 1:
			for thread in fetch_threads:
				if thread.isFailing == True:
					isFailing = True
					break
			if isFailing:
				for thread in fetch_threads:
					thread._need_to_quit = True
			time.sleep(1)
		
		# # at this point we are sure dwnld completed and can delete the
		# # state file and move the dwnld to output file from .part file
		# os.remove(state_file)
		if isFailing:
			print "File downloading failed!"

	except KeyboardInterrupt, k:
		print "KeyboardInterrupt! Quitting."
		for thread in fetch_threads:
			thread._need_to_quit = True

	except Exception, e:
		# TODO: handle other types of errors too.
		print e
		for thread in fetch_threads:
			thread._need_to_quit = True

def urllib_conf():
    # General configuration
    urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler()))
    urllib2.install_opener(urllib2.build_opener(
            urllib2.HTTPCookieProcessor()))
    socket.setdefaulttimeout(120)         # 2 minutes