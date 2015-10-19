# -*- coding: utf-8 -*-
import urllib2
from urllib2 import HTTPError
import re
import os

import json
import time
from datetime import date, datetime
import sys
import math

import xbmcplugin
import CommonFunctions
import xbmcutil as xbmcUtil
from bs4 import BeautifulSoup
import xbmcgui

import SimpleDownloader as downloader

dbg = True
downloader.dbg = True
import string

common = CommonFunctions
common.plugin = "plugin.video.ruutu"

USER_AGENT = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.3) Gecko/2008092417 Firefox/3.0.3'

# sets default encoding to utf-8
reload(sys)
sys.setdefaultencoding('utf8')

HIDE_PREMIUM_CONTENT = True

REMOTE_DBG = False

# append pydev remote debugger
if REMOTE_DBG:
    # Make pydev debugger works for auto reload.
    # Note pydevd module need to be copied in XBMC\system\python\Lib\pysrc
    try:
        sys.path.append('/home/jz/.eclipse/org.eclipse.platform_3.8_155965261/plugins/org.python.pydev_4.4.0.201510052309/pysrc')
        import pydevd
        #import pysrc.pydevd as pydevd # with the addon script.module.pydevd, only use `import pydevd`
    # stdoutToServer and stderrToServer redirect stdout and stderr to eclipse console
        pydevd.settrace('localhost', port=1234, stdoutToServer=True, stderrToServer=True)
    except ImportError:
        sys.stderr.write("Error: " +
            "You must add org.python.pydev.debug.pysrc to your PYTHONPATH.")
        sys.exit(1)

def getEpisodesLink(seriesId):
	episodesLinkTemplate = "http://www.ruutu.fi/component/690/update?series=SERIESID&media_type=video_episode&orderby=sequence&order_direction=desc"
	return episodesLinkTemplate.replace('SERIESID', seriesId)

def checkLinkOffset(link, pageSize, pg):
	if pg >= 2:
		# offset the listing by pageSize
		link += "&offset=%s" % str((pg-1)*pageSize)

def downloadVideo(url, title):
	def getFilename(title, url):
		template = "TITLE_UNIQUEID.mp4"
		valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
		# picks the uniqueID from the video filename
		urlRegex = r".*\/video/\d{1,4}/carbon_(\d{1,8})_(?:\d{4})_none.mp4"
		filename = template.replace("TITLE", ''.join(c for c in title if c in valid_chars))
		filename = filename.replace("UNIQUEID", re.match(urlRegex, url).group(1) if re.match(urlRegex, url) else '')
		return filename
	
	downloadPath = ruutu.addon.getSetting('download-path')
	if downloadPath is None or downloadPath == '':
		return
	downloadPath += url.split('/')[-2]
	if not os.path.exists(downloadPath):
		os.makedirs(downloadPath)
	
	filename = getFilename(title, url)
	params = {"url": url, "download_path": downloadPath, "title": title}
	xbmc.log(url + " " + filename + "   " + str(params))
	dw = downloader.SimpleDownloader()
	dw.download(filename, params)
	
def scrapInline(url, bitrate, pg=1):
	def getContent(bs):
		div = bs.find('div', {'data-content-id': True})
		if not div:
			return None
		else:
			isPremium = div.find('div', {'class': 'ruutuplus-text' }) is not None
			if HIDE_PREMIUM_CONTENT and isPremium:
				return None
			videoId = div.get('data-content-id')
			return getVideoDetails(videoId, bitrate, True)	
		
	# 	def getContentWithoutXMLQuery(bs):
	# 		div = bs.find('div', {'data-content-id': True})
	# 		if not div:
	# 			return None
	# 		else:
	# 			isPremium = div.find('div', {'class': 'ruutuplus-text' }) is not None
	# 			if isPremium:
	# 				return None
	# 			videoId = div.get('data-content-id')
	# 			preTitle = div.find('div', {'class': 'thumbnail-pretitle'}).text
	# 			title = div.find('div', {'class': 'thumbnail-title'}).text
	# 			details = div.find('div', {'class': 'hoverbox-details'}).text.strip()
	# 			imgUrl = div.find('img', attrs={'data-img_src_1': True}).get('data-img_src_3', '')
	# 			timeLeft = div.find('div', {'class': 'time-left'}).text

			
		
	resultObj = scrapJSON(url)
	items = resultObj.get('items', [])
	results = []
	for item in items:
		bs = BeautifulSoup(item, "html.parser")
		content = getContent(bs)
		if content:
			results.append(content)
	return results


