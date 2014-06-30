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
import sys
import xbmc
import os
import urllib
import time
from addon.common.addon import Addon

_1CH = Addon('plugin.video.1channel', sys.argv)

class DB_Connection():
    global db_lib
    def __init__(self):
        try:
            self.dbname = _1CH.get_setting('db_name')
            self.username = _1CH.get_setting('db_user')
            self.password = _1CH.get_setting('db_pass')
            self.address = _1CH.get_setting('db_address')
            if _1CH.get_setting('use_remote_db') == 'true' and \
                            self.db_address is not None and \
                            self.username is not None and \
                            self.password is not None and \
                            self.db_name is not None:
                import mysql.connector as db_lib
        
                _1CH.log('Loading MySQL as DB engine')
                self.db_type = 'mysql'
            else:
                _1CH.log('MySQL not enabled or not setup correctly')
                raise ValueError('MySQL not enabled or not setup correctly')
        except:
            try:
                from sqlite3 import dbapi2 as db_lib
                _1CH.log('Loading sqlite3 as DB engine')
            except:
                from pysqlite2 import dbapi2 as db_lib
                _1CH.log('pysqlite2 as DB engine')
            self.db_type = 'sqlite'
            db_dir = xbmc.translatePath("special://database")
            self.db_path = os.path.join(db_dir, 'onechannelcache.db')
        self.db=self.__connect_to_db()
    
    def __connect_to_db(self):
        if not self.db:
            if self.db_type == 'mysql':
                self.db = db_lib.connect(database=self.db_name, user=self.username, password=self.password, host=self.db_address, buffered=True)
            else:
                self.db = db_lib.connect(self.db_path)
                self.db.text_factory = str

    def flush_cache(self):
        sql = 'DELETE FROM url_cache'
        cur = self.db.cursor()
        cur.execute(sql)
        self.db.commit()

    # return the bookmark for the requested url or None if not found
    def get_bookmark(self,url):
        if not url: return None
        cur = self.db.cursor()
        sql=self.__format("SELECT resumepoint FROM new_bkmark where url=?")
        cur.execute(sql, (url,))
        bookmark = cur.fetchone()
        if bookmark:
            return bookmark[0]
        else:
            return None

    # return true if bookmark exists
    def bookmark_exists(self, url):
        return self.get_bookmark(url) != None
    
    def set_bookmark(self, url,offset):
        if not url: return
        sql = self.__format("REPLACE INTO new_bkmark (url, resumepoint) VALUES(?,?)")
        self.db.execute(sql,(url,offset))
        self.db.commit()
        
    def clear_bookmark(self, url):
        if not url: return
        sql = self._format("DELETE FROM new_bkmark WHERE url=?")
        self.db.execute(sql,(url,))
        self.db.commit()

    def get_all_favorites(self, section):
        sql = self.__format('SELECT type, name, url, year FROM favorites')
        if section: sql = sql + self.__format(" WHERE type = ? ORDER BY NAME")
        cur = self.db.cursor()
        cur.execute(sql, (section,))
        favs = cur.fetchall()
        cur.close()
        return favs
    
    def get_favorites_count(self, section):
        sql = self.__format('SELECT count(*) FROM favorites')
        if section: sql = sql + self.__format(" WHERE type = ?")
        cur = self.db.cursor()
        count=cur.execute(sql).fetchall()
        cur.close()
        return count
    
    def save_favorite(self, fav_type, name, url, year):
        sql = self.__format('INSERT INTO favorites (type, name, url, year) VALUES (%s,%s,%s,%s)')
        cursor = self.db.cursor()
        try:
            title = urllib.unquote_plus(unicode(name, 'latin1'))
            cursor.execute(sql, (fav_type, title, url, year))
            self.db.commit()
        except db_lib.IntegrityError:
            raise
    
    def delete_favorites(self, urls):
        url_string=', '.join('%s' for _ in urls)
        sql = self.__format('DELETE FROM favorites WHERE url in ('+url_string+')')
        cursor = self.db.cursor()
        cursor.execute(sql, (urls))
        self.db.commit()
        
    def delete_favorite(self, url):
        self.delete_favorites([url])

    def get_all_subscriptions(self, day=None):
        sql=self.__format('SELECT url, title, img, year, imdbnum FROM subscriptions')
        if day: sql += self.__format(' WHERE day = "%s"')
        cur = self.db.cursor()
        cur.execute(sql)
        rows=cur.fetchall()
        cur.close()
        return rows
    
    def add_subscription(self, url, title, img, year, imdbnum, day):
        sql = self.__format('INSERT INTO subscriptions (url, title, img, year, imdbnum, day) VALUES (?,?,?,?,?,?)')
        cur = self.db.cursor()
        try: 
            cur.execute(sql, (url, title, img, year, imdbnum, day)) #cur.execute(sql, (url, title, img, year, imdbnum))
            self.db.commit()

        except: ## Note: Temp-Fix for Adding the Extra COLUMN to the SQL TABLE ##
            try: 
                cur.execute('ALTER TABLE subscriptions ADD day TEXT')
                cur.execute(sql, (url, title, img, year, imdbnum, day))
                self.db.commit()
            except:
                raise
    def delete_subscription(self, url):
        sql = self.__format('DELETE FROM subscriptions WHERE url=?')
        cur = self.db.cursor()
        cur.execute(sql, (url))
        self.db.commit()

    def cache_url(self,url,body):
        now = time.time()
        cur = self.db.cursor()
        sql = self.__format("REPLACE INTO url_cache (url,response,timestamp) VALUES(?, ?, ?)")
        cur.execute(sql, (url, body, now))
        self.db.commit()
    
    def get_cached_url(self, url, cache_limit=8):
        html=''
        db = connect_db()
        cur = db.cursor()
        now = time.time()
        limit = 60 * 60 * cache_limit
        cur.execute('SELECT * FROM url_cache WHERE url = "%s"' % url)
        cached = cur.fetchone()
        if cached:
            created = float(cached[2])
            age = now - created
            if age < limit:
                html=cached[1]
    
        db.close()
        return html
    
    def cache_season(self, season_num,season_html):
        db = connect_db()
        if DB == 'mysql':
            sql = 'INSERT INTO seasons(season,contents) VALUES(%s,%s) ON DUPLICATE KEY UPDATE contents = VALUES(contents)'
        else:
            sql = 'INSERT or REPLACE into seasons (season,contents) VALUES(?,?)'
    
        if not isinstance(season_html, unicode):
            season_html = unicode(season_html, 'windows-1252')
        cur = db.cursor()
        cur.execute(sql, (season_num, season_html))
        cur.close()
        db.commit()
        db.close()
    
    def get_cached_season(self, season_num):
        sql = 'SELECT contents FROM seasons WHERE season=?'
        db = connect_db()
        if DB == 'mysql':
            sql = sql.replace('?', '%s')
        cur = db.cursor()
        cur.execute(sql, (season_num,))
        season_html = cur.fetchone()[0]
        db.close()
        return season_html

    def execute_sql(self, sql):
        self.db.execute(sql)
        self.db.commit()

    # apply formatting changes to make sql work with a particular db driver
    def __format(self, sql):
        if self.db_type =='mysql':
            sql = sql.replace('?', '%s')
            
        if self.db_type == 'sqlite' :
            if sql.left(6)=='REPLACE':
                sql = 'INSERT OR ' + sql
            
