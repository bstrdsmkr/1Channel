"""
    1Channel XBMC Addon
    Copyright (C) 2014 tknorris

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
"""
import utils
import time
import urllib2
import urllib
import re
import HTMLParser
import xbmc
import xbmcgui
import sys
import os
import math
from operator import itemgetter
from addon.common.net import Net
from addon.common.addon import Addon

USER_AGENT = ("User-Agent:Mozilla/5.0 (Windows NT 6.2; WOW64)"
              "AppleWebKit/537.17 (KHTML, like Gecko)"
              "Chrome/24.0.1312.56")

_1CH = Addon('plugin.video.1channel', sys.argv)
ADDON_PATH = _1CH.get_path()
ICON_PATH = os.path.join(ADDON_PATH, 'icon.png')
ITEMS_PER_PAGE=24
FAVS_PER_PAGE=40
MAX_PAGES=10

class PW_Scraper():
    def __init__(self, username, password):
        self.base_url = _1CH.get_setting('domain')
        if (_1CH.get_setting("enableDomain")=='true') and (len(_1CH.get_setting("customDomain")) > 10):
            self.base_url = _1CH.get_setting("customDomain")

        self.username=username
        self.password=password
        self.res_pages=-1
        self.res_total=-1
        self.imdb_num=''
    
    def add_favorite(self,url):
        _1CH.log('Saving favorite to website: %s' % (url))
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', url)
        if id_num:
            save_url = "%s/addtofavs.php?id=%s&whattodo=add"
            save_url = save_url % (self.base_url, id_num.group(1))
            _1CH.log('Save URL: %s' %(save_url))
            html = self.__get_url(save_url,login=True)
            ok_message = "<div class='ok_message'>Movie added to favorites"
            error_message = "<div class='error_message'>This video is already"
            if ok_message in html:
                return
            elif error_message in html:
                raise
            else:
                _1CH.log('Unable to confirm success')
                _1CH.log(html)
    
    def delete_favorite(self, url):
        _1CH.log('Deleting favorite from website')
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', url)
        if id_num:
            del_url = "%s/addtofavs.php?id=%s&whattodo=delete"
            del_url = del_url % (self.base_url, id_num.group(1))
            _1CH.log('Delete URL: %s' %(del_url))
            self.__get_url(del_url,login=True)
    
    def get_favorities(self, section, page=None, paginate=False):
        _1CH.log('Getting %s favorite from website' % (section))
        fav_url = '/profile.php?user=%s&fav&show=%s'
        if page: fav_url += '&page=%s' %(page)
        url = self.base_url + fav_url % (self.username, section)
        html=self.__get_url(url)
        r = re.search('strong>Favorites \(\s+([0-9,]+)\s+\)', html)
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0
        self.res_pages = int(math.ceil(total/float(FAVS_PER_PAGE)))
        self.res_total = total
        return self.__get_fav_gen(html, url, page, paginate)   
    
    def __get_fav_gen(self, html, url, page, paginate):
        if not page: page=1
        pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{1,4})?\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a></td>.+?class="favs_deleted"><a href=\'(.+?)\' ref=\'delete_fav\''''
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        while True:
            fav={}
            for item in regex.finditer(html):
                link, img, year, title, delete = item.groups()
                if not year or len(year) != 4: year = ''
                fav['url']=link
                fav['img']=img
                fav['year']=year
                fav['title']=title
                fav['delete']=delete
                yield fav
            
            # if we're not paginating, then keep yielding until we run out of pages or hit the max
            if not paginate:
                if html.find('> >> <') == -1 or int(page)>MAX_PAGES:
                    break
                
                page += 1
                pageurl = '%s&page=%s' % (url, page)
                html = self.__get_cached_url(pageurl, cache_limit=0)
            # if we are paginating, just do this page
            else:
                break
    
    def get_sources(self, url):
        html = self.__get_cached_url(self.base_url + url, cache_limit=2)
        adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
        adult = re.search(adultregex, html, re.DOTALL)
        if adult:
            _1CH.log('Adult content url detected')
            adulturl = self.base_url + adult.group(1)
            headers = {'Referer': url}
            html = self.__get_url(adulturl, headers=headers, login=True)
        
        imdbregex = 'mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"'
        match = re.search(imdbregex, html)
        if match:
            self.imdb_num = match.group(1)
        
        sort_order = []
        if _1CH.get_setting('sorting-enabled') == 'true':
            sort_tiers = ('first-sort', 'second-sort', 'third-sort', 'fourth-sort', 'fifth-sort')
            sort_methods = (None, 'host', 'verified', 'quality', 'views', 'multi-part')
            for tier in sort_tiers:
                if int(_1CH.get_setting(tier)) > 0:
                    method = sort_methods[int(_1CH.get_setting(tier))]
                    if _1CH.get_setting(tier + '-reversed') == 'true':
                        method = '-%s' %method
                    sort_order.append(method)
                else: break

        hosters = []
        container_pattern = r'<table[^>]+class="movie_version[ "][^>]*>(.*?)</table>'
        item_pattern = (
            r'quality_(?!sponsored|unknown)([^>]*)></span>.*?'
            r'url=([^&]+)&(?:amp;)?domain=([^&]+)&(?:amp;)?(.*?)'
            r'"version_veiws"> ([\d]+) views</')
        for container in re.finditer(container_pattern, html, re.DOTALL | re.IGNORECASE):
            for source in re.finditer(item_pattern, container.group(1), re.DOTALL):
                qual, url, host, parts, views = source.groups()
         
                item = {'host': host.decode('base-64'), 'url': url.decode('base-64')}
                item['verified'] = source.group(0).find('star.gif') > -1
                item['quality'] = qual.upper()
                item['views'] = int(views)
                pattern = r'<a href=".*?url=(.*?)&(?:amp;)?.*?".*?>(part \d*)</a>'
                other_parts = re.findall(pattern, parts, re.DOTALL | re.I)
                if other_parts:
                    item['multi-part'] = True
                    item['parts'] = [part[0].decode('base-64') for part in other_parts]
                else:
                    item['multi-part'] = False
                hosters.append(item)
     
                if sort_order:
                    hosters = self.__multikeysort(hosters, sort_order, functions={'host': utils.rank_host})
        
        return hosters
                    
    # returns a generator of results of a title search each of which is a dictionary of url, title, img, and year
    def search(self,section, query):
        return self.__search(section, urllib.quote_plus(query))
    
    # returns a generator of results of a description search each of which is a dictionary of url, title, img, and year
    def search_desc(self, section, query):
        keywords = urllib.quote_plus(query)
        keywords += '&desc_search=1' ## 1 = Search Descriptions
        return self.__search(section, keywords)

    # returns a generator of results of a advanced search each of which is a dictionary of url, title, img, and year
    def search_advanced(self, section, query, tag, description, country, genre, actor, director, year, month, decade, host, rating, advanced):
        keywords = urllib.quote_plus(query)
        if (description==True): keywords += '&desc_search=1'
        keywords += '&tag=' + urllib.quote_plus(tag)
        keywords += '&genre=' + urllib.quote_plus(genre)
        keywords += '&actor_name=' + urllib.quote_plus(actor)
        keywords += '&director=' + urllib.quote_plus(director)
        keywords += '&country=' + urllib.quote_plus(country)
        keywords += '&year=' + urllib.quote_plus(year)
        keywords += '&month=' + urllib.quote_plus(month)
        keywords += '&decade=' + urllib.quote_plus(decade)
        keywords += '&host=' + urllib.quote_plus(host)
        keywords += '&search_rating=' + urllib.quote_plus(rating) ## Rating higher than (#), 0-4
        keywords += '&advanced=' + urllib.quote_plus(advanced)
        return self.__search(section, keywords)
        
    # internal search function once a search url is (mostly) built
    def __search(self, section, keywords):
        search_url = self.base_url + '/index.php?search_keywords='
        search_url += keywords
        html =self. __get_cached_url(self.base_url, cache_limit=0)
        r = re.search('input type="hidden" name="key" value="([0-9a-f]*)"', html).group(1)
        search_url += '&key=' + r
        if section == 'tv': search_url += '&search_section=2'
        _1CH.log('Issuing search: %s' % (search_url))

        html = self.__get_cached_url(search_url, cache_limit=0)
        r = re.search('number_movies_result">([0-9,]+)', html)
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0
        self.res_pages = int(math.ceil(total/float(ITEMS_PER_PAGE)))
        self.res_total = total
        return self.__search_gen(html,search_url)
    
    # generator function for search results
    def __search_gen(self,html,search_url):
        page=1
        while page<=MAX_PAGES:
            pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
            result={}
            for item in re.finditer(pattern, html, re.DOTALL):
                link, title, year, img = item.groups()
                if not year or len(year) != 4: year = ''
                result['url']=link
                result['title']=title
                result['year']=year
                result['img']=img
                yield result
            
            if html.find('> >> <') == -1:
                break
            
            page += 1
            pageurl = '%s&page=%s' % (search_url, page)
            html = self.__get_cached_url(pageurl, cache_limit=0)

    def get_filtered_results(self, section, genre, letter, sort, page=None):
        pageurl = self.base_url + '/?'
        if section == 'tv': pageurl += 'tv'
        if genre:  pageurl += '&genre=' + genre
        if letter:  pageurl += '&letter=' + letter
        if sort:     pageurl += '&sort=' + sort
        if page:   pageurl += '&page=%s' % page
        _1CH.log('Getting filtered results: %s' % (pageurl))
    
        html = self.__get_cached_url(pageurl)
    
        r = re.search('number_movies_result">([0-9,]+)', html)
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0
        self.res_pages = int(math.ceil(total/float(ITEMS_PER_PAGE)))
        return self.__filtered_results_gen(html)
        
    def __filtered_results_gen(self, html):
        pattern = r'class="index_item.+?href="(.+?)" title="Watch (.+?)"?\(?([0-9]{4})?\)?"?>.+?src="(.+?)"'
        regex = re.compile(pattern, re.DOTALL)
        result={}
        for item in regex.finditer(html):
            link, title, year, img = item.groups()
            if not year or len(year) != 4: year = ''
            result['url']=link
            result['title']=title
            result['year']=year
            result['img']=img
            yield result
    
    def get_last_res_pages(self):
        return self.res_pages

    def get_last_res_total(self):
        return self.res_total
    
    def get_last_imdbnum(self):
        return self.imdb_num

    def get_season_list(self, url, cached=True):
        _1CH.log('Getting season list (%s): %s' % (cached,url))
        if cached:
            html = self.__get_cached_url(self.base_url+url)
        else:
            html = self.__get_url(self.base_url+url)
            
        adultregex = '<div class="offensive_material">.+<a href="(.+)">I understand'
        r = re.search(adultregex, html, re.DOTALL)
        if r:
            _1CH.log('Adult content url detected')
            adulturl = self.base_url + r.group(1)
            headers = {'Referer': url}
            html = self.__get_url(adulturl, headers=headers, login=True)

        match = re.search('mlink_imdb">.+?href="http://www.imdb.com/title/(tt[0-9]{7})"', html)
        self.imdb_num = match.group(1) if match else ''
        return self.__season_gen(html)
    
    def __season_gen(self, html):
        match = re.search('tv_container(.+?)<div class="clearer', html, re.DOTALL)
        if not match:
            raise StopIteration()
        
        show_container = match.group(1)
        season_containers = show_container.split('<h2>')

        for season_html in season_containers:
            r = re.search(r'<a.+?>Season (\d+)</a>', season_html)
            if r:
                season_label = r.group(1)
                yield (season_label,season_html)
    
    def __get_url(self,url, headers={}, login=False):
        _1CH.log('Fetching URL: %s' % url)
        before = time.time()
        cookiejar = _1CH.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        net = Net()
        net.set_cookies(cookiejar)
        html = net.http_GET(url, headers=headers).content
        if login and not '<a href="/logout.php">[ Logout ]</a>' in html:
            if self.__login(url):
                html=net.http_GET(url, headers=headers).content
            else:
                html=None
                _1CH.log("Login failed for %s getting: %s" % (self.username,url))

        # addon.net tries to use page's Content Type to convert to unicode
        # if it fails (usually because the data in the page doesn't match the Content Type), then the page encoding is left as-is
        # This then tries again with w-1252 code page which is the least restrictive
        if not isinstance(html,unicode):
            html = unicode(html, 'windows-1252')
            
        after = time.time()
        _1CH.log('Url Fetch took: %.2f secs' % (after-before))
        return html
    
    def __get_cached_url(self, url, cache_limit=8):
        _1CH.log('Fetching Cached URL: %s' % url)
        before = time.time()
        
        html=utils.get_cached_url(url, cache_limit)
        if html:
            _1CH.log('Returning cached result for: %s' % (url))
            return html
        
        _1CH.log('No cached url found for: %s' % url)
        req = urllib2.Request(url)
    
        host = re.sub('http://', '', self.base_url)
        req.add_header('User-Agent', USER_AGENT)
        req.add_header('Host', host)
        req.add_header('Referer', self.base_url)
    
        try:
            response = urllib2.urlopen(req, timeout=10)
            body = response.read()
            if '<title>Are You a Robot?</title>' in body:
                _1CH.log('bot detection')
    
                #download the captcha image and save it to a file for use later
                captchaimgurl = 'http://'+host+'/CaptchaSecurityImages.php'
                captcha_save_path = xbmc.translatePath('special://userdata/addon_data/plugin.video.1channel/CaptchaSecurityImage.jpg')
                req = urllib2.Request(captchaimgurl)
                host = re.sub('http://', '', self.base_url)
                req.add_header('User-Agent', USER_AGENT)
                req.add_header('Host', host)
                req.add_header('Referer', self.base_url)
                response = urllib2.urlopen(req)
                the_img = response.read()
                with open(captcha_save_path,'wb') as f:
                    f.write(the_img)
    
                #now pop open dialog for input
                #TODO: make the size and loc configurable
                img = xbmcgui.ControlImage(550,15,240,100,captcha_save_path)
                wdlg = xbmcgui.WindowDialog()
                wdlg.addControl(img)
                wdlg.show()
                kb = xbmc.Keyboard('', 'Type the letters in the image', False)
                kb.doModal()
                capcode = kb.getText()
                if (kb.isConfirmed()):
                    userInput = kb.getText()
                if userInput != '':
                    #post back user string
                    wdlg.removeControl(img)    
                    capcode = kb.getText()
                    data = {'security_code':capcode,
                            'not_robot':'I\'m Human! I Swear!'}
                    data = urllib.urlencode(data)
                    roboturl = 'http://'+host+'/are_you_a_robot.php'
                    req = urllib2.Request(roboturl)
                    host = re.sub('http://', '', self.base_url)
                    req.add_header('User-Agent', USER_AGENT)
                    req.add_header('Host', host)
                    req.add_header('Referer', self.base_url)
                    response = urllib2.urlopen(req, data)
                    body = self.__get_url(url)
                   
                elif userInput == '':
                    dialog = xbmcgui.Dialog()
                    dialog.ok("Robot Check", "You must enter text in the image to continue")
                wdlg.close()
    
            body = unicode(body, 'windows-1252')
            parser = HTMLParser.HTMLParser()
            body = parser.unescape(body)
        except:
            dialog = xbmcgui.Dialog()
            dialog.ok("Connection failed", "Failed to connect to url", url)
            _1CH.log('Failed to connect to URL %s' % url)
            return ''
    
        response.close()
        
        utils.cache_url(url, body)
        after = time.time()
        _1CH.log('Cached Url Fetch took: %.2f secs' % (after-before))
        return body
    
    def __login(self,redirect):
        _1CH.log('Logging in for url %s' % redirect)
        url = self.base_url + '/login.php'
        net = Net()
        cookiejar = _1CH.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        host = re.sub('http://', '', self.base_url)
        headers = {'Referer': redirect, 'Origin': self.base_url, 'Host': host, 'User-Agent': USER_AGENT}
        form_data = {'username': self.username, 'password': self.password, 'remember': 'on', 'login_submit': 'Login'}
        html = net.http_POST(url, headers=headers, form_data=form_data).content
        if '<a href="/logout.php">[ Logout ]</a>' in html:
            net.save_cookies(cookiejar)
            return True
        else:
            return False

    def __multikeysort(self, items, columns, functions=None, getter=itemgetter):
        """Sort a list of dictionary objects or objects by multiple keys bidirectionally.
    
        Keyword Arguments:
        items -- A list of dictionary objects or objects
        columns -- A list of column names to sort by. Use -column to sort in descending order
        functions -- A Dictionary of Column Name -> Functions to normalize or process each column value
        getter -- Default "getter" if column function does not exist
                  operator.itemgetter for Dictionaries
                  operator.attrgetter for Objects
        """
        if not functions: functions = {}
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
