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
import HTMLParser
import time

from t0mm0.common.addon import Addon
from t0mm0.common.net import Net
from metahandler import metahandlers
from metahandler import metacontainers
from operator import itemgetter, methodcaller

import metapacks
import playback
import captcha

try:
	from sqlite3 import dbapi2 as sqlite
	print "Loading sqlite3 as DB engine"
except:
	from pysqlite2 import dbapi2 as sqlite
	print "Loading pysqlite2 as DB engine"

addon = Addon('plugin.video.1channel', sys.argv)
DB = os.path.join(xbmc.translatePath("special://database"), 'onechannelcache.db')

META_ON = addon.get_setting('use-meta') == 'true'
FANART_ON = addon.get_setting('enable-fanart') == 'true'
USE_POSTERS = addon.get_setting('use-posters') == 'true'
POSTERS_FALLBACK = addon.get_setting('posters-fallback') == 'true'
THEME_LIST = ['mikey1234','Glossy_Black']
THEME = THEME_LIST[int(addon.get_setting('theme'))]
THEME_PATH = os.path.join(addon.get_path(), 'art', 'themes', THEME)
AUTO_WATCH = addon.get_setting('auto-watch') == 'true'

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

if not os.path.isdir(addon.get_profile()):
     os.makedirs(addon.get_profile())

def art(file):
	img = os.path.join(THEME_PATH, file)
	return img

def initDatabase():
	addon.log('Building 1channel Database')
	if not os.path.isdir(os.path.dirname(DB)):
		os.makedirs(os.path.dirname(DB))
	db = sqlite.connect(DB)
	db.execute('CREATE TABLE IF NOT EXISTS seasons (season UNIQUE, contents)')
	db.execute('CREATE TABLE IF NOT EXISTS favorites (type, name, url, year)')
	db.execute('CREATE TABLE IF NOT EXISTS subscriptions (url, title, img, year, imdbnum)')
	db.execute('CREATE TABLE IF NOT EXISTS bookmarks (video_type, title, season, episode, year, bookmark)')
	db.execute('CREATE TABLE IF NOT EXISTS url_cache (url UNIQUE, response, timestamp)')
	db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_fav ON favorites (name, url)')
	db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_sub ON subscriptions (url, title, year)')
	db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_bmk ON bookmarks (video_type, title, season, episode, year)')
	db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_url ON url_cache (url)')
	db.commit()
	db.close()

def SaveFav(type, name, url, img, year): #8888
	addon.log('Saving Favorite type: %s name: %s url: %s img: %s year: %s' %(type, name, url, img, year))
	if type != 'tv': type = 'movie'
	db = sqlite.connect( DB )
	cursor = db.cursor()
	statement  = 'INSERT INTO favorites (type, name, url, year) VALUES (?,?,?,?)'
	try: 
		cursor.execute(statement, (type, urllib.unquote_plus(unicode(name,'latin1')), url, year))
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

def GetURL(url, params = None, referrer = BASE_URL, cookie = None, save_cookie = False, silent = False, use_cache=True):
	addon.log('Fetching URL: %s' % url)
	db = sqlite.connect( DB )
	now = time.time()
	if use_cache:
		limit = 60*60*8 #8 hours
		cached = db.execute('SELECT * FROM url_cache WHERE url = ?', (url,)).fetchone()
		if cached:
			created = int(cached[2])
			age = now - created
			if age < limit:
				addon.log('Returning cached result for %s' %url)
				db.close()
				return cached[1].encode('latin-1')
			else: addon.log('Cache too old. Requesting from internet')
		else: addon.log('No cached response. Requesting from internet')

	if params: req = urllib2.Request(url, params)
	else: req = urllib2.Request(url)

	req.add_header('User-Agent', USER_AGENT)
	req.add_header('Host', 'www.1channel.ch')
	if referrer: req.add_header('Referer', referrer)
	if cookie: req.add_header('Cookie', cookie)
	
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
		if setcookie:
			setcookie = re.search('([^=]+=[^=;]+)', setcookie).group(1)
			body = body + '<cookie>' + setcookie + '</cookie>'

	response.close()
	db.execute('INSERT OR REPLACE INTO url_cache (url,response,timestamp) VALUES(?,?,?)',
				(url, body.decode('latin-1'), now))
	db.commit()
	db.close()
	return body

