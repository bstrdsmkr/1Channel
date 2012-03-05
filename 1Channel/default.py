'''
    1Channel XBMC Addon
    Copyright (C) 2012 Bstrdsmkr

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
'''

import re
import os
import string
import sys
import urllib2
import urllib
import urlresolver
import zipfile
import xbmcgui
import xbmcplugin
import xbmc, xbmcvfs
#import pyaxel
import time

from t0mm0.common.addon import Addon
from t0mm0.common.net import Net
from metahandler import metahandlers
from metahandler import metacontainers
import metapacks

try:
	from sqlite3 import dbapi2 as sqlite
	print "Loading sqlite3 as DB engine"
except:
	from pysqlite2 import dbapi2 as sqlite
	print "Loading pysqlite2 as DB engine"

ADDON = Addon('plugin.video.1channel', sys.argv)
DB = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')

META_ON = ADDON.get_setting('use-meta') == 'true'
FANART_ON = ADDON.get_setting('enable-fanart') == 'true'
USE_POSTERS = ADDON.get_setting('use-posters') == 'true'
POSTERS_FALLBACK = ADDON.get_setting('posters-fallback') == 'true'

AZ_DIRECTORIES = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y', 'Z']
BASE_URL = 'http://www.1channel.ch'
USER_AGENT = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.3) Gecko/2008092417 Firefox/3.0.3'
GENRES = ['Action', 'Adventure', 'Animation', 'Biography', 'Comedy', 
          'Crime', 'Documentary', 'Drama', 'Family', 'Fantasy', 'Game-Show', 
          'History', 'Horror', 'Japanese', 'Korean', 'Music', 'Musical', 
          'Mystery', 'Reality-TV', 'Romance', 'Sci-Fi', 'Short', 'Sport', 
          'Talk-Show', 'Thriller', 'War', 'Western', 'Zombies']

prepare_zip = False
metaget=metahandlers.MetaData(preparezip=prepare_zip)

if not os.path.isdir(ADDON.get_profile()):
     os.makedirs(ADDON.get_profile())

def AddOption(text, isFolder, mode, letter=None, section=None, sort=None, genre=None, query=None, page=None, img=None):
	li = xbmcgui.ListItem(text)
	fanart = os.path.join(ADDON.get_path(),'fanart.jpg')
	li.setProperty('fanart_image', fanart)
	if img is not None:
		img = os.path.join(ADDON.get_path(),'art',img)
		li.setIconImage(img)
		li.setThumbnailImage(img)
	print 'Adding option with params:\n Text: %s\n Folder: %s\n Mode %s\n Letter: %s\n Section: %s\n Sort: %s\n Genre: %s' %(text, isFolder,mode, letter, section, sort, genre)
	url = sys.argv[0]+'?mode=' + str(mode)
	if letter  is not None: url += '&letter=%s'  % letter
	if section is not None: url += '&section=%s' % section
	if sort    is not None: url += '&sort=%s'	 % sort
	if genre   is not None: url += '&genre=%s'	 % genre
	if query   is not None: url += '&query=%s'	 % query
	if page    is not None: url += '&page=%s'	 % page
	
	return xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=li, isFolder=isFolder)

def unicode_urlencode(value): 
	if isinstance(value, unicode): 
		return urllib.quote(value.encode("utf-8"))
	else: 
		return urllib.quote(value)


def initDatabase():
	print "Building 1channel Database"
	if not os.path.isdir( os.path.dirname( DB ) ):
		os.makedirs( os.path.dirname( DB ) )
	db = sqlite.connect( DB )
	db.execute('CREATE TABLE IF NOT EXISTS seasons (season UNIQUE, contents)')
	db.execute('CREATE TABLE IF NOT EXISTS favorites (type, name, url, year)')
	db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_fav ON favorites (name, url)')
#####Begin db upgrade code
	try: db.execute('SELECT year FROM favorites')
	except: 
		print 'Upgrading db...'
		try:
			with db:
				db.execute('CREATE TABLE favoritesbackup (type,name,url)')
				db.execute('INSERT INTO favoritesbackup SELECT type,name,url FROM favorites')
				db.execute('DROP TABLE favorites')
				db.execute('CREATE TABLE favorites(type,name,url)')
				db.execute('INSERT INTO favorites SELECT type,name,url FROM favoritesbackup')
				db.execute('DROP TABLE favoritesbackup')
				db.execute('ALTER TABLE favorites ADD COLUMN year')
				db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_fav ON favorites (name, url)')
		except: print 'Failed to upgrade db'
#####End db upgrade code
	db.commit()
	db.close()

def SaveFav(type, name, url, img, year): #8888
	if type != 'tv': type = 'movie'
	db = sqlite.connect( DB )
	cursor = db.cursor()
	statement  = 'INSERT INTO favorites (type, name, url, year) VALUES (?,?,?,?)'
	try: 
		cursor.execute(statement, (type, urllib.unquote_plus(name), url, year))
		builtin = 'XBMC.Notification(Save Favorite,Added to Favorites,2000)'
		xbmc.executebuiltin(builtin)
	except sqlite.IntegrityError: 
		builtin = 'XBMC.Notification(Save Favorite,Item already in Favorites,2000)'
		xbmc.executebuiltin(builtin)
	db.commit()
	db.close()

def DeleteFav(type, name, url): #7777
	if type != 'tv': type = 'movie'
	print 'Deleting Fav: %s\n %s\n %s\n' % (type,name,url)
	db = sqlite.connect( DB )
	cursor = db.cursor()
	cursor.execute('DELETE FROM favorites WHERE type=? AND name=? AND url=?', (type, name, url))
	db.commit()
	db.close()

