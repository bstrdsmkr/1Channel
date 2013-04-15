display_name = '1Channel'
#MUST be implemented. String that will be used to represent this provider to the user

required_addons = []
#MUST be implemented. A list of strings indicating which addons are required to
#be installed for this provider to be used.
#For example: required_addons = ['script.module.beautifulsoup', 'plugin.video.youtube']
#Currently, xbmc does not provide a way to require a specific version of an addon

tag = '1Ch'
#MUST be implemented. Unique 3 or 4 character string that will be used to
#denote content from this provider

def get_results(type,title,year,imdb,tvdb,season,episode):#MUST be implemented
	'''
	Should accept ALL of the following parameters:
	type: A string, either 'movie', 'tvshow', 'season', or 'episode'
	title: A string indicating the movie or tvshow title to find sources for
	year: A string indicating the release date of the desired movie, or premiere
		date of the desired tv show.
	imdb: A string or int of the imdb id of the movie or tvshow to find sources for
	tvdb: A string or int of the tvdb id of the movie or tvshow to find sources for
	season: A string or int indicating the season for which to return results.
		If season is supplied, but not episode, all results for that season
		should be returned
	episode: A string or int indicating the episode for which to return results
	
	If the source cannot filter results based one of these parameters, that
	parameter should be silently ignored.
	'''

	if   type=='movie'  : return _get_movies(title,year,imdb)
	elif type=='tvshow' : return _get_tvshows(title,year,imdb,tvdb)
	elif type=='season' : return _get_season(title,year,imdb,tvdb,season)
	elif type=='episode': return _get_episodes(title,year,imdb,tvsb,season,episode)
	#These are just example function names, the function name doesn't matter,
	#as long as it returns the expected result, which is described in these
	#example functions

def callback(params):
	'''
	MUST be implemented. This method allows you to call functions from your listitems.
	When Waldo is called with mode=CallModule, the callback() function of the module
	who's filename matches the receiver parameter will be called and passed all a dict
	of all the parameters.
	For example, to call this example function, you would call:
		plugin://plugin.video.waldo/?mode=CallModule&receiver=ExampleIndex
	'''
	addon.log('%s was called with the following parameters: %s' %(params.get('receiver',''), params))

def _get_movies(title,year,imdb):
	results = []
	result_1 = {}#Each result must be a dict with ALL of the following fields returned.
				 #If this source does not provide that particular piece of information,
				 #return '' (the empty string) in that field
	result_1['tag'] = tag
	result_1['provider_name'] = display_name
	result_1['title'] = 'Movie Result 1'
	result_1['function'] = result_1_function
	#Function (defined below) to be executed when the user selects the list
	#item created for this result

	result_1['kwargs'] = {'res_num':1, 'url':'www.example.com/result_1'}
	#A dict of argument:value pairs to be passed to the function indicated
	#by result_1['function'] above when the user selects the list item created
	#for this result

	result_1['rating'] = 0
	#A user rating of the result

	result_1['votes'] = ''
	#Number of votes cast in the above rating
	
	result_1['file_size'] = ''
	#int() indicating the file size of the result in MB

	result_1['duration'] = ''
	#Duration of this specific result (not the runtime of the movie)
	
	result_1['video_codec'] = ''
	#Shows the video codec of this result (common values: 3iv2, avc1,
	#div2, div3, divx, divx 4, dx50, flv, h264, microsoft, mp42, mp43,
	#mp4v, mpeg1video, mpeg2video, mpg4, rv40, svq1, svq3, theora, vp6f,
	#wmv2, wmv3, wvc1, xvid)

	result_1['video_codec'] = ''
	#Shows the resolution of this result (possible values: 480, 576, 540, 720, 1080)
	#Note that 540 usually means a widescreen format (around 960x540) while 576 means
	#PAL resolutions (normally 720x576), therefore 540 is actually better resolution
	#than 576.

	result_1['aspect_ratio'] = ''
	#Shows the aspect ratio of this result
	#(possible values: 1.33, 1.66, 1.78, 1.85, 2.20, 2.35)

	result_1['audio_codec'] = ''
	#Shows the audio codec of this result (common values: aac, ac3, cook, dca,
	#dtshd_hra, dtshd_ma, eac3, mp1, mp2, mp3, pcm_s16be, pcm_s16le, pcm_u8,
	#vorbis, wmapro, wmav2)
	
	result_1['audio_channels'] = ''
	#Shows the number of audio channels for this result
	#(possible values: 0, 1, 2, 4, 5, 6, 8)
	
	result_1['audio_languages'] = ''
	#Comma separated string of  audio languages available in this result
	#(ISO 639-2 three character codes, e.g. eng, epo, deu)
	
	result_1['subtitle_languages'] = ''
	#Comma separated string of subtitle languages available in this result
	#(ISO 639-2 three character codes, e.g. eng, epo, deu)
	#If subtitles are not provided within this file, return the string 'none'
	#If it is not known whether this file contains subtitles, return the
	#empty string ''

	results.append(result_1)
	return results

def result_1_function(res_num,url):
	print 'Result %s from 1Channel function was called. It\'s url is %s'%(res_num,url)

def result_2_function(res_num,url):
	print 'Result 2 from 1Channel function was called'

def result_3_function(res_num,url):
	print 'Result 3 from 1Channel function was called'