def GetSources(url, title, img, year, imdbnum, dialog): #10
	url	  = urllib.unquote(url)
	addon.log('Playing: %s' % url)

	match = re.search('tv-\d{1,10}-(.*)/season-(\d{1,4})-episode-(\d{1,4})', url, re.IGNORECASE | re.DOTALL)
	if match:
		video_type = 'episode'
		season  = int(match.group(2))
		episode = int(match.group(3))
	else:
		video_type = 'movie'
		season  = ''
		episode = ''

	net = Net()
	cookiejar = addon.get_profile()
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
		html = net.http_GET(adulturl, headers=headers).content

	sources = []
	list = []
	if META_ON and video_type=='movie' and not imdbnum:
		imdbregex = 'mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"'
		r = re.search(imdbregex, html)
		if r:
			imdbnum = r.group(1)
			metaget.update_meta('movie',title,imdb_id='',
								new_imdb_id=imdbnum,year=year)

	if addon.get_setting('sorting-enabled')=='true':
		sorts = [None,'host','verified','quality','views','multi-part']
		if int(addon.get_setting('first-sort')) > 0:
			this_sort = sorts[int(addon.get_setting('first-sort'))]
			if addon.get_setting('first-sort-reversed')=='true':
				this_sort = '-%s' %this_sort
			sorting = [this_sort]
			if int(addon.get_setting('second-sort')) > 0:
				this_sort = sorts[int(addon.get_setting('second-sort'))]
				if addon.get_setting('second-sort-reversed')=='true':
					this_sort = '-%s' %this_sort
				sorting.append(this_sort)
				if int(addon.get_setting('third-sort')) > 0:
					this_sort = sorts[int(addon.get_setting('third-sort'))]
					if addon.get_setting('third-sort-reversed')=='true':
						this_sort = '-%s' %this_sort
					sorting.append(this_sort)
					if int(addon.get_setting('fourth-sort')) > 0:
						this_sort = sorts[int(addon.get_setting('fourth-sort'))]
						if addon.get_setting('fourth-sort-fourth')=='true':
							this_sort = '-%s' %this_sort
						sorting.append(this_sort)
						if int(addon.get_setting('fifth-sort')) > 0:
							this_sort = sorts[int(addon.get_setting('fifth-sort'))]
							if addon.get_setting('fifth-sort-reversed')=='true':
								this_sort = '-%s' %this_sort
							sorting.append(this_sort)
	else: sorting = []

	for version in re.finditer('<table[^\n]+?class="movie_version(?: movie_version_alt)?">(.*?)</table>',
								html, re.DOTALL|re.IGNORECASE):
		for s in re.finditer('quality_(?!sponsored|unknown)(.*?)></span>.*?'+
 							 'url=(.*?)&(?:amp;)?domain=(.*?)&(?:amp;)?(.*?)'+
							 '"version_veiws"> ([\d]+) views</',
							 version.group(1), re.DOTALL):
			q, url, host, parts, views = s.groups()
			
			item = {}
			item['host'] = host.decode('base-64')
			item['url'] = url.decode('base-64')
			if urlresolver.HostedMediaFile(item['url']).valid_url():
				item['verified'] = s.group(0).find('star.gif') > -1
				item['quality'] = q.upper()
				item['views'] = int(views)
				r = '\[<a href=".*?url=(.*?)&(?:amp;)?.*?".*?>(part [0-9]*)</a>\]'
				additional_parts = re.findall(r, parts, re.DOTALL|re.IGNORECASE)
				if additional_parts:
					item['multi-part'] = True
					item['parts'] = [part[0].decode('base-64') for part in additional_parts]
				else: item['multi-part'] = False
				list.append(item)

			if sorting: list = multikeysort(list, sorting, functions={'host':rank_host})
	if not list: addon.show_ok_dialog(['No sources were found for this item'], title='1Channel')
	if dialog and addon.get_setting('auto-play')=='false': #we're comming from a .strm file and can't create a directory so we have to pop a 
		sources = []									   #dialog if auto-play isn't on
		for item in list:
			try:
				label = '[%s] %s ' %(item['quality'],item['host'])
				if item.has_key('parts'): label += ' part 1'
				label = '%s (%s views)' %(label,item['views'])
				if item['verified']: label = '[COLOR gold]%s[/COLOR]' %label
				hosted_media = urlresolver.HostedMediaFile(url=item['url'], title=label)
				sources.append(hosted_media)
				if item['multi-part']:
					partnum = 2
					for part in item['parts']:
						label  = '     %s part %s' %(item['host'],partnum)
						hosted_media = urlresolver.HostedMediaFile(url=item['parts'][partnum-2], title=label)
						sources.append(hosted_media)
						partnum += 1
			except: addon.log('Error while trying to resolve %s' % url)
		source = urlresolver.choose_source(sources).get_url()
		PlaySource(source, title, img, year, imdbnum, video_type, season, episode)
	else:
		try:
			if addon.get_setting('auto-play')=='false': raise escape #skips the next line and goes into the else clause
			for source in list:
				try:
					PlaySource(source['url'], title, img, year, imdbnum, video_type, season, episode)
					break #Playback was successful, break out of the loop
				except: continue #Playback failed, try the next one
		except:
			for item in list:
				addon.log(item)
				label = '[%s] %s ' %(item['quality'],item['host'])
				if item.has_key('parts'): label += ' part 1'
				label = '%s (%s views)' %(label,item['views'])
				if item['verified']: label = '[COLOR gold]%s[/COLOR]' %label
				addon.add_directory({'mode':'PlaySource', 'url':item['url'], 'title':title,
									 'img':img, 'year':year, 'imdbnum':imdbnum,
									 'video_type':video_type, 'season':season, 'episode':episode},
				infolabels={'title':label}, is_folder=False, img=img, fanart=art('fanart.png'))
				if item['multi-part']:
					partnum = 2
					for part in item['parts']:
						label = '[I]          [/I]%s part %s' %(item['host'],partnum)
						partnum += 1
						addon.add_directory({'mode':'PlaySource', 'url':part, 'title':title,
											 'img':img, 'year':year, 'imdbnum':imdbnum,
											 'video_type':video_type, 'season':season, 'episode':episode},
						infolabels={'title':label}, is_folder=False, img=img, fanart=art('fanart.png'))
				
			addon.end_of_directory()

def PlaySource(url, title, img, year, imdbnum, video_type, season, episode):
	addon.log('Attempting to play url: %s' % url)
	stream_url = urlresolver.HostedMediaFile(url=url).resolve()
	playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
	playlist.clear()
	listitem = xbmcgui.ListItem(title, iconImage=img, thumbnailImage=img)
	if META_ON:
		if video_type == 'episode':
			try:
				meta = metaget.get_episode_meta(title,imdbnum,season,episode)
				tag = '%sx%s ' %(season,episode)
				meta['title'] = tag + meta['title']
				meta['TVShowTitle'] = title
				listitem.setInfo(type="Video", infoLabels=meta)
				# listitem.setInfo('video', {'TVShowTitle': title, 'Season': season, 'Episode': episode } )
			except: addon.log('Failed to get metadata for Title: %s IMDB: %s Season: %s Episode %s' %(title,imdbnum,season,episode))
		elif video_type == 'movie':
			try:
				meta = metaget.get_meta('movie', title.encode('utf-8'), year=year)
				listitem.setInfo(type="Video", infoLabels=meta)
			except: addon.log('Failed to get metadata for Title: %s IMDB: %s Season: %s Episode %s' %(title,imdbnum,season,episode))
	addon.resolve_url(stream_url)
	playlist.add(url=stream_url, listitem=listitem)
	player = playback.Player(imdbnum=imdbnum, video_type=video_type, title=title, season=season, episode=episode, year=year)
	player.play(playlist)
	while player._playbackLock.isSet():
		addon.log('Main function. Playback lock set. Sleeping for 250.')
		xbmc.sleep(250)