def GetURL(url, params = None, referrer = BASE_URL, cookie = None, save_cookie = False, silent = False):
	if params: req = urllib2.Request(url, params)
		# req.add_header('Content-type', 'application/x-www-form-urlencoded')
	else: req = urllib2.Request(url)

	req.add_header('User-Agent', USER_AGENT)
	req.add_header('Host', 'www.1channel.ch')
	if referrer: req.add_header('Referer', referrer)
	if cookie: req.add_header('Cookie', cookie)

	print 'Fetching URL: %s' % url
	
	try:
		response = urllib2.urlopen(req, timeout=10)
		body = response.read()
	except:
		if not silent:
			dialog = xbmcgui.Dialog()
			dialog.ok("Connection failed", "Failed to connect to url", url)
			print "Failed to connect to URL %s" % url
			return ''

	if save_cookie:
		setcookie = response.info().get('Set-Cookie', None)
		#print "Set-Cookie: %s" % repr(setcookie)
		if setcookie:
			setcookie = re.search('([^=]+=[^=;]+)', setcookie).group(1)
			body = body + '<cookie>' + setcookie + '</cookie>'

	response.close()
	return body

def GetSources(url, title='', img='', update='', year='', imdbnum='', video_type='', season='', episode=''): #10
	url	  = urllib.unquote(url)
	print 'Title befor unquote %s' % title
	#title = urllib.unquote(title)
	#title = title.decode('utf-8')
	print 'Title is %s' % title
	print 'Playing: %s' % url
	videotype = None
	match = re.search('tv-\d{1,10}-(.*)/season-(\d{1,4})-episode-(\d{1,4})', url, re.IGNORECASE | re.DOTALL)
	if match:
		videotype = 'tv'
		season = int(match.group(2))
		episode = int(match.group(3))	
	net = Net()
	cookiejar = ADDON.get_profile()
	cookiejar = os.path.join(cookiejar,'cookies')
	html = net.http_GET(url).content
	net.save_cookies(cookiejar)
	adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
	r = re.search(adultregex, html, re.DOTALL)
	if r:
		print 'Adult content url detected'
		adulturl = BASE_URL + r.group(1)
		headers = {'Referer': url}
		net.set_cookies(cookiejar)
		html = net.http_GET(adulturl, headers=headers).content #.encode('utf-8', 'ignore')

	if update:
		imdbregex = 'mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"'
		r = re.search(imdbregex, html)
		if r:
			imdbnum = r.group(1)
			metaget.update_meta('movie',title,imdb_id='',
								new_imdb_id=imdbnum,year=year)
	titleregex = '<meta property="og:title" content="(.*?)">'
	r = re.search(titleregex,html)
	title = r.group(1)
	sources = []
	for version in re.finditer('<table[^\n]+?class="movie_version(?: movie_version_alt)?">(.*?)</table>',
								html, re.DOTALL|re.IGNORECASE):
		for s in re.finditer('quality_(?!sponsored|unknown)(.*?)></span>.*?'+
							 'url=(.*?)&(?:amp;)?domain=(.*?)&(?:amp;)?(.*?)'+
							 '"version_veiws">(.*?)</',
							 version.group(1), re.DOTALL):
			q, url, host,parts, views = s.groups()
			r = '\[<a href=".*?url=(.*?)&(?:amp;)?.*?".*?>(part [0-9]*)</a>\]'
			additional_parts = re.findall(r, parts, re.DOTALL|re.IGNORECASE)
			verified = s.group(0).find('star.gif') > -1
			label = '[%s]  ' % q.upper()
			label += host.decode('base-64')
			if additional_parts: label += ' Part 1'
			if verified: label += ' [verified]'
			label += ' (%s)' % views.strip()
			url = url.decode('base-64')
			host = host.decode('base-64')
			print 'Source found:\n quality %s\n url %s\n host %s\n views %s\n' % (q, url, host, views)
			try:
				hosted_media = urlresolver.HostedMediaFile(url=url, title=label)
				sources.append(hosted_media)
				if additional_parts:
					for part in additional_parts:
						label = '     [%s]  ' % q.upper()
						label += host
						label += ' ' + part[1]
						if verified: label += ' [verified]'
						#label += ' (%s)' % views.strip()
						url = part[0].decode('base-64')
						hosted_media = urlresolver.HostedMediaFile(url=url, title=label)
						sources.append(hosted_media)
			except:
				print 'Error while trying to resolve %s' % url

	source = urlresolver.choose_source(sources)
	if source:
		stream_url = source.resolve()
		print 'Attempting to play url: %s' % stream_url
		playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
		playlist.clear()
		listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
		if videotype == 'tv': listitem.setInfo('video', {'TVShowTitle': title, 'Season': season, 'Episode': episode } )		
		playlist.add(url=stream_url, listitem=listitem)
		xbmc.Player().play(playlist)
		if ADDON.get_setting('auto-watch') == 'true':
			Autowatch()
            
            
def Autowatch():
    #Begin auto-watch code
    xbmc.executebuiltin("XBMC.Container.Refresh")
    watched_values = [.7, .8, .9]
    min_watched_percent = watched_values[int(ADDON.get_setting('watched-percent'))]
    currentTime = 1
    totalTime = 20
    while(1):
        if xbmc.Player().isPlayingVideo():
            totalTime=xbmc.Player().getTotalTime()
            currentTime=xbmc.Player().getTime()
        else: 
            if ((currentTime/totalTime) > min_watched_percent):
                print '******** currentTime / totalTime : %s / %s = %s' % (currentTime, totalTime, currentTime/totalTime)
                ChangeWatched(imdbnum, video_type, title, season, episode, year, watched=7,refresh=True)
                break
            elif currentTime > 30: #Essentially a timeout.  30 seconds without starting the video.
                break
        xbmc.sleep(1000)
  
