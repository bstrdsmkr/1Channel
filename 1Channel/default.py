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
import xbmcgui
import xbmcplugin
import xbmc, xbmcvfs 
from t0mm0.common.addon import Addon
from metahandler import metahandlers


ADDON = Addon('plugin.video.1channel', sys.argv)

try:
	from sqlite3 import dbapi2 as sqlite
	print "Loading sqlite3 as DB engine"
except:
	from pysqlite2 import dbapi2 as sqlite
	print "Loading pysqlite2 as DB engine"

DB = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')
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

def AddOption(text, isFolder, mode, letter=None, section=None, sort=None, genre=None, query=None, page=None):
	li = xbmcgui.ListItem(text)
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
		return urllib.quote_plus(value.encode("utf-8")) 
	else: 
		return urllib.quote_plus(value) 

def initDatabase():
	print "Building 1channel Database"
	if ( not os.path.isdir( os.path.dirname( DB ) ) ):
		os.makedirs( os.path.dirname( DB ) )
	db = sqlite.connect( DB )
	cursor = db.cursor()
	cursor.execute('CREATE TABLE IF NOT EXISTS seasons (season UNIQUE, contents);')
	cursor.execute('CREATE TABLE IF NOT EXISTS favorites (type, name, url, year);')
	db.commit()
	db.close()

def SaveFav(type, name, url, img, year): #8888
	if type != 'tv': type = 'movie'
	db = sqlite.connect( DB )
	cursor = db.cursor()
	cursor.execute('INSERT INTO favorites (type, name, url, year) Values (?,?,?,?)', 
				  (type, urllib.unquote_plus(name), url, year))
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