def ChangeWatched(imdb_id, video_type, name, season, episode, year='', watched='', refresh=False):
    metaget=metahandlers.MetaData(preparezip=prepare_zip)
    metaget.change_watched(video_type, name, imdb_id, season=season, episode=episode, year=year, watched=watched)
    if refresh:
        xbmc.executebuiltin("XBMC.Container.Refresh")

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
	last_search = addon.load_data('search')
	if not last_search: last_search = ''
	keyboard = xbmc.Keyboard()
	if section == 'tv': keyboard.setHeading('Search TV Shows')
	else: keyboard.setHeading('Search Movies')
	keyboard.setDefault(last_search)
	keyboard.doModal()
	if (keyboard.isConfirmed()):
		search_text = keyboard.getText()
		addon.save_data('search',search_text)
		if search_text.startswith('!#'):
			if search_text == '!#create metapacks': create_meta_packs()
			if search_text == '!#repair meta'	  : repair_missing_images()
			if search_text == '!#install all meta': install_all_meta()
		else:
			Search(section, keyboard.getText())
	else:
		BrowseListMenu(section)

def Search(section, query):
	html = GetURL(BASE_URL)
	r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
	pageurl = BASE_URL + '/index.php?search_keywords='
	pageurl += urllib.quote_plus(query)
	pageurl += '&key=' + r
	if section == 'tv':
		setView('tvshows', 'tvshows-view')
		pageurl += '&search_section=2'
		nextmode = 'TVShowSeasonList'
		video_type = 'tvshow'
		folder = True

	else:
		setView('movies', 'movies-view')
		nextmode = 'GetSources'
		video_type = 'movie'
		folder = addon.get_setting('auto-play')=='false'

	html = '> >> <'
	page = 0

	while html.find('> >> <') > -1 and page < 10:
		page += 1
		if page > 1: pageurl += '&page=%s' % page
		html = GetURL(pageurl, use_cache=False)

		r = re.search('number_movies_result">([0-9,]+)', html)
		if r: total = int(r.group(1).replace(',', ''))
		else: total = 0

		r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
		regex = re.finditer(r, html, re.DOTALL)
		resurls = []
		for s in regex:
			resurl,title,year,thumb = s.groups()
			title = unicode(title, 'latin-1')
			h = HTMLParser.HTMLParser()
			title = h.unescape(title)
			meta = {}
			if resurl not in resurls:
				resurls.append(resurl)
				runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'SaveFav', 'section':section, 'title':title.encode('utf-8'), 'url':BASE_URL+resurl, 'year':year})
				cm = add_contextsearchmenu(title, section)
				cm.append(('Add to Favorites', runstring,))
				runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'AddToLibrary', 'video_type':video_type, 'url':BASE_URL+resurl, 'title':title.encode('utf-8'), 'img':thumb, 'year':year})
				cm.append(('Add to Library', runstring,))
				if video_type == 'tvshow':
					runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'AddSubscription', 'video_type':video_type, 'url':BASE_URL+resurl, 'title':title.encode('utf-8'), 'img':thumb, 'year':year})
					cm.append(('Subscribe', runstring,))
				cm.append(('Show Information', 'XBMC.Action(Info)',))
				if year: disptitle = title +'('+year+')'
				else: disptitle = title
				img = thumb
				fanart = ''
				meta['imdb_id'] = ''

				if META_ON:
					try:
						if video_type == 'tvshow':
							meta = metaget.get_meta(video_type, title)
							if not (meta['imdb_id'] or meta['tvdb_id']):
								meta = metaget.get_meta(video_type, title, year=year)
						else: meta = metaget.get_meta(video_type, title, year=year)

						###Temporary work around. t0mm0.common isn't happy with the episode key being a str
						try: meta['episode'] = int(meta['episode'])
						except: pass

						if meta['trailer_url']:
							url = meta['trailer_url']
							url = re.sub('&feature=related','',url)
							url = url.encode('base-64').strip()
							runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'PlayTrailer', 'url':url})
							cm.append(('Watch Trailer', runstring,))
						if meta['overlay'] == 6: label = 'Mark as watched'
						else: label = 'Mark as unwatched'
						runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'ChangeWatched', 'title':title, 'imdbnum':meta['imdb_id'],  'video_type':video_type, 'year':year})
						cm.append((label, runstring,))
						
						if video_type == 'tvshow' and not USE_POSTERS:
							meta['cover_url'] = meta['banner_url']
						if POSTERS_FALLBACK and meta['cover_url'] in ('/images/noposter.jpg',''):
							meta['cover_url'] = thumb
						img = meta['cover_url']
					except: addon.log('Error assigning meta data for %s %s %s' %(video_type, title, year))

				if FANART_ON:
					try: fanart = meta['backdrop_url']
					except: pass
				
				meta['title'] = disptitle
				# print title
				addon.add_directory({'mode':nextmode, 'title':title.encode('utf-8'), 'url':BASE_URL + resurl, 'img':thumb, 'imdbnum':meta['imdb_id'], 'video_type':video_type, 'year':year},
									meta, cm, True, img, fanart, total_items=total, is_folder=folder)			


	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def AddonMenu():  #homescreen
	print '1Channel menu'
	addon.add_directory({'mode': 'BrowseListMenu', 'section': ''},   {'title':  'Movies'}, img=art('movies.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'BrowseListMenu', 'section': 'tv'}, {'title':  'TV shows'}, img=art('television.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'ManageSubscriptions'}, {'title':  'Manage Subscriptions'}, img=art('subscriptions.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'ResolverSettings'},   {'title':  'Resolver Settings'}, img=art('settings.png'), fanart=art('fanart.png'))
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseListMenu(section=None): #500
	print 'Browse Options'
	addon.add_directory({'mode': 'BrowseAlphabetMenu', 'section': section},   {'title':  'A-Z'}, img=art('atoz.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'GetSearchQuery', 'section': section},   {'title':  'Search'}, img=art('search.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'BrowseFavorites', 'section': section},   {'title':  'Favourites'}, img=art('favourites.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'BrowseByGenreMenu', 'section': section},   {'title':  'Genres'}, img=art('genres.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'featured'},   {'title':  'Featured'}, img=art('featured.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'views'},   {'title':  'Most Popular'}, img=art('most_popular.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'ratings'},   {'title':  'Highly rated'}, img=art('highly_rated.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'release'},   {'title':  'Date released'}, img=art('date_released.png'), fanart=art('fanart.png'))
	addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort': 'date'},   {'title':  'Date added'}, img=art('date_added.png'), fanart=art('fanart.png'))
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseAlphabetMenu(section=None): #1000
	print 'Browse by alphabet screen'
	addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort':'alphabet', 'letter':'123'},   {'title':  '#123'}, img=art('#123.png'), fanart=art('fanart.png'))
	for character in AZ_DIRECTORIES:
		addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort':'alphabet', 'letter': character},   {'title':  character}, img=art(character+'.png'), fanart=art('fanart.png'))
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def BrowseByGenreMenu(section=None, letter=None): #2000
	print 'Browse by genres screen'
	for genre in GENRES:
		addon.add_directory({'mode': 'GetFilteredResults', 'section': section, 'sort':'', 'genre': genre},   {'title':  genre})
	xbmcplugin.endOfDirectory(int(sys.argv[1]))

def add_contextsearchmenu(title, type):
	contextmenuitems = []
	if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.icefilms'):
		contextmenuitems.append(('Search Icefilms', 'XBMC.Container.Update(%s?mode=555&url=%s&search=%s&nextPage=%s)' %('plugin://plugin.video.icefilms/','http://www.icefilms.info/',title,'1')))
	if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.tubeplus'):
		if type == 'tv':
			section = 'tv-shows'
		else:
			section = 'movies'
		contextmenuitems.append(('Search tubeplus', 'XBMC.Container.Update(%s?mode=Search&section=%s&query=%s)' %('plugin://plugin.video.tubeplus/',section,title)))
	if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.tvlinks'):
		if type == 'tv':
			contextmenuitems.append(('Search tvlinks', 'XBMC.Container.Update(%s?mode=Search&query=%s)' %('plugin://plugin.video.tvlinks/',title)))
	if os.path.exists(xbmc.translatePath("special://home/addons/")+'plugin.video.solarmovie'):
		if type == 'tv':
			section = 'tv-shows'
		else:
			section = 'movies'
		contextmenuitems.append(('Search solarmovie', 'XBMC.Container.Update(%s?mode=Search&section=%s&query=%s)' %('plugin://plugin.video.solarmovie/',section,title)))

	return contextmenuitems

def GetFilteredResults(section=None, genre=None, letter=None, sort='alphabet', page=None): #3000
	addon.log('Filtered results for Section: %s Genre: %s Letter: %s Sort: %s Page: %s' %(section, genre, letter, sort, page))

	pageurl = BASE_URL + '/?'
	if section == 'tv': pageurl += 'tv'
	if genre  :	pageurl += '&genre='  + genre
	if letter :	pageurl += '&letter=' + letter
	if sort   :	pageurl += '&sort='   + sort
	if page	  : pageurl += '&page=%s' % page

	if page: page = int(page) + 1
	else: page = 2

	if section == 'tv':
		nextmode = 'TVShowSeasonList'
		video_type = 'tvshow'
		folder = True

	else:
		nextmode = 'GetSources'
		section = 'movie'
		video_type = 'movie'
		folder = addon.get_setting('auto-play')=='false'

	html = GetURL(pageurl)

	r = re.search('number_movies_result">([0-9,]+)', html)
	if r: total = int(r.group(1).replace(',', ''))
	else: total = 0
	total_pages = total/24
	total = min(total,24)

	r = 'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
	regex = re.finditer(r, html, re.DOTALL)
	resurls = []
	for s in regex:
		resurl,title,year,thumb = s.groups()
		title = unicode(title, 'latin-1')
		h = HTMLParser.HTMLParser()
		title = h.unescape(title)
		meta = {}
		if resurl not in resurls:
			resurls.append(resurl)
			runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'SaveFav', 'section':section, 'title':title.encode('utf-8'), 'url':BASE_URL+resurl, 'year':year})
			cm = add_contextsearchmenu(title, section)
			cm.append(('Add to Favorites', runstring,))
			runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'AddToLibrary', 'video_type':video_type, 'url':BASE_URL+resurl, 'title':title.encode('utf-8'), 'img':thumb, 'year':year})
			cm.append(('Add to Library', runstring,))
			if video_type == 'tvshow':
				runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'AddSubscription', 'video_type':video_type, 'url':BASE_URL+resurl, 'title':title.encode('utf-8'), 'img':thumb, 'year':year})
				cm.append(('Subscribe', runstring,))
			cm.append(('Show Information', 'XBMC.Action(Info)',))
			if year: disptitle = title +'('+year+')'
			else: disptitle = title
			img = thumb
			fanart = ''
			meta['imdb_id'] = ''

			if META_ON:
				try:
					if video_type == 'tvshow':
						meta = metaget.get_meta(video_type, title)
						if not (meta['imdb_id'] or meta['tvdb_id']):
							meta = metaget.get_meta(video_type, title, year=year)

					###Temporary work around. t0mm0.common isn't happy with the episode key being a str
					try: meta['episode'] = int(meta['episode'])
					except: pass

					else: meta = metaget.get_meta(video_type, title, year=year)
					if meta['trailer_url']:
						url = meta['trailer_url']
						url = re.sub('&feature=related','',url)
						url = url.encode('base-64').strip()
						runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'PlayTrailer', 'url':url})
						cm.append(('Watch Trailer', runstring,))
					if meta['overlay'] == 6: label = 'Mark as watched'
					else: label = 'Mark as unwatched'
					runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'ChangeWatched', 'title':title, 'imdbnum':meta['imdb_id'],  'video_type':video_type, 'year':year})
					cm.append((label, runstring,))
					
					if video_type == 'tvshow' and not USE_POSTERS:
						meta['cover_url'] = meta['banner_url']
					if POSTERS_FALLBACK and meta['cover_url'] in ('/images/noposter.jpg',''):
						meta['cover_url'] = thumb
					img = meta['cover_url']
				except: addon.log('Error assigning meta data for %s %s %s' %(video_type, title, year))

			if FANART_ON:
				try: fanart = meta['backdrop_url']
				except: pass
			
			meta['title'] = disptitle

			addon.add_directory({'mode':nextmode, 'title':title.encode('utf-8'), 'url':BASE_URL + resurl, 'img':thumb, 'imdbnum':meta['imdb_id'], 'video_type':video_type, 'year':year},
								meta, cm, True, img, fanart, total_items=total, is_folder=folder)			

	if html.find('> >> <') > -1:
		label = 'Skip to Page...'
		command = addon.build_plugin_url({'mode':'PageSelect', 'pages':total_pages, 'section':section, 'genre':genre, 'letter':letter, 'sort':sort})
		command = 'RunPlugin(%s)' %command
		cm = [(label, command)]
		meta = {'title':'Next Page >>'}
		addon.add_directory({'mode':'GetFilteredResults', 'section':section, 'genre':genre, 'letter':letter, 'sort':sort, 'page':page},
							meta, cm, True, art('nextpage.png'), art('fanart.png'), is_folder=True)

	# xbmcplugin.endOfDirectory(int(sys.argv[1]))
	addon.end_of_directory()
	if   video_type == 'tvshow': setView('tvshows', 'tvshows-view')
	elif video_type == 'movie' : setView('movies', 'movies-view')