def ChangeWatched(imdb_id, videoType, name, season, episode, year='', watched='', refresh=False):
    metaget=metahandlers.MetaData(preparezip=prepare_zip)
    metaget.change_watched(videoType, name, imdb_id, season=season, episode=episode, year=year, watched=watched)
    if refresh:
        xbmc.executebuiltin("XBMC.Container.Refresh")

#	profile = ADDON.get_profile()
#	if not os.path.isdir(profile):
#		os.makedirs(profile)
#	print 'Downloading %s' % stream_url
#	mediafile = os.path.join(profile, 'temp.flv')
#	t = pyaxel.Download(stream_url, 'c:/temp.flv', num_connections=8)
#	t.start()
#	playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
#	listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
#	playlist.add(url=mediafile, listitem=listitem)
	#xbmc.sleep(10000)
#	xbmc.Player().play(playlist)
#	playlist.clear()



def PlayTrailer(url): #250
	url = url.decode('base-64')
	print 'Attempting to resolve and play trailer at %s' % url
	sources = []
	hosted_media = urlresolver.HostedMediaFile(url=url)
	sources.append(hosted_media)
	source = urlresolver.choose_source(sources)
	if source: stream_url = source.resolve()
	else: stream_url = ''
	xbmc.Player().play(stream_url)

def GetSearchQuery(section):
	last_search = ADDON.load_data('search')
	if not last_search: last_search = ''
	keyboard = xbmc.Keyboard()
	if section == 'tv': keyboard.setHeading('Search TV Shows')
	else: keyboard.setHeading('Search Movies')
	keyboard.setDefault(last_search)
	keyboard.doModal()
	if (keyboard.isConfirmed()):
		search_text = keyboard.getText()
		ADDON.save_data('search',search_text)
		if search_text.startswith('!#'):
			if search_text == '!#create metapacks': create_meta_packs()
			if search_text == '!#repair meta'	  : repair_missing_images()
			if search_text == '!#install all meta': install_all_meta()
		else:
			Search(section, keyboard.getText())
	else:
		BrowseListMenu(section)

