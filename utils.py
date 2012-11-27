import sys
import re

from t0mm0.common.addon import Addon

addon = Addon('plugin.video.1channel', sys.argv)

def format_label_tvshow(info):
	if 'premiered' in info:
		year = info['premiered'][:4]
	else: year = ''
	title = info['title']
	# if not isinstance(title, unicode):
		# print 'Converting unicode title'
		# title = title.decode('utf-8')
	label = addon.get_setting('format-tvshow')
	label = label.replace('{t}', title)
	label = label.replace('{y}', year)
	label = label.replace('{ft}', format_tvshow_title(title))
	label = label.replace('{fy}', format_tvshow_year(year))
	return label

def format_tvshow_title(title):
	title_format = addon.get_setting('format-tvshow-title')
	label = re.sub('\{t\}', title, title_format)
	return label

def format_tvshow_year(year):
	if not year: return ''
	year_format = addon.get_setting('format-tvshow-year')
	label = re.sub('\{y\}', year, year_format)
	return label

def format_tvshow_episode(info):
	episode_format = addon.get_setting('format-tvshow-episode')
	label = re.sub('\{s\}', str(info['season']), episode_format)
	label = re.sub('\{e\}', str(info['episode']), label)
	label = re.sub('\{t\}', info['title'], label)
	label = re.sub('\{st\}', info['TVShowTitle'], label)
	return label

def format_label_sub(info):
	sub_format = addon.get_setting('format-tvshow-sub')
	label = format_label_tvshow(info)
	formatted_label = re.sub('\{L\}', label, sub_format)
	return formatted_label

def format_label_movie(info):
	label = addon.get_setting('format-movie')
	label = re.sub('\{t\}', info['title'], label)
	label = re.sub('\{y\}', str(info['year']), label)
	label = re.sub('\{ft\}', format_movie_title(info['title']), label)
	label = re.sub('\{fy\}', format_movie_year(str(info['year'])), label)
	return label

def format_movie_title(title):
	title_format = addon.get_setting('format-movie-title')
	label = re.sub('\{t\}', title, title_format)
	return label

def format_movie_year(year):
	if not year: return ''
	year_format = addon.get_setting('format-movie-year')
	label = re.sub('\{y\}', year, year_format)
	return label

def format_label_source(info):
	label = addon.get_setting('format-source')
	label = re.sub('\{q\}', info['quality'], label)
	label = re.sub('\{h\}', info['host'], label)
	label = re.sub('\{v\}', str(info['views']), label)
	if info['multi-part']: parts = 'part 1'
	else: parts = ''
	label = re.sub('\{p\}', parts, label)
	if info['verified']: label = format_label_source_verified(label)
	return label

def format_label_source_verified(label):
	ver_format = addon.get_setting('format-source-verified')
	formatted_label = re.sub('\{L\}', label, ver_format)
	return formatted_label

def format_label_source_parts(info, part_num):
	label = addon.get_setting('format-source-parts')
	label = re.sub('\{q\}', info['quality'], label)
	label = re.sub('\{h\}', info['host'], label)
	label = re.sub('\{v\}', str(info['views']), label)
	parts = 'part %s' %part_num
	label = re.sub('\{p\}', parts, label)
	if info['verified']: label = format_label_source_verified(label)
	return label