def TVShowSeasonList(url, title, year, old_imdb, old_tvdb=''): #4000
	addon.log('Seasons for TV Show %s' % url)
	net = Net()
	cookiejar = addon.get_profile()
	cookiejar = os.path.join(cookiejar,'cookies')
	html = net.http_GET(url).content
	net.save_cookies(cookiejar)
	adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
	r = re.search(adultregex, html, re.DOTALL)
	if r:
		addon.log('Adult content url detected')
		adulturl = BASE_URL + r.group(1)
		headers = {'Referer': url}
		net.set_cookies(cookiejar)
		html = net.http_GET(adulturl, headers=headers).content

	db = sqlite.connect( DB )

	try:
		new_imdb = re.search('mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"', html).group(1)
	except: new_imdb = ''
	seasons = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
	if not seasons: addon.log_error('couldn\'t find seasons')
	else:
		season_container = seasons.group(1)
		season_nums = re.compile('<a href=".+?">Season ([0-9]{1,2})').findall(season_container)
		fanart = ''
		imdbnum = old_imdb
		if META_ON: 
			if not old_imdb and new_imdb:
				addon.log('Imdb ID not recieved from title search, updating with new id of %s' % new_imdb)
				try:
					addon.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s'%(title,old_imdb,old_tvdb,new_imdb, year))
					metaget.update_meta('tvshow', title, old_imdb, old_tvdb, new_imdb)
				except: 
					addon.log('Error while trying to update metadata with:')
					# addon.log('Title: %s Old IMDB: %s Old TVDB: %s New IMDB %s Year: %s'%(title,old_imdb,old_tvdb,new_imdb, year))
				imdbnum = new_imdb

			try: season_meta = metaget.get_seasons(title, imdbnum, season_nums)
			except: pass
			if FANART_ON:
				try: fanart = temp['backdrop_url']
				except: pass
		seasonList = season_container.split('<h2>')
		num = 0
		temp = {}
		for eplist in seasonList:
			r = re.search('<a.+?>(.+?)</a>', eplist)
			if r:
				season_name = r.group(1)
				try:
					temp = season_meta[num]
					if META_ON and FANART_ON:
						try: fanart = temp['backdrop_url']
						except: pass
				except: 
					temp['cover_url']    = ''
					temp['backdrop_url'] = ''
				temp['title'] = season_name

				addon.log('Season name: %s' %season_name)
				db.execute('INSERT or REPLACE into seasons (season,contents) VALUES(?,?)',
								(season_name, eplist))

				addon.add_directory({'mode':'TVShowEpisodeList', 'season':season_name, 'imdbnum':imdbnum, 'title':title},
									temp, img=temp['cover_url'], fanart=fanart,
									total_items=len(seasonList), is_folder=True)

				db.commit()
				num += 1
		xbmcplugin.endOfDirectory(int(sys.argv[1]))
		setView('seasons', 'seasons-view')
		db.close()