def Search(section, query):
	#TODO: Combine this with GetFilteredResults
	html = GetURL(BASE_URL)
	r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
	pageurl = BASE_URL + '/index.php?search_keywords='
	pageurl += urllib.quote_plus(query)
	pageurl += '&key=' + r
	if section == 'tv':
		setView('tvshows', 'tvshows-view')
		pageurl += '&search_section=2'
		nextmode = '?mode=4000'
		type = 'tvshow'
	else:
		setView('movies', 'movies-view')
		nextmode = '?mode=10'
		type = 'movie'
	html = '> >> <'
	page = 0

	while html.find('> >> <') > -1 and page < 10:
		page += 1
		if page > 1: pageurl += '&page=%s' % page
		html = GetURL(pageurl)

		r = re.search('number_movies_result">([0-9,]+)', html)
		if r: total = int(r.group(1).replace(',', ''))
		else: total = 0

		r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
		regex = re.finditer(r, html, re.DOTALL)
		resurls = []
		for s in regex:
			resurl,title,year,thumb = s.groups()
			meta = {}
			if resurl not in resurls:
				resurls.append(resurl)
				cm = []
				if year: disptitle = title +'('+year+')'
				else: disptitle = title
				update = False
				img = thumb

				if META_ON:
					try:
						if type == 'tvshow':
							meta = metaget.get_meta(type, title, year=year)
							if meta['tvdb_id'] =='' and meta['imdb_id'] =='':
								update = True
						elif type == 'movie':
							meta = metaget.get_meta(type, title, year=year)
							if meta['imdb_id'] =='':
								update = True
							if meta['trailer_url']:
								url = meta['trailer_url']
								url = re.sub('&feature=related','',url)
								url = url.encode('base-64').strip()
								runstring = 'RunScript(plugin.video.1channel,%s,?mode=250&url=%s)' %(sys.argv[1],url)
								cm.append(('Watch Trailer', runstring))

						if type == 'tvshow'and not USE_POSTERS:
							meta['cover_url'] = meta['banner_url']
						if POSTERS_FALLBACK and meta['cover_url'] in ('/images/noposter.jpg',''):
							meta['cover_url'] = thumb
						img = meta['cover_url']
					except: update = True

				listitem = xbmcgui.ListItem(disptitle, iconImage=img, thumbnailImage=img)
				try: listitem.setInfo(type="Video", infoLabels=meta)
				except: pass
				title = unicode_urlencode(title)
				runstring = 'RunScript(plugin.video.1channel,%s,?mode=8888&section=%s&title=%s&url=%s&year=%s)'\
							%(sys.argv[1],section,title,BASE_URL+resurl,year)
				cm.append(('Show Information', 'XBMC.Action(Info)'))
				cm.append(('Add to Favorites', runstring))
				listitem.addContextMenuItems(cm, replaceItems=True)
				try: listitem.setProperty('fanart_image', meta['backdrop_url'])
				except: pass
				resurl = BASE_URL + resurl
				liurl = sys.argv[0] + nextmode
				liurl += '&title=' + title
				liurl += '&img='	 + thumb
				liurl += '&url=' + resurl
				if update: liurl += '&update=1'
				xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=liurl, listitem=listitem, 
							isFolder=True, totalItems=total)

	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def AddonMenu():  #homescreen
	print '1Channel menu'
	AddOption('Movies',  True, 500, section=None, img='movies.jpg')
	AddOption('TV shows',True, 500, section='tv', img='television.jpg')
	AddOption('Resolver Settings',True, 9999, img='settings.jpg')
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseListMenu(section=None): #500
	AddOption('A-Z',		  True, 1000, section=section, img='atoz.jpg')
	AddOption('Search',		  True, 6000, section=section, img='search.jpg', query=query)
	AddOption('Favorites',	  True, 8000, section=section, img='favourites.jpg')
	AddOption('Genres',		  True, 2000, section=section, img='genres.jpg')
	AddOption('Featured', 	  True, 3000, section=section, img='featured.jpg', sort='featured')
	AddOption('Most Popular', True, 3000, section=section, img='most_popular.jpg', sort='views')	
	AddOption('Highly rated', True, 3000, section=section, img='highly_rated.jpg', sort='ratings')
	AddOption('Date released',True, 3000, section=section, img='date_released.jpg', sort='release')	
	AddOption('Date added',	  True, 3000, section=section, img='date_added.jpg', sort='date')
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseAlphabetMenu(section=None): #1000
	print 'Browse by alphabet screen'
	AddOption('#123',True,3000,letter='123', section=section, genre=genre, sort='alphabet')
	for character in AZ_DIRECTORIES:
		AddOption(character,True,3000,letter=character, section=section, genre=genre, sort='alphabet')
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseByGenreMenu(section=None, letter=None): #2000
	print 'Browse by genres screen'
	for g in GENRES:
		AddOption(g,True,3000,genre=g,section=section,sort=None)
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def GetFilteredResults(section=None, genre=None, letter=None, sort='alphabet', page=None): #3000
	print 'Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s' % \
			(section, genre, letter, sort, page)
	if section == 'tv':	xbmcplugin.setContent( int( sys.argv[1] ), 'tvshows' )
	else: xbmcplugin.setContent( int( sys.argv[1] ), 'movies' )

	liurl = BASE_URL + '/?'
	if section == 'tv': liurl += 'tv'
	if genre  is not None:	liurl += '&genre='  + genre
	if letter is not None:	liurl += '&letter=' + letter
	if sort   is not None:	liurl += '&sort='	+ sort
	pageurl = liurl
	if page: pageurl += '&page=%s' % page

	if section == 'tv':
		nextmode = '?mode=4000'
		type = 'tvshow'
	else:
		nextmode = '?mode=10'
		section = 'movie'
		type = 'movie'

	html = GetURL(pageurl)

	r = re.search('number_movies_result">([0-9,]+)', html)
	if r: total = int(r.group(1).replace(',', ''))
	else: total = 0
	total = min(total,24)

	r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
	regex = re.finditer(r, html, re.DOTALL)
	resurls = []
	for s in regex:
		resurl,title,year,thumb = s.groups()
		meta = {}
		if resurl not in resurls:
			resurls.append(resurl)
			cm = []
			if year: disptitle = title +'('+year+')'
			else: disptitle = title
			update = False
			img = thumb

			if META_ON:
				try:
					if type == 'tvshow':
						meta = metaget.get_meta(type, title, year=year)
						if meta['imdb_id'] =='' and meta['tvdb_id'] =='':
							update = True

					elif type == 'movie':
						meta = metaget.get_meta(type,title,year=year)
						if meta['imdb_id'] =='':
							update = True

						if meta['trailer_url']:
							url = meta['trailer_url']
							url = re.sub('&feature=related','',url)
							url = url.encode('base-64').strip()
							runstring = 'RunScript(plugin.video.1channel,%s,?mode=250&url=%s)' %(sys.argv[1],url)
							cm.append(('Watch Trailer', runstring))
					
					if type == 'tvshow'and not USE_POSTERS:
						meta['cover_url'] = meta['banner_url']
					if POSTERS_FALLBACK and meta['cover_url'] in ('/images/noposter.jpg',''):
						meta['cover_url'] = thumb
					img = meta['cover_url']
				except: update = True

			listitem = xbmcgui.ListItem(unicode(disptitle, 'latin1'), iconImage=img, thumbnailImage=img)
			try: listitem.setInfo(type="Video", infoLabels=meta)
			except: pass
			title = unicode_urlencode(title)
			resurl = BASE_URL + resurl
			liurl = sys.argv[0] + nextmode
			liurl += '&title=' + urllib.quote(title)
			liurl += '&url=' + resurl
			liurl += '&img=' + thumb
			liurl += '&imdbnum=' + meta['imdb_id']
			liurl += '&videoType=' + type
			if update: liurl += '&update=1'
			print 'liurl is: %s' % liurl
			runstring = 'RunScript(plugin.video.1channel,%s,?mode=8888&section=%s&title=%s&url=%s&year=%s)' %(sys.argv[1],section,title,resurl,year)
			cm.append(('Add to Favorites', runstring))
			cm.append(('Show Information', 'XBMC.Action(Info)'))
			listitem.addContextMenuItems(cm, replaceItems=True)
			if FANART_ON:
				try: listitem.setProperty('fanart_image', meta['backdrop_url'])
				except: pass
			print 'URL is %s' % liurl
			xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=liurl, listitem=listitem, 
						isFolder=True, totalItems=total)
	if page is not None: page = int(page) + 1
	else: page = 2
	if html.find('> >> <') > -1:
		AddOption('Next Page >>', True, 3000, section=section, genre=genre, letter=letter, sort=sort, page=page)
	xbmcplugin.endOfDirectory(int(sys.argv[1]))
	if section == 'tv':  setView('tvshows', 'tvshows-view')
	else: setView('movies', 'movies-view')

