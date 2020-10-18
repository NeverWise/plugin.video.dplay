#!/usr/bin/python
import neverwise as nw, os, re, subprocess, sys, xbmc, xbmcplugin
from datetime import timedelta#, datetime

class Dplay(object):

    USER_AGENT = "okhttp/4.2.1"
    _handle = int(sys.argv[1])
    _params = nw.urlParametersToDict(sys.argv[2])
    _access_token = None

    def __init__(self):
        fanart = nw.addon.getAddonInfo('fanart')

        if len(self._params) == 0:
            response = self._getResponseJson(None)
            if response.isSucceeded:
                response = self._getResponseJson('https://eu2-prod.disco-api.com/content/shows?sort=name&page[size]=100&include=images', self._getHeaders(True))

                pages = response.body["meta"]["totalPages"]

                for p in range(1,pages+1):
                    response = self._getResponseJson('https://eu2-prod.disco-api.com/content/shows?sort=name&page[size]=100&include=images&page[number]={0}'.format(p), self._getHeaders(True))

                    imgList = self.loadImagesFromJson(response.body["included"])

                    for show in response.body['data']:
                        attr = show["attributes"]
                        desc = attr['description'] if 'description' in attr else ''
                        title = attr['name']

                        rel = show.get("relationships",{})

                        plus = False

                        try:
                            packages = rel["contentPackages"]["data"]
                            for p in packages:
                                if p.get("id","") == "Premium" :
                                    pp = "Dplay plus"
                                    plus = True
                                    title = title + " (PLUS)"
                                else:
                                    pp = p


                        except:
                            pass

                        images = rel.get("images",[])
                        if images:
                            icon_code = images["data"][0]["id"]

                            if icon_code in imgList:
                                icon = imgList[icon_code]
                            else:
                                icon = ""
                        else:
                            icon = ""

                        self._addItem(title, { 'at' : self._access_token, 'action' : 's', 'value' : show['id'] }, icon , fanart, desc)

                xbmcplugin.endOfDirectory(self._handle)
        else:
            self._access_token = self._params['at']

            if self._params['action'] == 's':
                url = 'https://eu2-prod.disco-api.com/content/videos?filter[show.id]={0}&page[size]=100&include=images&sort=seasonNumber,episodeNumber&filter[videoType]=EPISODE'.format(self._params['value'])
                xbmc.log("Dplay. OPEN URL: %s" % url)
                response = self._getResponseJson(url, self._getHeaders(True))
                if response.isSucceeded:

                    #if len(response.body['Sections']) > 0:
                    #    fanart = response.body['Images'][0]['Src']
                    fanart = ""  # da aggiustare
                    time_zone = nw.gettzlocal()
                    haveFFmpeg = os.path.isfile(nw.addon.getSetting('ffmpeg_path')) and os.path.isdir(nw.addon.getSetting('download_path'))

                    xbmc.log("Dplay. start reading images")
                    imgList = self.loadImagesFromJson(response.body["included"])
                    xbmc.log("Dplay. end reading images")

                    for video in response.body["data"]:
                        attr = video["attributes"]
                        season_number = attr.get("seasonNumber", 0)
                        episode_number = attr.get("episodeNumber",0)

                        vd = self._getVideoInfo(attr, time_zone)

                        rel = video.get("relationships",{})
                        images = rel.get("images",[])
                        if images:
                            icon_code = images["data"][0]["id"]

                            if icon_code in imgList:
                                icon = imgList[icon_code]
                            else:
                                icon = ""
                        else:
                            icon = ""

                        params = { 'at' : self._access_token, 'action' : 'v', 'value' : video['id'] } #'v' instead of 'd'
                        #params['action'] = 'v'
                        cm = nw.getDownloadContextMenu('RunPlugin({0})'.format(nw.formatUrl(params)), vd['title']) if haveFFmpeg else None
                        self._addItem(vd['title'], params, icon, icon, vd['descr'], self._getDuration(attr["videoDuration"]), True, cm)
                        xbmcplugin.setContent(self._handle, 'episodes')
                    xbmcplugin.endOfDirectory(self._handle)
                else:
                    nw.showNotification(nw.getTranslation(30014))

            elif self._params['action'] == 'v':
                result = self._getStream(self._params['value'])
                if not result:
                    nw.showVideoNotAvailable()
                else:
                    # Force XBMC to set the User-Agent HTTP header to the correct value
                    result_url = result['url'] + "|User-Agent=%s" % Dplay.USER_AGENT

                    nw.playStream(self._handle, result['title'], result['img'], result_url,
                        'video', { 'title' : result['title'], 'plot' : result['descr'] })

            elif self._params['action'] == 'd':
                result = self._getStream(self._params['value'])
                if not result:
                    nw.showVideoNotAvailable()
                else:
                    name = ''.join([i if ord(i) < 128 else '' for i in result['title'].replace(' ', '_')])
                    name = '{0}.ts'.format(name)
                    os.chdir(nw.addon.getSetting('download_path'))
                    #~ subprocess.call([nw.addon.getSetting('ffmpeg_path'), '-i', result['url'], '-c', 'copy', name])
                    subprocess.Popen([nw.addon.getSetting('ffmpeg_path'), '-user-agent', Dplay.USER_AGENT, '-i', result['url'], '-c', 'copy', name])

    def loadImagesFromJson(self, jsonIncluded):
        images = {}

        for img in jsonIncluded:
            try:
                if img.get("type","") == "image":
                    img_id = img.get("id","")
                    if img_id:
                        img_path = img["attributes"]["src"]

                        images[img_id] = img_path
            except:
                pass
        return images


    def _getStream(self, video_id):
        result = {}
        url = 'http://eu2-prod.disco-api.com/content/videos/{0}'.format(video_id)
        xbmc.log("Dplay OPEN URL: %s " % url)
        response = self._getResponseJson(url, self._getHeaders(True))
        if response.isSucceeded:
          vd = self._getVideoInfo(response.body["data"]["attributes"])
          result['title'] = vd['title']
          result['descr'] = vd['descr']
          result['img'] = "" # vd['img']
          if vd['plus'] :
              return
          response = self._getResponseJson('http://eu2-prod.disco-api.com/playback/videoPlaybackInfo/{0}'.format(video_id), True)
          if response.isSucceeded:
            url = response.body['data']['attributes']['streaming']['hls']['url']
            stream = nw.getResponse(url, headers={"User-Agent": Dplay.USER_AGENT})
            if stream.isSucceeded:
              qlySetting = nw.addon.getSetting('vid_quality')
              if qlySetting == '0':
                qlySetting = 180
              elif qlySetting == '1':
                qlySetting = 270
              elif qlySetting == '2':
                qlySetting = 360
              elif qlySetting == '3':
                qlySetting = 432
              elif qlySetting == '4':
                qlySetting = 576
              elif qlySetting == '5':
                qlySetting = 720
              elif qlySetting == '6':
                qlySetting = 1080
              else:
                qlySetting = 576
              try: # For python 2.x
                strms_names = re.findall(r'RESOLUTION=.+?x(.+?),.+?".+?"\s(.+)', stream.body)
              except: # For python 3.x
                strms_names = re.findall(r'RESOLUTION=.+?x(.+?),.+?".+?"\s(.+)', stream.body.decode('utf-8'))
              items = []
              for qly, strm_name in strms_names:
                items.append(( abs(qlySetting - int(qly)), strm_name.strip() ))
              items = sorted(items, key = lambda item: item[0])
              i_end = url.find('?')
              i_start = url.rfind('/', 0, i_end) + 1
              old_str = url[i_start:i_end]
              result['url'] = url.replace(old_str, items[0][1])
        return result


    def _getResponseJson(self, url, add_bearer = False):

        #token_url = 'https://dplayproxy.azurewebsites.net/api/config/init'
        token_url = "https://eu2-prod.disco-api.com/token?realm=dplayit"

        if url == None or len(url) == 0:
            url = token_url

        response = nw.getResponseJson(url, self._getHeaders(add_bearer), False)
        if not response.isSucceeded:
            self._access_token = None

            response = nw.getResponseJson(token_url, self._getHeaders())
            if response.isSucceeded:
                self._access_token = response.body['data']['attributes']['token']
                response = nw.getResponseJson(url, self._getHeaders(add_bearer))

        return response


    def _getHeaders(self, add_bearer = False):

        default_headers = { 'User-Agent' : Dplay.USER_AGENT, 'Accept-Encoding' : 'gzip' }
        headers = None
        if self._access_token != None:
            headers = { 'AccessToken' : self._access_token }
            try: # For python 2.x
                for key, value in default_headers.iteritems():
                    headers[key] = value
            except: # For python 3.x
                for key,value in default_headers.items():
                    headers[key] = value

        if headers == None:
            headers = default_headers
        if add_bearer:
            headers['Authorization'] = 'Bearer {0}'.format(self._access_token)

        return headers


    def _getVideoInfo(self, video, time_zone = None):
        title = u'{0} ({1} {2} - {3} {4})'.format(video['name'], nw.getTranslation(30011), video['seasonNumber'], nw.getTranslation(30012), video['episodeNumber'])
        descr = video['description']

        if 'publishEnd' in video:
            if time_zone == None:
                time_zone = nw.gettzlocal()
                date = nw.strptime(video['publishEnd'], '%Y-%m-%dT%H:%M:%SZ')
                date = date.replace(tzinfo = nw.gettz('UTC'))
                date = date.astimezone(time_zone)
                descr = u'{0}\n\n{1} {2}'.format(descr, nw.getTranslation(30013), date.strftime(nw.datetime_format))

        plus = False

        if 'packages' in video:
            descr = descr + "\n" + nw.getTranslation(30015) + ":" # cambiare stringa
            for p in video['packages']:
                if p == "Premium" :
                    pp = "Dplay plus"
                    plus = True
                    title = title + " (PLUS)"
                else:
                    pp = p

                descr = descr + " " + pp

        # aggiungere immagini

        return { 'img' : '' , 'title' : title, 'descr' : descr , 'plus' : plus}


    def _addItem(self, title, keyValueUrlList, logo = 'DefaultFolder.png', fanart = None, plot = None, duration = '', isPlayable = False, contextMenu = None):
        li = nw.createListItem(title, thumbnailImage = logo, fanart = fanart, streamtype = 'video', infolabels = { 'title' : title, 'plot' : plot }, duration = duration, isPlayable = isPlayable, contextMenu = contextMenu)
        xbmcplugin.addDirectoryItem(self._handle, nw.formatUrl(keyValueUrlList), li, not isPlayable)


    def _getDuration(self, milliseconds):
        return str(timedelta(milliseconds/1000.0))


# Entry point.
#startTime = datetime.now()
dplay = Dplay()
del dplay
#xbmc.log('{0} azione {1}'.format(nw.addonName, str(datetime.now() - startTime)))