def getVideoDetails(videoId, bitrate, isCategoryFetch=False):
	def low(name):
		return name.lower()

	def getModifiedVideoUrl(url):
		return url.replace("_1000_", "_" + str(bitrate) + "_")
	
	def getTitle(description, name):
		if not name or len(name) == 0:
			# first sentence fom description is better than nothing
			return description.split(".")[0]
		else:
			return name
# 		try:
# 			if isCategoryFetch:
# 				return name
# 			# syntax goes: "Kausi 2. Jakso 6/10. Episode name. Rest of description..."
# 			return description.split(".")[2]
# 		except Exception as e:
# 			return name

	def isPremium(xmlsoup):
		return xmlsoup.find(low('PassthroughVariables')).find('variable', {'name': 'paid'}) == '1'
	
	def getDuration(xmlsoup):
		runtimeEl = xmlsoup.find(low('Runtime'))
		durationEl = xmlsoup.find(low('Duration'))
		duration = None
		
		if runtimeEl and runtimeEl.text:
			duration = runtimeEl.text or '0'
		elif durationEl and durationEl.text:
			duration = durationEl.text or '0'
		return duration
	
	def getSeasonAndEpisodeNum(episodeCode):
		retDict = {}
		if episodeCode == 'NA':
			retDict['episode'] = None
			retDict['season'] = None
		else:
			epRegex1 = r'S(\d\d)E(\d\d)' # example: S04E12
			epRegex2 = r'S(\d{4})E(\d{1,4})' # example: S2015E291
			match1 = re.match(epRegex1, episodeCode)
			match2 = re.match(epRegex2, episodeCode)
			if match1:
				retDict['season'] = match1.group(1)
				retDict['episode'] = match1.group(2)
			elif match2:
				retDict['season'] = match2.group(1)
				retDict['episode'] = match2.group(2)
		return retDict
	
	def getPublishedTime(startTime):
		format = '%d.%m.%Y %H:%M'
		publishedTs = None
		# to date object
		# workaround for bug http://forum.kodi.tv/showthread.php?tid=112916
		try:
			publishedTs = datetime.strptime(startTime, format) if program.get('start_time') else None
		except TypeError:
			publishedTs = datetime(*(time.strptime(startTime, format)[0:6]))
		finally:
			return publishedTs
	
	try:
		infoUrlTemplate = "http://gatling.nelonenmedia.fi/media-xml-cache?id=VIDEOID"
		#videoPageTemplate = "http://www.ruutu.fi/video/VIDEOID"
		
		resDict = {}
	
		infoUrl = infoUrlTemplate.replace('VIDEOID', videoId)
		#videoPage = videoPageTemplate.replace('VIDEOID', videoId)
		
		# start fetching the XML file
		xbmc.log(infoUrl)
		req = urllib2.Request(infoUrl)
		req.add_header('User-Agent', USER_AGENT)
		response = urllib2.urlopen(req)
		content = response.read()
		response.close()
		
		# workaround, cannot get xml parser to work -> html works but is all lowercase
		xmlsoup = BeautifulSoup(content, "html.parser") #, 'lxml-xml')
		
		# no listing of premium content:
		if HIDE_PREMIUM_CONTENT and isPremium(xmlsoup):
			return None
	
		program = xmlsoup.find(low('Behavior')).find(low('Program'))
		# extract the episode name for the listing:
		episodeCode = xmlsoup.find(low('PassthroughVariables')).find('variable', {'name': 'episode_code'}).get('value')
		epInfo = getSeasonAndEpisodeNum(episodeCode)
		link = getModifiedVideoUrl(xmlsoup.find(low('HTTPMediaFile')).text)
		image = xmlsoup.find(low('Startpicture')).get('href', '') if xmlsoup.find(low('Startpicture')) else ''
		duration = getDuration(xmlsoup)
		publishedTs = getPublishedTime(program.get('start_time'))
		availabilityText = 'available-text'
		available = 'available'
		desc = program.get('description', '')
		programName = program.get('program_name', '')
		title = getTitle(desc, programName)
		
		resDict = {'title': title, 'seasonNum': epInfo.get('season'), 'episodeNum': epInfo.get('episode'), 'link': link, 'image': image, 'duration': duration,
					'published-ts': publishedTs, 'available-text': availabilityText, 'available': available, 'desc': desc, 'details': programName}
		
		return resDict
	except Exception as e:
		xbmc.log("Error at fetching videoId = " + videoId + " -> skipped and exception handled.")
		return None