def TVShowEpisodeList(ShowTitle, season, imdbnum, tvdbnum): #5000
	db = sqlite.connect( DB )
	eplist = db.execute('SELECT contents FROM seasons WHERE season=?', (season,))
	eplist = eplist.fetchone()[0]
	db.close()
	r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
	episodes = re.finditer(r, eplist, re.DOTALL)
	folder = addon.get_setting('auto-play')=='false'
	for ep in episodes:
		cm = []
		cm.append(('Show Information', 'XBMC.Action(Info)',))
		epurl, eptitle = ep.groups()
		meta = {}
		eptitle = re.sub('<[^<]+?>', '', eptitle.strip())
		eptitle = re.sub('\s\s+' , ' ', eptitle)

		season = re.search('/season-([0-9]{1,4})-', epurl).group(1)
		epnum = re.search('-episode-([0-9]{1,3})', epurl).group(1)
		fanart = ''
		if META_ON and imdbnum:
			try:
				meta = metaget.get_episode_meta(ShowTitle.decode('utf-8'),imdbnum,season,epnum)
				if meta['overlay'] == 6: label = 'Mark as watched'
				else: label = 'Mark as unwatched'
				runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'ChangeWatched', 'title':ShowTitle, 'imdbnum':meta['imdb_id'], 'season':season, 'episode':epnum,  'video_type':'episode', 'year':year})
				cm.append((label, runstring,))
			except:
				meta['cover_url'] = ''
				meta['backdrop_url'] = ''
				meta['title'] = eptitle
				addon.log('Error getting metadata for %s season %s episode %s with imdbnum %s' % (ShowTitle,season,epnum,imdbnum))
		else:
			meta['cover_url'] = ''
			meta['title'] = eptitle
		img = meta['cover_url']

		if meta['title'] == ShowTitle.decode('utf-8'):
			meta['title'] = eptitle
			addon.log('Episode title not found in metadata, using title from website')
		else:
			tag = '%sx%s ' %(season,epnum)
			meta['title'] = tag + meta['title']

		if not meta['title']: meta['title'] = eptitle

		meta['TVShowTitle'] = ShowTitle
		if FANART_ON:
			try: fanart =  meta['backdrop_url']
			except: pass
		url = BASE_URL + epurl
		addon.add_directory({'mode':'GetSources', 'url':url, 'imdbnum':imdbnum, 'title':ShowTitle, 'img':img},
						infolabels=meta, contextmenu_items=cm, context_replace=True, is_folder=folder, img=img, fanart=fanart)

	setView('episodes', 'episodes-view')
	addon.end_of_directory()