def TVShowSeasonList(url, title, year, update=''): #4000
	print 'Seasons for TV Show %s' % url
	net = Net()
	cookiejar = ADDON.get_profile()
	cookiejar = os.path.join(cookiejar,'cookies')
	html = net.http_GET(url).content
	net.save_cookies(cookiejar)
	adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
	r = re.search(adultregex, html, re.DOTALL)
	if r:
		print 'Adult content url detected'
		adulturl = BASE_URL + r.group(1)
		headers = {'Referer': url}
		net.set_cookies(cookiejar)
		html = net.http_GET(adulturl, headers=headers).content #.encode('utf-8', 'ignore')

	cnxn = sqlite.connect( DB )
	cnxn.text_factory = str
	cursor = cnxn.cursor()
	if year: title = title +'('+year+')'
	try:
		imdbnum = re.search('mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"', html).group(1)
	except: imdbnum = ''
	seasons = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
	if not seasons: ADDON.log_error('couldn\'t find seasons')
	else:
		season_container = seasons.group(1)
		season_nums = re.compile('<a href=".+?">Season ([0-9]{1,2})').findall(season_container)
		if imdbnum and META_ON: 
			metaget.update_meta('tvshow', title, imdbnum, year=year)
			season_meta = metaget.get_seasons(title, imdbnum, season_nums)
			if update:
				metaget.update_meta('tvshow', title, imdb_id='',
									new_imdb_id=imdbnum, year=year)
		seasonList = season_container.split('<h2>')
		num = 0
		temp = {}
		for eplist in seasonList:
			r = re.search('<a.+?>(.+?)</a>', eplist)
			if r:
				season_name = r.group(1)
				try: 	temp = season_meta[num]
				except: temp['cover_url'] = ''
				listitem = xbmcgui.ListItem(season_name, iconImage=temp['cover_url'], thumbnailImage=temp['cover_url'])
				listitem.setInfo(type="Video", infoLabels=temp)
				if FANART_ON:
					try: listitem.setProperty('fanart_image', meta['backdrop_url'])
					except: pass
				season_name = unicode_urlencode(season_name).lower()
				cursor.execute('INSERT or REPLACE into seasons (season,contents) VALUES(?,?);',
								(season_name, eplist))
				url = sys.argv[0]+ '?mode=5000'+'&season=' +season_name+ '&imdbnum='+imdbnum
				xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=listitem, 
											isFolder=True)
				cnxn.commit()
				num += 1
		setView('seasons', 'seasons-view')
		xbmcplugin.endOfDirectory(int(sys.argv[1]))
		cnxn.close()

def TVShowEpisodeList(season, imdbnum): #5000
	cnxn = sqlite.connect( DB )
	cnxn.text_factory = str
	cursor = cnxn.cursor()
	eplist = cursor.execute('SELECT contents FROM seasons WHERE season=?', (season,))
	eplist = eplist.fetchone()[0]
	r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
	episodes = re.finditer(r, eplist, re.DOTALL)
	cm = []
	cm.append(('Show Information', 'XBMC.Action(Info)'))
	for ep in episodes:
		epurl, title = ep.groups()
		meta = {}
		title = re.sub('<[^<]+?>', '', title.strip())
		title = re.sub('\s\s+' , ' ', title)
		title = urllib.unquote_plus(title)
		name = re.search('/(tv|watch)-[0-9]+-(.+?)/season-', epurl).group(2)
		name = re.sub('-',' ',name)
		season = re.search('/season-([0-9]{1,4})-', epurl).group(1)
		epnum = re.search('-episode-([0-9]{1,3})', epurl).group(1)
		if META_ON:
			try:
				meta = metaget.get_episode_meta(name=name,imdb_id=imdbnum,season=season, episode=epnum)
			except:
				meta['cover_url'] = ''
				meta['backdrop_url'] = ''
				print 'Error getting metadata for %s season %s episode %s with imdbnum %s' % (name,season,epnum,imdbnum)
		else:
			meta['cover_url'] = ''
		img = meta['cover_url']
		listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
		listitem.setInfo(type="Video", infoLabels=meta)
		if FANART_ON:
			try: listitem.setProperty('fanart_image', meta['backdrop_url'])
			except: pass
		listitem.addContextMenuItems(cm)
		url = '%s?mode=10&url=%s&title=%s&img=%s&imdbnum=%s&videoType=episode&season=%s&episode=%s' % \
				(sys.argv[0], BASE_URL + epurl, unicode_urlencode(title), img, imdbnum, season, epnum)
		xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=listitem, 
									isFolder=True)
	setView('episodes', 'episodes-view')
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseFavorites(section): #8000
	db = sqlite.connect( DB )
	cursor = db.cursor()
	if section == 'tv':  setView('tvshows', 'tvshows-view')
	else: setView('movies', 'movies-view')
	if section == 'tv':
		nextmode = '?mode=4000'
		type = 'tvshow'
	else: 
		nextmode = '?mode=10'
		section  = 'movie'
		type 	 = 'movie'
	favs = cursor.execute('SELECT type, name, url, year FROM favorites WHERE type = ? ORDER BY name', (section,))
	for row in favs:
		title	  = row[1]
		favurl	  = row[2]
		year	  = row[3]
		cm		  = []
		meta	  = {}
		if year: disptitle = title +'('+year+')'
		else:	 disptitle = title
		update = False
		img = ''

		if META_ON:
			try:
				if type == 'tvshow':
					try: meta = metaget.get_meta(type,title,year=year)
					except: print 'Failed to get metadata for %s %s %s' %(type,title,year)
					if meta['tvdb_id'] =='' and meta['imdb_id'] =='':
						update = True
				elif type == 'movie':
					try: meta = metaget.get_meta(type,title,year=year)
					except: print 'Failed to get metadata for %s %s %s' %(type,title,year)
					if meta['imdb_id'] =='':
						update = True

					if meta['trailer_url']:
						url = meta['trailer_url']
						url = re.sub('&feature=related','',url)
						url = url.encode('base-64').strip()
						runstring = 'RunScript(plugin.video.1channel,%s,?mode=250&url=%s)' %(sys.argv[1],url)
						cm.append(('Watch Trailer', runstring))

				if type == 'tvshow'and not USE_POSTERS:
					meta['cover_url'] = meta['banner_url']

				img = meta['cover_url']
			except: update = True

		liurl = sys.argv[0] + nextmode
		liurl += '&title='  + title
		liurl += '&url='	+ favurl
		liurl += '&imdbnum=' + meta['imdb_id']
		liurl += '&videoType=' + type
		if update: liurl += '&update=1'
		listitem = xbmcgui.ListItem(disptitle, iconImage=img, thumbnailImage=img)
		try: listitem.setInfo(type="Video", infoLabels=meta)
		except: pass
		if FANART_ON:
			try: listitem.setProperty('fanart_image', meta['backdrop_url'])
			except: pass
		remfavstring = 'RunScript(plugin.video.1channel,%s,?mode=7777&section=%s&title=%s&year=%s&url=%s)' %(sys.argv[1],section,title,year,favurl)
		cm.append(('Remove from Favorites', remfavstring))
		listitem.addContextMenuItems(cm)
		xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=liurl, listitem=listitem, 
						isFolder=True, totalItems=0)
	xbmcplugin.endOfDirectory(int(sys.argv[1]))
	db.close()

