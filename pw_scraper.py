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
from addon.common.addon import Addon

USER_AGENT = ("User-Agent:Mozilla/5.0 (Windows NT 6.2; WOW64)"
              "AppleWebKit/537.17 (KHTML, like Gecko)"
              "Chrome/24.0.1312.56")

_1CH = Addon('plugin.video.1channel', sys.argv)

class PW_Scraper():
    def __init__(self, base_url):
        self.base_url=base_url
        pass
    
    def add_favorite(self):
        pass
    
    def delete_favorite(self):
        pass
    
    def get_favorities(self):
        user = _1CH.get_setting('username')
        url = '/profile.php?user=%s&fav&show=%s'
        url = BASE_URL + url % (user, section)
        cookiejar = _1CH.get_profile()
        cookiejar = os.path.join(cookiejar, 'cookies')
        net = Net()
        net.set_cookies(cookiejar)
        html = net.http_GET(url).content
        if not '<a href="/logout.php">[ Logout ]</a>' in html:
        html = utils.login_and_retry(url)
        pattern = '''<div class="index_item"> <a href="(.+?)"><img src="(.+?(\d{1,4})?\.jpg)" width="150" border="0">.+?<td align="center"><a href=".+?">(.+?)</a></td>.+?class="favs_deleted"><a href=\'(.+?)\' ref=\'delete_fav\''''
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        for item in regex.finditer(html):
            link, img, year, title, delete = item.groups()
            if not year or len(year) != 4: year = ''

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
    
    def get_filtered_results(self):
        pass
    
    def get_season_list(self):
        pass
    
    def get_episode_list(self):
        pass
       
    def __get_url(self, url, cache_limit=8):
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