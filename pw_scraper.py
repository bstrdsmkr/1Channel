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
from addon.common.net import Net
from addon.common.addon import Addon

USER_AGENT = ("User-Agent:Mozilla/5.0 (Windows NT 6.2; WOW64)"
              "AppleWebKit/537.17 (KHTML, like Gecko)"
              "Chrome/24.0.1312.56")

_1CH = Addon('plugin.video.1channel', sys.argv)
ADDON_PATH = _1CH.get_path()
ICON_PATH = os.path.join(ADDON_PATH, 'icon.png')

class PW_Scraper():
    def __init__(self, base_url, username, password):
        self.base_url=base_url
        self.username=username
        self.password=password
        self.res_pages=-1
        pass
    
    def add_favorite(self,url):
        _1CH.log('Saving favorite to website')
        id_num = re.search(r'.+(?:watch|tv)-([\d]+)-', url)
        if id_num:
            save_url = "%s/addtofavs.php?id=%s&whattodo=add"
            save_url = save_url % (self.base_url, id_num.group(1))
            _1CH.log('Save URL: %s' %(save_url))
            html = self.__get_url(save_url,True)
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
            self.__get_url(del_url,True)
    
    def get_favorities(self, section):
        url = '/profile.php?user=%s&fav&show=%s'
        url = self.base_url + url % (self.username, section)
        html=self.__get_url(url)
        pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{1,4})?\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a></td>.+?class="favs_deleted"><a href=\'(.+?)\' ref=\'delete_fav\''''
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
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
        return

    def migrate_favorites(self):
        pass
    
    def get_sources(self):
        pass
    
    def search(self):
        pass
    
    def search_advanced(self):
        pass
    
    def search_desc(self):
        pass
    
    def get_filtered_results(self, section, genre, letter, sort, page):
        pageurl = self.base_url + '/?'
        if section == 'tv': pageurl += 'tv'
        if genre:  pageurl += '&genre=' + genre
        if letter:  pageurl += '&letter=' + letter
        if sort:     pageurl += '&sort=' + sort
        if page:   pageurl += '&page=%s' % page
    
        html = self.__get_cached_url(pageurl)
    
        r = re.search('number_movies_result">([0-9,]+)', html)
        if r:
            total = int(r.group(1).replace(',', ''))
        else:
            total = 0
        self.res_pages = total / 24
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
        return
    
    def get_last_res_pages(self):
        return self.res_pages

    def get_season_list(self):
        pass
    
    def get_episode_list(self):
        pass
       
    def __get_url(self,url,login=False):
        cookiejar = _1CH.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        net = Net()
        net.set_cookies(cookiejar)
        html = net.http_GET(url).content
        if login and not '<a href="/logout.php">[ Logout ]</a>' in html:
            if self.__login(url):
                return net.http_GET(url).content
            else:
                _1CH.log("Login failed for %s getting: %s" (self.username,url))
        else:
            return html
    
    def __get_cached_url(self, url, cache_limit=8):
        #_1CH.log('Fetching URL: %s' % url)
        db = utils.connect_db()
        cur = db.cursor()
        now = time.time()
        limit = 60 * 60 * cache_limit
        cur.execute('SELECT * FROM url_cache WHERE url = "%s"' % url)
        cached = cur.fetchone()
        if cached:
            created = float(cached[2])
            age = now - created
            if age < limit:
                _1CH.log('Returning cached result for %s' % url)
                db.close()
                return cached[1]
            else:
                _1CH.log('Cache too old. Requesting from internet')
        else:
            _1CH.log('No cached response. Requesting from internet')
    
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
    
            body = unicode(body, 'iso-8859-1')
            parser = HTMLParser.HTMLParser()
            body = parser.unescape(body)
        except:
            dialog = xbmcgui.Dialog()
            dialog.ok("Connection failed", "Failed to connect to url", url)
            _1CH.log('Failed to connect to URL %s' % url)
            return ''
    
        response.close()
        
        utils.cache_url(url, body, now)
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