def BrowseFavorites(section): #8000
	db = sqlite.connect( DB )
	if section == 'tv':  setView('tvshows', 'tvshows-view')
	else: setView('movies', 'movies-view')
	if section == 'tv':
		nextmode = 'TVShowSeasonList'
		type = 'tvshow'
		folder = True
	else: 
		nextmode = 'GetSources'
		section  = 'movie'
		type 	 = 'movie'
		folder   = addon.get_setting('auto-play')=='false'
	favs = db.execute('SELECT type, name, url, year FROM favorites WHERE type = ? ORDER BY name', (section,))
	for row in favs:
		title	  = row[1]
		favurl	  = row[2]
		year	  = row[3]
		cm		  = []
		meta	  = {}
		if year: disptitle = title +'('+year+')'
		else:	 disptitle = title
		img = ''
		fanart = ''

		if META_ON:
			# try:
				title = title.encode('ascii', 'ignore')
				try: 
					meta = metaget.get_meta(type,title,year=year)

					###Temporary work around. t0mm0.common isn't happy with the episode key being a str
					try: meta['episode'] = int(meta['episode'])
					except: pass

				except: print 'Failed to get metadata for %s %s %s' %(type,title,year)

				if 'trailer_url' in meta:
					url = meta['trailer_url']
					url = re.sub('&feature=related','',url)
					url = url.encode('base-64').strip()
					runstring = 'RunScript(plugin.video.1channel,%s,?mode=PlayTrailer&url=%s)' %(sys.argv[1],url)
					cm.append(('Watch Trailer', runstring))

				if type == 'tvshow'and not USE_POSTERS:
					meta['cover_url'] = meta['banner_url']
				
				if meta['overlay'] == 6: label = 'Mark as watched'
				else: label = 'Mark as unwatched'
				runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'ChangeWatched', 'title':title, 'imdbnum':meta['imdb_id'],  'video_type':type, 'year':year})
				cm.append((label, runstring))

				img = meta['cover_url']
			# except: addon.log('Error while assigning meta data for %s %s %s'%(type,title,year))
		meta['title'] = disptitle

		if FANART_ON:
			try: fanart = meta['backdrop_url']
			except: pass
		remfavstring = 'RunScript(plugin.video.1channel,%s,?mode=DeleteFav&section=%s&title=%s&year=%s&url=%s)' %(sys.argv[1],section,title,year,favurl)
		cm.append(('Remove from Favorites', remfavstring))

		addon.add_directory({'mode':nextmode, 'title':title, 'url':favurl, 'imdbnum':meta['imdb_id'], 'video_type':type, 'year':year},
							meta, cm, True, img, fanart, is_folder=folder)	
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

def install_metapack(pack):
	packs = metapacks.list()
	pack_details = packs[pack]
	mc = metacontainers.MetaContainer()
	work_path  = mc.work_path
	cache_path = mc.cache_path
	zip = os.path.join(work_path, pack)

	net = Net()
	cookiejar = addon.get_profile()
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
	install_local_zip(zip)

def install_local_zip(zip):
	mc = metacontainers.MetaContainer()
	work_path  = mc.work_path
	cache_path = mc.cache_path

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
	if addon.get_setting('auto-view') == 'true':
		xbmc.executebuiltin("Container.SetViewMode(%s)" % addon.get_setting(viewType) )

	# set sort methods - probably we don't need all of them
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_UNSORTED )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_LABEL )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RATING )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_DATE )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_PROGRAM_COUNT )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RUNTIME )
	xbmcplugin.addSortMethod( handle=int( sys.argv[ 1 ] ), sortMethod=xbmcplugin.SORT_METHOD_GENRE )
 