def scan_by_letter(section, letter):
	print 'Building meta for %s letter %s' % (section,letter)
	pDialog = xbmcgui.DialogProgress()
	ret = pDialog.create('Scanning Metadata')
	url = BASE_URL + '/?'
	if section == 'tvshow': url += 'tv'
	url += '&letter=' + letter
	url += '&sort=alphabet'
	html = '> >> <'
	total = 1
	page = 1
	items = 0
	percent = 0
	r = 'class="index_item.+?href=".+?" title="Watch (.+?)(?:\(|">)([0-9]{4})?'
	while html.find('> >> <') > -1:
		failed_attempts = 0
		if page == 1:
			while failed_attempts < 4:
				try: 
					html = GetURL(url)
					failed_attempts = 4
				except: 
					failed_attempts += 1
					if failed_attempts == 4:
						html = '> >> <'
						failed_attempts = 0
			url += '&page=%s'
		else:
			while failed_attempts < 4:
				try: 
					html = GetURL(url % page)
					failed_attempts = 4
				except: 
					failed_attempts += 1
					if failed_attempts == 4:
						html = '> >> <'
		regex = re.finditer(r, html, re.DOTALL)
		for s in regex:
			title,year = s.groups()
			failed_attempts = 0
			while failed_attempts < 4:
				try: 
					meta = metaget.get_meta(section,title,year=year)
					failed_attempts = 4
				except: 
					failed_attempts += 1
					if failed_attempts == 4:
						print 'Failed retrieving metadata for %s %s %s' %(section, title, year)
			pattern = re.search('number_movies_result">([0-9,]+)', html)
			if pattern: total = int(pattern.group(1).replace(',', ''))
			items += 1
			percent = 100*items
			percent = percent/total
			pDialog.update(percent,'Scanning metadata for %s' % letter, title)
			if (pDialog.iscanceled()): break
		if (pDialog.iscanceled()): break
		page += 1
	if (pDialog.iscanceled()): return

def zipdir(basedir, archivename):
	from contextlib import closing
	from zipfile import ZipFile, ZIP_DEFLATED
	assert os.path.isdir(basedir)
	with closing(ZipFile(archivename, "w", ZIP_DEFLATED)) as z:
		for root, dirs, files in os.walk(basedir):
			#NOTE: ignore empty directories
			for fn in files:
				absfn = os.path.join(root, fn)
				zfn = absfn[len(basedir)+len(os.sep):] #XXX: relative path
				z.write(absfn, zfn)

def extract_zip(src, dest):
		try:
			print 'Extracting '+str(src)+' to '+str(dest)
			#make sure there are no double slashes in paths
			src=os.path.normpath(src)
			dest=os.path.normpath(dest) 

			#Unzip - Only if file size is > 1KB
			if os.path.getsize(src) > 10000:
				xbmc.executebuiltin("XBMC.Extract("+src+","+dest+")")
			else:
				print '************* Error: File size is too small'
				return False

		except:
			print 'Extraction failed!'
			return False
		else:                
			print 'Extraction success!'
			return True

def create_meta_packs():
	import shutil
	global metaget
	container = metacontainers.MetaContainer()
	savpath = container.path
	AZ_DIRECTORIES.append('123')
	letters_completed = 0
	letters_per_zip = 27
	start_letter = ''
	end_letter = ''

	for type in ('tvshow','movie'):
		for letter in AZ_DIRECTORIES:
			if letters_completed == 0:
				start_letter = letter
				metaget.__del__()
				shutil.rmtree(container.cache_path)
				metaget=metahandlers.MetaData(preparezip=prepare_zip)

			if letters_completed <= letters_per_zip:
				scan_by_letter(type, letter)
				letters_completed += 1

			if (letters_completed == letters_per_zip
				or letter == '123' or get_dir_size(container.cache_path) > (500*1024*1024)):
				end_letter = letter
				arcname = 'MetaPack-%s-%s-%s.zip' % (type, start_letter, end_letter)
				arcname = os.path.join(savpath, arcname)
				metaget.__del__()
				zipdir(container.cache_path, arcname)
				metaget=metahandlers.MetaData(preparezip=prepare_zip)
				letters_completed = 0
				xbmc.sleep(5000)

def copy_meta_contents(root_src_dir, root_dst_dir):
	import shutil
	for root, dirs, files in os.walk(root_src_dir):

		#figure out where we're going
		dest = root_dst_dir + root.replace(root_src_dir, '')

		#if we're in a directory that doesn't exist in the destination folder
		#then create a new folder
		if not os.path.isdir(dest):
			os.mkdir(dest)
			print 'Directory created at: ' + dest

		#loop through all files in the directory
		for f in files:
			if not f.endswith('.db') and not f.endswith('.zip'):
				#compute current (old) & new file locations
				oldLoc = os.path.join(root, f)

				newLoc = os.path.join(dest, f)
				if not os.path.isfile(newLoc):
					try:
						shutil.copy2(oldLoc, newLoc)
						print 'File ' + f + ' copied.'
					except IOError:
						print 'file "' + f + '" already exists'
			else: print 'Skipping file ' + f
	# for src_dir, dirs, files in os.walk(root_src_dir):
		# dst_dir = src_dir.replace(root_src_dir, root_dst_dir)
		# if not os.path.exists(dst_dir):
			# os.mkdir(dst_dir)
		# for file_ in files:
			# if not file_.endswith('.db') and not file_.endswith('.zip'):
				# src_file = os.path.join(src_dir, file_)
				# dst_file = os.path.join(dst_dir, file_)
				# if os.path.exists(dst_file):
					# os.remove(dst_file)
				# shutil.move(src_file, dst_dir)