def GetSources(url, title='', img=''): #10
	url	  = urllib.unquote_plus(url)
	title = urllib.unquote_plus(title)
	print 'Playing: %s' % url
	html = GetURL(url)

	#find all sources and their info
	sources = []
	for s in re.finditer('class="movie_version.+?quality_(?!sponsored)(.+?)>.+?url=(.+?)' + 
						 '&domain=(.+?)&.+?"version_veiws">(.+?)</', 
						 html, re.DOTALL):
		q, url, host, views = s.groups()
		verified = s.group(0).find('star.gif') > -1
		label = '[%s]  ' % q.upper()
		label += host.decode('base-64')
		if verified: label += ' [verified]'
		label += ' (%s)' % views.strip()
		url = url.decode('base-64')
		host = host.decode('base-64')
		print 'Source found:\n quality %s\n url %s\n host %s\n views %s\n' % (q, url, host, views)
		try:
			hosted_media = urlresolver.HostedMediaFile(url=url, title=label)
			sources.append(hosted_media)
		except:
			print 'Error while trying to determine'

	source = urlresolver.choose_source(sources)
	if source: stream_url = source.resolve()
	else: stream_url = ''
	listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
	xbmc.Player().play(stream_url, listitem)

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
	if section == 'tv': heading = 'Search TV Shows'
	else: heading = 'Search Movies'
	keyboard = xbmc.Keyboard(heading=heading)
	keyboard.doModal()
	if (keyboard.isConfirmed()):
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
		xbmcplugin.setContent( int( sys.argv[1] ), 'tvshows' )
		pageurl += '&search_section=2'
		nextmode = '?mode=4000'
		type = 'tvshow'
	else:
		xbmcplugin.setContent( int( sys.argv[1] ), 'movies' )
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
			if resurl not in resurls:
				resurls.append(resurl)
				cm = []
				if year: disptitle = title +'('+year+')'
				else: disptitle = title

				if type == 'tvshow':
					meta = metaget.get_meta(type,disptitle)
					if meta['tvdb_id'] =='' and meta['imdb_id'] =='':
						meta = metaget.get_meta(type,title)
				elif type == 'movie':
					meta = metaget.get_meta(type,disptitle,year)
					if meta['imdb_id'] =='':
						meta = metaget.get_meta(type,title)
					if meta['trailer_url']:
						url = meta['trailer_url']
						url = re.sub('&feature=related','',url)
						url = url.encode('base-64').strip()
						runstring = 'RunScript(plugin.video.1channel,%s,?mode=250&url=%s)' %(sys.argv[1],url)
						cm.append(('Watch Trailer', runstring))
				if meta['cover_url'] in ('/images/noposter.jpg',''):
					meta['cover_url'] = thumb

				listitem = xbmcgui.ListItem(disptitle, iconImage=meta['cover_url'], thumbnailImage=meta['cover_url'])
				listitem.setInfo(type="Video", infoLabels=meta)
				title = unicode_urlencode(title)
				runstring = 'RunScript(plugin.video.1channel,%s,?mode=8888&section=%s&title=%s&url=%s&year=%s)' %(sys.argv[1],section,title,resurl,year)
				cm.append(('Show Information', 'XBMC.Action(Info)'))
				cm.append(('Add to Favorites', runstring))
				listitem.addContextMenuItems(cm, replaceItems=True)
				listitem.setProperty('fanart_image', meta['backdrop_url'])
				resurl = BASE_URL + resurl
				liurl = sys.argv[0] + nextmode
				liurl += '&title=' + title
				liurl += '&img='	 + thumb
				liurl += '&url=' + resurl
				xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=liurl, listitem=listitem, 
							isFolder=True, totalItems=total)

	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def AddonMenu():  #homescreen
	print '1Channel menu'
	AddOption('Movies',  True, 500, section=None)
	AddOption('TV shows',True, 500, section='tv')
	AddOption('Settings',True, 9999)
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseListMenu(section=None): #500
	AddOption('A-Z',		  True, 1000, section=section)
	AddOption('Search',		  True, 6000, section=section, query=query)
	AddOption('Favorites',	  True, 8000, section=section)
	AddOption('Genres',		  True, 2000, section=section)
	AddOption('Featured', 	  True, 3000, section=section, sort='featured')
	AddOption('Most Popular', True, 3000, section=section, sort='views')	
	AddOption('Highly rated', True, 3000, section=section, sort='ratings')
	AddOption('Date released',True, 3000, section=section, sort='release')	
	AddOption('Date added',	  True, 3000, section=section, sort='date')
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
		if resurl not in resurls:
			resurls.append(resurl)
			cm = []
			if year: disptitle = title +'('+year+')'
			else: disptitle = title

			if type == 'tvshow':
				meta = metaget.get_meta(type,disptitle)
				if meta['tvdb_id'] =='' and meta['imdb_id'] =='':
					meta = metaget.get_meta(type,title)
			elif type == 'movie':
				meta = metaget.get_meta(type,title,year)
				if meta['imdb_id'] =='':
					meta = metaget.get_meta(type,disptitle)
				if meta['trailer_url']:
					url = meta['trailer_url']
					url = re.sub('&feature=related','',url)
					url = url.encode('base-64').strip()
					runstring = 'RunScript(plugin.video.1channel,%s,?mode=250&url=%s)' %(sys.argv[1],url)
					cm.append(('Watch Trailer', runstring))
			if meta['cover_url'] in ('/images/noposter.jpg',''):
				meta['cover_url'] = thumb

			listitem = xbmcgui.ListItem(disptitle, iconImage=meta['cover_url'], thumbnailImage=meta['cover_url'])
			listitem.setInfo(type="Video", infoLabels=meta)
			title = unicode_urlencode(title)
			resurl = BASE_URL + resurl
			liurl = sys.argv[0] + nextmode
			liurl += '&title=' + title
			liurl += '&url=' + resurl
			runstring = 'RunScript(plugin.video.1channel,%s,?mode=8888&section=%s&title=%s&url=%s&year=%s)' %(sys.argv[1],section,title,resurl,year)
			cm.append(('Add to Favorites', runstring))
			cm.append(('Show Information', 'XBMC.Action(Info)'))
			listitem.addContextMenuItems(cm, replaceItems=True)
			listitem.setProperty('fanart_image', meta['backdrop_url'])
			xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=liurl, listitem=listitem, 
						isFolder=True, totalItems=total)
	if page is not None: page = int(page) + 1
	else: page = 2
	if html.find('> >> <') > -1:
		AddOption('Next Page >>', True, 3000, section=section, genre=genre, letter=letter, sort=sort, page=page)
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def TVShowSeasonList(url, title, year): #4000
	print 'Seasons for TV Show %s' % url
	html = GetURL(url)
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
		metaget=metahandlers.MetaData(preparezip=prepare_zip)
		if imdbnum: 
			metaget.update_meta('tvshow', title, imdbnum, year=year)
			season_meta = metaget.get_seasons(title, imdbnum, season_nums)
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
				try: listitem.setProperty('fanart_image', temp['backdrop_url'])
				except: pass
				season_name = unicode_urlencode(season_name).lower()
				cursor.execute('INSERT or REPLACE into seasons (season,contents) VALUES(?,?);',
								(season_name, eplist))
				url = sys.argv[0]+ '?mode=5000'+'&season=' +season_name+ '&imdbnum='+imdbnum
				xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=listitem, 
											isFolder=True)
				cnxn.commit()
				num += 1
		xbmcplugin.endOfDirectory(int(sys.argv[1]))
		cnxn.close()