def scrapSeries(url, bitrate, pg=1):
	def getContent(bs):
		el = bs.find('div', { 'data-video-id': True })
		if el:
			# only need the videoid from the cache listing
			videoId = el.get('data-video-id')
			return getVideoDetails(videoId, bitrate)
		else:
			return None
	
# 	try:
	resultObj = scrapJSON(url)
	episodes = resultObj.get('items', [])
	results = []
	for episode in episodes:
		bs = BeautifulSoup(episode, "html.parser")
		isPremiumEpisode = bs.find('span', {'class': 'premium'}) is not None
		if HIDE_PREMIUM_CONTENT and isPremiumEpisode:
			pass
		else:
			content = getContent(bs)
			if content:
				results.append(content)
	return results
# 	except Exception as e:
# 		return []


def trimFromExtraSpaces(text):
	try:
		text = text.strip().replace('\n', '')
	except:
		text = ""
	while "  " in text: text = text.replace('  ', ' ')
	return text

def scrapJSON(url):
	req = urllib2.Request(url)
	req.add_header('User-Agent', USER_AGENT)
	try:
		response = urllib2.urlopen(req)
		content = response.read()
		response.close()
		jsonObj = json.loads(content)
		return jsonObj
	except urllib2.HTTPError:
		return []


def scrapPrograms():
    url = 'http://www.ruutu.fi/ruutu_search/published-series'
    series = scrapJSON(url)
    retLinks = []
    # for getting only the series ID
    regex = r'\/series\/'
    for serie in series:
        seriesId = re.sub(regex, '', serie.get('value'))
        retLinks.append({ 'name': serie.get('label'), 
                         'seriesId': seriesId })
    return retLinks

def formatDate(dt):
	delta = date.today() - dt.date()
	if delta.days == 0: return lang(30004)
	if delta.days == 1: return lang(30010)
	if 1 < delta.days < 5: return dt.strftime('%A %d.%m.%Y')
	return dt.strftime('%d.%m.%Y')