def install_metapack(pack):
	packs = metapacks.list()
	pack_details = packs[pack]
	mc = metacontainers.MetaContainer()
	work_path  = mc.work_path
	cache_path = mc.cache_path
	zip = os.path.join(work_path, pack)

	net = Net()
	cookiejar = ADDON.get_profile()
	cookiejar = os.path.join(cookiejar,'cookies')

	html = net.http_GET(pack_details[0]).content
	net.save_cookies(cookiejar)
	name = re.sub('-', r'\\\\u002D', pack)

	r = '"name": "%s".*?"id": "([^\s]*?)".*?"secure_prefix":"(.*?)",' % name
	r = re.search(r,html)
	pack_url  = 'http://i.minus.com'
	pack_url += r.group(2)
	pack_url += '/d' + r.group(1) + '.zip'

	complete = download_metapack(pack_url, zip, displayname=pack)
	extract_zip(zip, work_path)
	xbmc.sleep(5000)
	copy_meta_contents(work_path, cache_path)
	for table in mc.table_list:
		install = mc._insert_metadata(table)

def install_all_meta():
	all_packs = metapacks.list()
	skip = []
	skip.append('MetaPack-tvshow-A-G.zip')
	skip.append('MetaPack-tvshow-H-N.zip')
	skip.append('MetaPack-tvshow-O-U.zip')
	skip.append('MetaPack-tvshow-V-123.zip')
	for pack in all_packs:
		if pack not in skip:
			install_metapack(pack)

class StopDownloading(Exception): 
        def __init__(self, value): 
            self.value = value 
        def __str__(self): 
            return repr(self.value)

def download_metapack(url, dest, displayname=False):
	print 'Downloading Metapack'
	print 'URL: %s' % url
	print 'Destination: %s' % dest
	if displayname == False:
		displayname=url
	dp = xbmcgui.DialogProgress()
	dp.create('Downloading', '', displayname)
	start_time = time.time()
	if os.path.isfile(dest): 
		print 'File to be downloaded already esists'
		return True
	try: 
		urllib.urlretrieve(url, dest, lambda nb, bs, fs: _pbhook(nb, bs, fs, dp, start_time)) 
	except:
		#only handle StopDownloading (from cancel), ContentTooShort (from urlretrieve), and OS (from the race condition); let other exceptions bubble 
		if sys.exc_info()[0] in (urllib.ContentTooShortError, StopDownloading, OSError): 
			return False 
		else: 
			raise 
		return False
	return True

def is_metapack_installed(pack):
	pass

def format_eta(seconds):
	print 'Format ETA starting with %s seconds' % seconds
	minutes,seconds = divmod(seconds, 60)
	print 'Minutes/Seconds: %s %s' %(minutes,seconds)
	if minutes > 60:
		hours,minutes = divmod(minutes, 60)
		print 'Hours/Minutes: %s %s' %(hours,minutes)
		return "ETA: %02d:%02d:%02d " % (hours, minutes, seconds)
	else:
		return "ETA: %02d:%02d " % (minutes, seconds)
	print 'Format ETA: hours: %s minutes: %s seconds: %s' %(hours,minutes,seconds)

def repair_missing_images():
	mc = metacontainers.MetaContainer()
	dbcon = sqlite.connect(mc.videocache)
	dbcur = dbcon.cursor()
	dp = xbmcgui.DialogProgress()
	dp.create('Repairing Images', '', '', '')
	for type in ('tvshow','movie'):
		total  = 'SELECT count(*) from %s_meta WHERE ' % type
		total += 'imgs_prepacked = "true"'
		total = dbcur.execute(total).fetchone()[0]
		statement =  'SELECT title,cover_url,backdrop_url'
		if type   == 'tvshow': statement += ',banner_url'
		statement += ' FROM %s_meta WHERE imgs_prepacked = "true"' % type
		complete = 1.0
		start_time = time.time()
		already_existing = 0

		for row in dbcur.execute(statement):
			title	 = row[0]
			cover 	 = row[1]
			backdrop = row[2]
			if type == 'tvshow': banner = row[3]
			else: banner = False
			percent = int((complete*100)/total)
			entries_per_sec = (complete - already_existing)
			entries_per_sec /=  max(float((time.time() - start_time)),1)
			total_est_time = total / max(entries_per_sec,1)
			eta = total_est_time - (time.time() - start_time)

			eta = format_eta(eta) 
			dp.update(percent, eta + title, '')
			if cover:
				dp.update(percent, eta + title, cover)
				img_name = metaget._picname(cover)
				img_path = os.path.join(metaget.mvcovers, img_name[0].lower())
				file = os.path.join(img_path,img_name)
				if not os.path.isfile(file):
					retries = 4
					while retries:
						try: 
							metaget._downloadimages(cover, img_path, img_name)
							break
						except: retries -= 1
				else: already_existing -= 1
			if backdrop:
				dp.update(percent, eta + title, backdrop)
				img_name = metaget._picname(backdrop)
				img_path = os.path.join(metaget.mvbackdrops, img_name[0].lower())
				file = os.path.join(img_path,img_name)
				if not os.path.isfile(file):
					retries = 4
					while retries:
						try: 
							metaget._downloadimages(backdrop, img_path, img_name)
							break
						except: retries -= 1
				else: already_existing -= 1
			if banner:
				dp.update(percent, eta + title, banner)
				img_name = metaget._picname(banner)
				img_path = os.path.join(metaget.tvbanners, img_name[0].lower())
				file = os.path.join(img_path,img_name)
				if not os.path.isfile(file):
					retries = 4
					while retries:
						try: 
							metaget._downloadimages(banner, img_path, img_name)
							break
						except: retries -= 1
				else: already_existing -= 1
			if dp.iscanceled(): return False
			complete += 1