def TVShowEpisodeList(season, imdbnum): #5000
	xbmcplugin.setContent( int( sys.argv[1] ), 'episodes' )
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
		title = re.sub('<[^<]+?>', '', title.strip())
		title = re.sub('\s\s+' , ' ', title)
		title = urllib.unquote_plus(title)
		name = re.search('/(tv|watch)-[0-9]+-(.+?)/season-', epurl).group(2)
		name = re.sub('-',' ',name)
		season = re.search('/season-([0-9]{1,3})-', epurl).group(1)
		epnum = re.search('-episode-([0-9]{1,3})', epurl).group(1)
		meta = metaget.get_episode_meta(name=name,imdb_id=imdbnum,season=season, episode=epnum)
		img = meta['cover_url']
		listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
		listitem.setInfo(type="Video", infoLabels=meta)
		try: listitem.setProperty('fanart_image', meta['backdrop_url'])
		except: pass
		listitem.addContextMenuItems(cm)
		url = '%s?mode=10&url=%s&title=%s&img=%s' % \
				(sys.argv[0], BASE_URL + epurl, unicode_urlencode(title), img)
		xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=listitem, 
									isFolder=True)
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseFavorites(section): #8000
	db = sqlite.connect( DB )
	cursor = db.cursor()
	if section == 'tv':	xbmcplugin.setContent( int( sys.argv[1] ), 'tvshows' )
	else: xbmcplugin.setContent( int( sys.argv[1] ), 'movies' )
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
		liurl = sys.argv[0] + nextmode
		liurl += '&title='  + title
		liurl += '&url='	+ favurl
		disptitle = title +'('+year+')'

		if type == 'tvshow':
			meta = metaget.get_meta(type,title)
#			if meta['tvdb_id'] =='' and meta['imdb_id'] =='':
#				meta = metaget.get_meta(type,disptitle)
		elif type == 'movie':
			meta = metaget.get_meta(type,title,year)
			if meta['imdb_id'] =='':
				meta = metaget.get_meta(type,title)
			if meta['trailer_url']:
				url = meta['trailer_url']
				url = re.sub('&feature=related','',url)
				url = url.encode('base-64').strip()
				runstring = 'RunScript(plugin.video.1channel,%s,?mode=250&url=%s)' %(sys.argv[1],url)
				cm.append(('Watch Trailer', runstring))

		listitem = xbmcgui.ListItem(disptitle, iconImage=meta['cover_url'], thumbnailImage=meta['cover_url'])
		listitem.setInfo(type="Video", infoLabels=meta)
		listitem.setProperty('fanart_image', meta['backdrop_url'])
		remfavstring = 'RunScript(plugin.video.1channel,%s,?mode=7777&section=%s&title=%s&year=%s&url=%s)' %(sys.argv[1],section,title,year,favurl)
		cm.append(('Remove from Favorites', remfavstring))
		listitem.addContextMenuItems(cm)
		xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=liurl, listitem=listitem, 
						isFolder=True, totalItems=0)
	xbmcplugin.endOfDirectory(int(sys.argv[1]))
	db.close()

def create_meta_pack(section, letter):
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
		if page == 1:
			html = GetURL(url)
			url += '&page=%s'
		else:
			html = GetURL(url % page)
		regex = re.finditer(r, html, re.DOTALL)
		for s in regex:
			title,year = s.groups()
			if type == 'tvshow':
				meta = metaget.get_meta(type,title)
			elif type == 'movie':
				meta = metaget.get_meta(type,title,year)
			pattern = re.search('number_movies_result">([0-9,]+)', html)
			if pattern: total = int(pattern.group(1).replace(',', ''))
			items += 1
			percent = float(100*items)
			percent = percent/total
			pDialog.update(percent,'Scanning metadata for %s' % letter, title)
			if (pDialog.iscanceled()): break
		if (pDialog.iscanceled()): break
		page += 1
	if (pDialog.iscanceled()): return


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


print '==========================PARAMS:\nMODE: %s\nMYHANDLE: %s\nPARAMS: %s' % (mode, sys.argv[1], params )

initDatabase()

#for letter in AZ_DIRECTORIES:
#	create_meta_pack('tvshow', letter)

if mode==None: #Main menu
	AddonMenu()
elif mode==10: #Play Stream
	GetSources(url,title,img)
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
	TVShowSeasonList(url, title, year)
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
elif mode==9999: #Open URL Resolver Settings
	urlresolver.display_settings()