def AddToLibrary(video_type, url, title, img, year, imdbnum):
	addon.log('Creating .strm for %s %s %s %s %s %s'%(video_type, url, unicode(title,'utf-8'), img, year, imdbnum))
	if video_type == 'tvshow': 
		save_path = addon.get_setting('tvshow-folder')
		save_path = xbmc.translatePath(save_path)
		ShowTitle = unicode(title,'utf-8').strip()
		net = Net()
		cookiejar = addon.get_profile()
		cookiejar = os.path.join(cookiejar,'cookies')
		html = net.http_GET(url).content
		net.save_cookies(cookiejar)
		adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
		r = re.search(adultregex, html, re.DOTALL)
		if r:
			addon.log('Adult content url detected')
			adulturl = BASE_URL + r.group(1)
			headers = {'Referer': url}
			net.set_cookies(cookiejar)
			html = net.http_GET(adulturl, headers=headers).content
		seasons = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
		if not seasons: addon.log_error('No Seasons found for %s at %s' %(ShowTitle,url))
		else:
			season_container = seasons.group(1)
			seasonList = season_container.split('<h2>')
			for eplist in seasonList:
				r = re.search('<a.+?>(.+?)</a>', eplist)
				if r:
					season = r.group(1)
					r = '"tv_episode_item".+?href="(.+?)">(.*?)</a>'
					episodes = re.finditer(r, eplist, re.DOTALL)
					for ep in episodes:
						epurl, eptitle = ep.groups()
						eptitle = re.sub('<[^<]+?>', '', eptitle.strip())
						eptitle = re.sub('\s\s+' , ' ', eptitle)

						match = re.search('tv-\d{1,10}-.*/season-(\d{1,4})-episode-(\d{1,4})', epurl, re.IGNORECASE | re.DOTALL)
						seasonnum = match.group(1)
						epnum = match.group(2)

						filename = '%sx%s %s.strm' %(seasonnum,epnum,eptitle)
						final_path = os.path.join(save_path, ShowTitle, season, filename)
						final_path = xbmc.makeLegalFilename(final_path).decode('utf-8')
						if not os.path.isdir(os.path.dirname(final_path)):
							try:    os.makedirs(os.path.dirname(final_path))
							except: addon.log('Failed to create directory %s' %final_path)

						playurl = BASE_URL + epurl
						strm_string = addon.build_plugin_url({'mode':'GetSources', 'url':playurl, 'imdbnum':'', 'title':ShowTitle.encode('utf-8'), 'img':'', 'dialog':1})
						try:
							file = open(final_path,'w')
							file.write(strm_string)
							file.close()
						except: addon.log('Failed to create .strm file: %s' %final_path)

	elif video_type == 'movie' :
		save_path = addon.get_setting('movie-folder')
		save_path = xbmc.translatePath(save_path)
		strm_string = addon.build_plugin_url({'mode':'GetSources', 'url':url, 'imdbnum':imdbnum, 'title':title, 'img':img, 'year':year, 'dialog':1})
		if year: title = '%s(%s)'% (title,year)
		filename = '%s.strm' %title
		final_path = os.path.join(save_path,title,filename)
		final_path = xbmc.makeLegalFilename(final_path).decode('utf-8')
		if not os.path.isdir(os.path.dirname(final_path)):
			try:    os.makedirs(os.path.dirname(final_path))
			except: addon.log('Failed to create directory %s' %final_path)
		# try:
		file = open(final_path,'w')
		file.write(strm_string)
		file.close()
		# except: addon.log('Failed to create .strm file: %s' %final_path)

def AddSubscription(url, title, img, year, imdbnum):
	try:
		db = sqlite.connect(DB)
		db.execute('INSERT INTO subscriptions (url, title, img, year, imdbnum) VALUES (?,?,?,?,?)', (url, unicode(title,'utf-8'), img, year, imdbnum))
		db.commit()
		db.close()
		AddToLibrary('tvshow', url, title, img, year, imdbnum)
		builtin = "XBMC.Notification(Subscribe,Subscribed to '%s',2000)" %title
		xbmc.executebuiltin(builtin)
	except sqlite.IntegrityError:
		builtin = "XBMC.Notification(Subscribe,Already subscribed to '%s',2000)" %title
		xbmc.executebuiltin(builtin)

def CancelSubscription(url, title, img, year, imdbnum):
	db = sqlite.connect(DB)
	db.execute('DELETE FROM subscriptions WHERE url=? AND title=? AND year=?', (url,unicode(title,'utf-8'),year))
	db.commit()
	db.close()
	xbmc.executebuiltin('Container.Refresh')

def UpdateSubscriptions():
	db = sqlite.connect(DB)
	for sub in db.execute('SELECT * FROM subscriptions'):
		AddToLibrary('tvshow',sub[0],sub[1].encode('utf-8'),sub[2],sub[3],sub[4])
	db.close()

def ManageSubscriptions():
	addon.add_item({'mode':'UpdateSubscriptions'}, {'title':'Update Subscriptions'})
	db = sqlite.connect(DB)
	for sub in db.execute('SELECT * FROM subscriptions'):
		cm = []
		runstring = 'RunPlugin(%s)' % addon.build_plugin_url({'mode':'CancelSubscription', 'url':sub[0], 'title':sub[1].encode('utf-8'), 'img':sub[2], 'year':sub[3], 'imdbnum':sub[4]})
		cm.append(('Cancel subscription', runstring,))
		addon.add_item({'mode':'ManageSubscriptions'},{'title':sub[1]},cm,True,sub[2],art('fanart.png'))
	db.close()
	addon.end_of_directory()

def clean_filename(filename):
	# filename = addon.unescape(filename)
	return re.sub('[\\/:"*?<>|]+',' ',filename)