def _pbhook(numblocks, blocksize, filesize, dp, start_time):
        try: 
            percent = min(numblocks * blocksize * 100 / filesize, 100) 
            currently_downloaded = float(numblocks) * blocksize / (1024 * 1024) 
            kbps_speed = numblocks * blocksize / (time.time() - start_time) 
            if kbps_speed > 0: 
                eta = (filesize - numblocks * blocksize) / kbps_speed 
            else: 
                eta = 0 
            kbps_speed = kbps_speed / 1024 
            total = float(filesize) / (1024 * 1024) 
            # print ( 
                # percent, 
                # numblocks, 
                # blocksize, 
                # filesize, 
                # currently_downloaded, 
                # kbps_speed, 
                # eta, 
                # ) 
            mbs = '%.02f MB of %.02f MB' % (currently_downloaded, total) 
            e = 'Speed: %.02f Kb/s ' % kbps_speed 
            e += 'ETA: %02d:%02d' % divmod(eta, 60) 
            dp.update(percent, mbs, e)
            #print percent, mbs, e 
        except: 
            percent = 100 
            dp.update(percent) 
        if dp.iscanceled(): 
            dp.close() 
            raise StopDownloading('Stopped Downloading')

def get_dir_size(start_path):
	print 'Calculating size of %s' % start_path
	total_size = 0
	for dirpath, dirnames, filenames in os.walk(start_path):
		for f in filenames:
			fp = os.path.join(dirpath, f)
			total_size += os.path.getsize(fp)
	print 'Calculated: %s' % total_size
	return total_size

def setView(content, viewType):
	# set content type so library shows more views and info
	if content:
		xbmcplugin.setContent(int(sys.argv[1]), content)
	if ADDON.get_setting('auto-view') == 'true':
		xbmc.executebuiltin("Container.SetViewMode(%s)" % ADDON.get_setting(viewType) )

	# set sort methods - probably we don't need all of them
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_UNSORTED )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_LABEL )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RATING )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_DATE )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_PROGRAM_COUNT )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RUNTIME )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_GENRE )

def GetParams():
	param=[]
	paramstring=sys.argv[len(sys.argv)-1]
	if len(paramstring)>=2:
		cleanedparams=paramstring.replace('?','')
		if (paramstring[len(paramstring)-1]=='/'):
				paramstring=paramstring[0:len(paramstring)-2]
		pairsofparams=cleanedparams.split('&')
		param={}
		for i in range(len(pairsofparams)):
			splitparams={}
			splitparams=pairsofparams[i].split('=')
			if (len(splitparams))==2:
				param[splitparams[0]]=splitparams[1]			
	return param

print 'BEFORE GETPARAMS: %s' % sys.argv
params=GetParams()

try:	mode = 	  int(params['mode'])
except: mode =	  None
try:	section = params['section']
except: section = None
try: 	genre =   params['genre']
except: genre =   None
try:	letter =  params['letter']
except: letter =  None
try: 	sort =    params['sort']
except: sort =    None
try: 	url = 	  params['url']
except: url = 	  None
try: 	title =   params['title']
except: title =   None
try: 	img = 	  params['img']
except: img = 	  None
try: 	season =  params['season']
except: season =  None
try: 	query =   params['query']
except: query =   None
try: 	page =    params['page']
except: page =    None
try: 	imdbnum = params['imdbnum']
except: imdbnum = None
try: 	year =    params['year']
except: year = 	  None
try: 	update =  params['update']
except: update =  None

print '==========================PARAMS:\nMODE: %s\nMYHANDLE: %s\nPARAMS: %s' % (mode, sys.argv[1], params )

initDatabase()

if mode==None: #Main menu
	AddonMenu()
elif mode==10: #Play Stream
	GetSources(url,title,img,update, imdbnum=imdbnum, video_type=video_type, season=season, episode=episode)
elif mode==250: #Play Trailer
	PlayTrailer(url)
elif mode==500: #Browsing options menu
	BrowseListMenu(section)
elif mode==1000: #Browse by A-Z menu
	BrowseAlphabetMenu(section)
elif mode==2000: #Browse by genre
	BrowseByGenreMenu(section)
elif mode==3000: #Show the results of the menus selected
	GetFilteredResults(section, genre, letter, sort, page)
elif mode==4000: #TV Show season list
	TVShowSeasonList(url, title, year, update)
elif mode==5000: #TVShow episode list
	TVShowEpisodeList(season, imdbnum)
elif mode==6000: #Get search terms
	GetSearchQuery(section)
elif mode==7000: #Get search results
	Search(section, query)
elif mode==8000: #Browse Favorites
	BrowseFavorites(section)
elif mode==8888: #Save to favorites
	SaveFav(section, title, url, img, year)
elif mode==7777: #Delete favorite
	DeleteFav(section, title, url)
	xbmc.executebuiltin('Container.Refresh')
elif mode==9988: #Metahandler Settings
	print "Metahandler Settings"
	import metahandler
	metahandler.display_settings()
elif mode==9999: #Open URL Resolver Settings
	urlresolver.display_settings()
elif mode==10000: #Install meta pack
	install_metapack(title)
