# Links and info about metacontainers.
# Update this file to update the containers.

# Size is in MB

#return dictionary of strings and integers
def list():
	containers = {} 

	#date updated
	containers['date'] = 'Dec 2011'

	#--- Database Meta Container ---#
	#containers['Container_Name.zip'] = (url,size)
	containers['MetaPack-tvshow-A-G.zip'] = (url,size)
	containers['MetaPack-tvshow-H-N.zip'] = (url,size)
	containers['MetaPack-tvshow-O-U.zip'] = (url,size)
	containers['MetaPack-tvshow-V-#123.zip'] = (url,size)

	containers['MetaPack-movie-A-G.zip'] = (url,size)
	containers['MetaPack-movie-H-N.zip'] = (url,size)
	containers['MetaPack-movie-O-U.zip'] = (url,size)
	containers['MetaPack-movie-V-#123.zip'] = (url,size)
	return containers