class RuutuAddon(xbmcUtil.ViewAddonAbstract):
	ADDON_ID = 'plugin.video.ruutu'

	def __init__(self):
		def getBitrate(value):
			d = { '720p': '3000',
				'576p': '1800',
				'432p': '1000',
				'288p': '600'
				}
			return d.get(value)
		xbmcUtil.ViewAddonAbstract.__init__(self)
		self.REMOVE = u'[COLOR red][B]•[/B][/COLOR] %s' % self.lang(30019)
		self.FAVOURITE = '[COLOR yellow][B]•[/B][/COLOR] %s'
		self.EXPIRES_DAYS = u'[COLOR brown]%d' + self.lang(30003) + '[/COLOR] %s'
		self.EXPIRES_HOURS = u'[COLOR red]%d' + self.lang(30002) + '[/COLOR] %s'
		self.GROUP_FORMAT = u'   [COLOR blue]%s[/COLOR]'
		self.NEXT = '[COLOR blue]   >>> %s  >>>[/COLOR]' % self.lang(33078)
		self.HIGHLIGHTED = "[COLOR green]  >> %s[/COLOR]"

		self.addHandler(None, self.handleMain)
		self.addHandler('inline', self.handleInline)
		self.addHandler('category', self.handleCategory)
		self.addHandler('serie', self.handleSeries)
		self.addHandler('programs', self.handlePrograms)
		self.addHandler('search', self.handleSearch)
		self.favourites = {}
		self.initFavourites()
		self.enabledDownload = self.addon.getSetting("enable-download") == 'true'
		self.bitrate = getBitrate(self.addon.getSetting("bitrate"))


	def handleMain(self, pg, args):
		# --- All programs:
		self.addViewLink(self.HIGHLIGHTED % self.lang(30020), 'programs', 1)
		
		self.addViewLink(self.HIGHLIGHTED % self.lang(30021), 'search', 1, { "pg-size": 1000 })
		
		# --- Time:
		# newest episodes:
		self.addViewLink(self.lang(30030), 'inline', 1, {'link': 'http://www.ruutu.fi/component/1567/update?media_type=video_episode&orderby=&publishing_channel=nelonenmedia&order_direction=desc&limit=30', 'grouping': True, 'pg-size': 15})
		# most watched during one week:
		self.addViewLink(self.lang(30031), 'inline', 1,
						 {'link': 'http://www.ruutu.fi/component/527/update?media_type=video_episode&orderby=popularity_weekly&publishing_channel=nelonenmedia&order_direction=desc&limit=30', 'pg-size': 15})
		
		# --- Category:
		# Drama
		self.addViewLink(self.lang(30050), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/218/update?has_episode_videos=1&internalclass=4%2C5&orderby=ruutu&order_direction=desc&internalsubclass=2%2C3&limit=100', 'grouping': True, 'pg-size': 10})

		# Thrillers
		self.addViewLink(self.lang(30051), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/219/update?has_episode_videos=1&internalclass=4%2C5&orderby=ruutu&order_direction=desc&internalsubclass=1&limit=100', 'grouping': True, 'pg-size': 10})
		
		# Domestic
		self.addViewLink(self.lang(30052), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/536/update?has_episode_videos=1&internalclass=4&orderby=ruutu&order_direction=desc&internalsubclass=4%2C5%2C7&limit=100', 'grouping': True, 'pg-size': 10})
		
		# Foreign
		self.addViewLink(self.lang(30053), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/555/update?has_episode_videos=1&internalclass=5&orderby=ruutu&order_direction=desc&internalsubclass=4%2C5%2C7&limit=100', 'grouping': True, 'pg-size': 10})

		# Entertainment & Music
		self.addViewLink(self.lang(30054), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/557/update?has_episode_videos=1&internalclass=4%2C5&orderby=ruutu&order_direction=desc&internalsubclass=5&limit=100', 'grouping': True, 'pg-size': 10})

		# Talkshows
		self.addViewLink(self.lang(30055), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/558/update?has_episode_videos=1&internalclass=4%2C5&orderby=ruutu&order_direction=desc&internalsubclass=7&limit=100', 'grouping': True, 'pg-size': 10})

		# Reality
		self.addViewLink(self.lang(30056), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/544/update?has_episode_videos=1&internalclass=4%2C5&orderby=ruutu&order_direction=desc&internalsubclass=8&limit=100', 'grouping': True, 'pg-size': 10})
		
		# Lifestyle
		self.addViewLink(self.lang(30057), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/537/update?has_episode_videos=1&internalclass=4%2C5&orderby=ruutu&order_direction=desc&internalsubclass=6%2C9&limit=100', 'grouping': True, 'pg-size': 10})

		# Domestic movies
		self.addViewLink(self.lang(30058), 'inline', 1,
						 {'link': 'http://www.ruutu.fi/component/539/update?internalclass=6&orderby=created&order_direction=desc&internalsubclass=1&limit=100', 'grouping': True, 'pg-size': 10})
		
		# Foreign movies
		self.addViewLink(self.lang(30059), 'inline', 1,
						 {'link': 'http://www.ruutu.fi/component/606/update?internalclass=6&orderby=created&order_direction=desc&internalsubclass=2&limit=100', 'grouping': True, 'pg-size': 10})

		# Documents
		self.addViewLink(self.lang(30060), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/538/update?has_episode_videos=1&internalclass=2&orderby=ruutu&order_direction=desc&internalsubclass=1&limit=100', 'grouping': True, 'pg-size': 10})

		# News
		self.addViewLink(self.lang(30061), 'inline', 1,
						 {'link': 'http://www.ruutu.fi/component/214/update?series=1377550&media_type=video_clip&orderby=popularity_weekly&order_direction=desc&limit=100', 'grouping': True, 'pg-size': 10})

		# Weather
		self.addViewLink(self.lang(30062), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/215/update?has_episode_videos=1&internalclass=4%2C5&orderby=ruutu&order_direction=desc&internalsubclass=1&limit=100', 'grouping': True, 'pg-size': 10})
		

		# Children
		self.addViewLink(self.lang(30063), 'category', 1,
						 {'link': 'http://www.ruutu.fi/component/310/update?has_videos=1&internalclass=7&orderby=ruutu&order_direction=desc&limit=100', 'grouping': True, 'pg-size': 10})
		
		# Children's movies
		self.addViewLink(self.lang(30064), 'inline', 1,
						 {'link': 'http://www.ruutu.fi/component/584/update?media_type=video_episode&internalclass=6&themes=18&orderby=created&order_direction=desc&limit=100', 'grouping': True, 'pg-size': 10})

		
		for title, link in self.favourites.items():
			t = title
			cm = [(self.createContextMenuAction(self.REMOVE, 'removeFav', {'name': t}) )]
			self.addViewLink(self.FAVOURITE % t, 'serie', 1, {'link': link, 'pg-size': 10}, cm)

	def initFavourites(self):
		fav = self.addon.getSetting("fav")
		if fav:
			try:
				favList = eval(fav)
				for title, link in favList.items():
					self.favourites[title] = link
			except:
				pass


	def isFavourite(self, title):
		return title in self.favourites

	@staticmethod
	def getPageQuery(pg):
		return str(pg - 1) if pg > 0    else ''
	
	def handleSearch(self, pg, args):
		def getContent(video, bitrate):
			videoId = video.get('data-content-id')
			isPremium = video.find('div', {'class': 'ruutuplus-text' }) is not None
			if HIDE_PREMIUM_CONTENT and isPremium:
				return None
			return getVideoDetails(videoId, bitrate, True)

		def scrapSearch(bs, bitrate, pg):
			videos = bs.findAll('div', attrs={ 'data-content-type': 'video', 'data-content-id': True })
			results = []
			for index, video in enumerate(videos):
				content = getContent(video, bitrate)
				if content:
					results.append(content)
				if index >= 30:
					# safeguard to limit too long searches
					break
			return results
				
				
		searchUrlTemplate = 'http://www.ruutu.fi/ruutu_search/search-content-freetext/SEARCH_STRING'
		keyboard = xbmc.Keyboard()
		keyboard.setHeading(self.lang(30080))
		keyboard.doModal()
		if (keyboard.isConfirmed() and keyboard.getText() != ''):
			query = keyboard.getText()
			url = searchUrlTemplate.replace('SEARCH_STRING', query)
			resultList = scrapJSON(url)
			content = resultList[1].get('data')
			bs = BeautifulSoup(content, 'html.parser')
			self.listItems(scrapSearch(bs, self.bitrate, pg), pg, args, 'inline', True)
	
	def handleCategory(self, pg, args):
		def scrapCategory(url, pg=1):
			xbmc.log(url)
			req = urllib2.Request(url)
			req.add_header('User-Agent', USER_AGENT)
			response = urllib2.urlopen(req)
			content = response.read()
			response.close()
		
			resultObj = scrapJSON(url)
			seriesTagList = resultObj.get('items', [])
		
			for seriesTag in seriesTagList:
				#try:
				bs = BeautifulSoup(seriesTag, 'html.parser')
				isPremium = bs.find('div', {'class': 'ruutuplus-text'}) is not None
				if HIDE_PREMIUM_CONTENT and isPremium:
					continue
		
				seriesId = bs.find('div', attrs={ 'data-content-id': True }).get('data-content-id')
				episodesLink = getEpisodesLink(seriesId)
				title = bs.find('h4', {'class': 'thumbnail-title'}).text
				# note the change in handler name
				self.addViewLink(title, 'serie', 1, {'link': episodesLink, 'pg-size': 100})
				#except:
				#	pass
		
		link = args['link'] if 'link' in args else ''
		if link != '':
			self.listItems(scrapCategory(link, pg), pg, args, 'category', False)

	def handleInline(self, pg, args):
		link = args.get('link', '')
		pageSize = args.get('pg-size', 15)
		#checkLinkOffset(link, pageSize, pg)
		if link != '':
			self.listItems(scrapInline(link, self.bitrate, pg), pg, args, 'time', True)

	def handleSeries(self, pg, args):
		link = args['link'] if 'link' in args else ''
		if link != '':
			self.listItems(scrapSeries(link, self.bitrate, pg), pg, args, 'serie', False)

	def listItems(self, items, pg, args, handler, markFav=False):
		grouping = args.get('grouping', False)
		pgSize = args.get('pg-size', -1)
		groupName = ''
		if items is not None:
			xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
			for item in items:
				if not item:
					continue # may be None due to fetch errors

				title = item['title']
				if markFav and self.isFavourite(title):
					title = self.FAVOURITE % title
				# truncate if necessary:
				#if len(title) > 50:
				#	title = title[:50] + u'…'
				if item.get('episodeNum') and item.get('seasonNum'):
					title += ' (S%sE%s)' % (item['seasonNum'], item['episodeNum'])

				#av = item['available']
				#expiresInHours = int((int(av) - time.time()) / (60 * 60))

				#availableText = item['available-text']
				#if 24 > expiresInHours >= 0:
				#	title = self.EXPIRES_HOURS % (expiresInHours, title)
				#	availableText = '[COLOR red]%s[/COLOR]' % availableText
				#elif 120 >= expiresInHours >= 0:
				#	title = self.EXPIRES_DAYS % (expiresInHours / 24, title)
				#	availableText = '[COLOR red]%s[/COLOR]' % availableText

				plot = '[B]%s[/B]\n\r%s' % (item['details'], item['desc'])
				contextMenu = []

				if self.enabledDownload:
					contextMenu.append((self.createContextMenuAction('Download', 'download', {'videoLink': item['link'], 'title': item['title']}) ))
				if item.get('published-ts') is not None:
					aired = item.get('published-ts').strftime('%Y-%m-%d')
				else:
					aired = None
				self.addVideoLink(title, item['link'], item['image'],
								  infoLabels={'plot': plot, 'season': item.get('seasonNum', None), 'episode': item.get('episodeNum', None), 'aired': aired, 'duration': item['duration']}, contextMenu=contextMenu)
			if len(items) > 0 and len(items) >= pgSize:
				self.addViewLink(self.NEXT, handler, pg + 1, args)

	def handlePrograms(self, pg, args):
		serieList = scrapPrograms()
		for serie in serieList:
			try:
				title = serie.get('name').encode('utf-8').replace('&#039;', "'")
				menu = [(self.createContextMenuAction(self.FAVOURITE % self.lang(30017), 'addFav', serie) )]
				episodesLink = getEpisodesLink( str(serie.get('seriesId')) )
				if self.isFavourite(title):
					title = self.FAVOURITE % title
					menu = [(self.createContextMenuAction(self.REMOVE, 'removeFav', serie) )]
				self.addViewLink(title, 'serie', 1, {'link': episodesLink, 'pg-size': 100}, menu)
			except:
				pass

	def handleAction(self, action, params):
		if action == 'addFav':
			self.favourites[params['name'].encode("utf-8")] = params['link']
			favStr = repr(self.favourites)
			self.addon.setSetting('fav', favStr)
			xbmcUtil.notification(self.lang(30006), params['name'].encode("utf-8"))
		elif action == 'removeFav':
			self.favourites.pop(params['name'])
			favStr = repr(self.favourites)
			self.addon.setSetting('fav', favStr)
			xbmcUtil.notification(self.lang(30007), params['name'].encode("utf-8"))
		elif action == 'download':
			downloadVideo(params['videoLink'], params['title'])
		else:
			super(ViewAddonAbstract, self).handleAction(self, action, params)

	def handleVideo(self, link):
		return link

#-----------------------------------

ruutu = RuutuAddon()
lang = ruutu.lang
ruutu.handle()