def multikeysort(items, columns, functions={}, getter=itemgetter):
    """Sort a list of dictionary objects or objects by multiple keys bidirectionally.

    Keyword Arguments:
    items -- A list of dictionary objects or objects
    columns -- A list of column names to sort by. Use -column to sort in descending order
    functions -- A Dictionary of Column Name -> Functions to normalize or process each column value
    getter -- Default "getter" if column function does not exist
              operator.itemgetter for Dictionaries
              operator.attrgetter for Objects
    """
    comparers = []
    for col in columns:
        column = col[1:] if col.startswith('-') else col
        if not column in functions:
            functions[column] = getter(column)
        comparers.append((functions[column], 1 if column == col else -1))

    def comparer(left, right):
        for func, polarity in comparers:
            result = cmp(func(left), func(right))
            if result:
                return polarity * result
        else:
            return 0
    return sorted(items, cmp=comparer)

def compose(inner_func, *outer_funcs):
     """Compose multiple unary functions together into a single unary function"""
     if not outer_funcs:
         return inner_func
     outer_func = compose(*outer_funcs)
     return lambda *args, **kwargs: outer_func(inner_func(*args, **kwargs))

def rank_host(source):
	host = source['host']
	ranking = addon.get_setting('host-rank').split(',')
	host = host.lower()
	for tier in ranking:
		tier = tier.lower()
		if host in tier.split('|'):
			return ranking.index(tier) + 1
	return 1000

initDatabase()

mode 		= addon.queries.get('mode', 	  None)
section 	= addon.queries.get('section',    '')
genre 		= addon.queries.get('genre', 	  '')
letter 		= addon.queries.get('letter', 	  '')
sort 		= addon.queries.get('sort', 	  '')
url 		= addon.queries.get('url', 		  '')
title 		= addon.queries.get('title',	  '')
img 		= addon.queries.get('img', 		  '')
season 		= addon.queries.get('season', 	  '')
query 		= addon.queries.get('query', 	  '')
page 		= addon.queries.get('page', 	  '')
imdbnum 	= addon.queries.get('imdbnum',	  '')
year 		= addon.queries.get('year', 	  '')
video_type  = addon.queries.get('video_type', '')
episode		= addon.queries.get('episode',    '')
season 		= addon.queries.get('season', 	  '')
tvdbnum 	= addon.queries.get('tvdbnum', 	  '')
dialog	 	= addon.queries.get('dialog', 	  '')

addon.log(addon.queries)

if mode=='main':
	AddonMenu()
elif mode=='GetSources':
	GetSources(url,title,img,year,imdbnum,dialog)
elif mode=='PlaySource':
	PlaySource(url, title, img, year, imdbnum, video_type, season, episode)
elif mode=='PlayTrailer':
	PlayTrailer(url)
elif mode=='BrowseListMenu':
	BrowseListMenu(section)
elif mode=='BrowseAlphabetMenu':
	BrowseAlphabetMenu(section)
elif mode=='BrowseByGenreMenu':
	BrowseByGenreMenu(section)
elif mode=='GetFilteredResults':
	GetFilteredResults(section, genre, letter, sort, page)
elif mode=='TVShowSeasonList':
	TVShowSeasonList(url, title, year, tvdbnum)
elif mode=='TVShowEpisodeList':
	TVShowEpisodeList(title, season, imdbnum, tvdbnum)
elif mode=='GetSearchQuery':
	GetSearchQuery(section)
elif mode=='7000': # Enables Remote Search
	Search(section, query)
elif mode=='BrowseFavorites':
	BrowseFavorites(section)
elif mode=='SaveFav':
	SaveFav(section, title, url, img, year)
elif mode=='DeleteFav':
	DeleteFav(section, title, url)
	xbmc.executebuiltin('Container.Refresh')
elif mode=='ChangeWatched':
	ChangeWatched(imdb_id=imdbnum, video_type=video_type, name=title, season=season, episode=episode, year=year)
	xbmc.executebuiltin('Container.Refresh')
elif mode=='9988': #Metahandler Settings
	print "Metahandler Settings"
	import metahandler
	metahandler.display_settings()
elif mode=='ResolverSettings':
	urlresolver.display_settings()
elif mode=='install_metapack':
	install_metapack(title)
elif mode=='install_local_metapack':
	dialog = xbmcgui.Dialog()
	zip = dialog.browse(1, 'Metapack', 'files', '.zip', False, False)
	install_local_zip(zip)
elif mode=='AddToLibrary':
	AddToLibrary(video_type, url, title, img, year, imdbnum)
	builtin = "XBMC.Notification(Add to Library,Added '%s' to library,2000)" %title
	xbmc.executebuiltin(builtin)
elif mode=='UpdateSubscriptions':
	UpdateSubscriptions()
elif mode=='AddSubscription':
	AddSubscription(url, title, img, year, imdbnum)
elif mode=='ManageSubscriptions':
	ManageSubscriptions()
elif mode=='CancelSubscription':
	CancelSubscription(url, title, img, year, imdbnum)
elif mode=='PageSelect':
	pages = int(addon.queries['pages'])
	dialog = xbmcgui.Dialog()
	options = []
	for page in range(pages):
		label = 'Page %s' % str(page+1)
		options.append(label)
	index = dialog.select('Skip to page', options)
	url = addon.build_plugin_url({'mode':'GetFilteredResults', 'section':section, 'genre':genre, 'letter':letter, 'sort':sort, 'page':index+1})
	builtin = 'Container.Update(%s)' %url
	xbmc.executebuiltin(builtin)
elif mode=='test':
	solver = captcha.InputWindow(captcha = 'C:\DialogBack.png')
	solution = solver.get()
	if solution:
		addon.log('Solution provided: %s' %solution)
	else: addon.log('Dialog was canceled')