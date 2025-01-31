import uuid, requests, json, pytz, gzip, re
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

class Client:
    def __init__(self):
        self.session = requests.Session()
        self.sessionAt = {}
        self.response_list = {}
        self.epg_data = {}
        self.device = None
        self.all_channels = {}

        self.load_device()
        self.x_forward = {"local": {"X-Forwarded-For":""},
                          "uk": {"X-Forwarded-For":"178.238.11.6"},
                          "ca": {"X-Forwarded-For":"192.206.151.131"},
                          "us_east": {"X-Forwarded-For":"108.82.206.181"},
                          "us_west": {"X-Forwarded-For":"76.81.9.69"},}

    def load_device(self):
        if self.device is None:
            self.device = uuid.uuid1()
        return(self.device)

    def resp_data(self, country_code):
        desired_timezone = pytz.timezone('UTC')
        current_date = datetime.now(desired_timezone)
        if (self.response_list.get(country_code) is not None) and (current_date - self.sessionAt.get(country_code, datetime.now())) < timedelta(hours=4):
            return self.response_list[country_code], None

        boot_headers = {
            'authority': 'boot.pluto.tv',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'origin': 'https://pluto.tv',
            'referer': 'https://pluto.tv/',
            'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            }

        boot_params = {
            'appName': 'web',
            'appVersion': '8.0.0-111b2b9dc00bd0bea9030b30662159ed9e7c8bc6',
            'deviceVersion': '122.0.0',
            'deviceModel': 'web',
            'deviceMake': 'chrome',
            'deviceType': 'web',
            'clientID': 'c63f9fbf-47f5-40dc-941c-5628558aec87',
            'clientModelNumber': '1.0.0',
            'serverSideAds': 'false',
            'drmCapabilities': 'widevine:L3',
            'blockingMode': '',
            'notificationVersion': '1',
            'appLaunchCount': '',
            'lastAppLaunchDate': '',
            # 'clientTime': '2024-04-18T19:05:52.323Z',
            }

        if country_code in self.x_forward.keys():
            boot_headers.update(self.x_forward.get(country_code))

        try:
            response = self.session.get('https://boot.pluto.tv/v4/start', headers=boot_headers, params=boot_params)
        except Exception as e:
            return None, (f"Error Exception type: {type(e).__name__}")

        if (200 <= response.status_code <= 201):
            resp = response.json()
        else:
            print(f"HTTP failure {response.status_code}: {response.text}")
            return None, f"HTTP failure {response.status_code}: {response.text}"

        # Save entire Response:
        self.response_list.update({country_code: resp})
        self.sessionAt.update({country_code: current_date})
        print(f"New token for {country_code} generated at {(self.sessionAt.get(country_code)).strftime('%Y-%m-%d %H:%M.%S %z')}")

        return self.response_list.get(country_code), None

    def channels(self, country_code):
        if country_code == 'all':
            return(self.channels_all())

        resp, error = self.resp_data(country_code)
        if error: return None, error

        token = resp.get('sessionToken', None)
        if token is None: return None, error

        url = f"https://service-channels.clusters.pluto.tv/v2/guide/channels"

        headers = {
            'authority': 'service-channels.clusters.pluto.tv',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {token}',
            'origin': 'https://pluto.tv',
            'referer': 'https://pluto.tv/',
            }

        params = {
            'channelIds': '',
            'offset': '0',
            'limit': '1000',
            'sort': 'number:asc',
            }

        if country_code in self.x_forward.keys():
            headers.update(self.x_forward.get(country_code))

        try:
            response = self.session.get(url, params=params, headers=headers)
        except Exception as e:
            return None, (f"Error Exception type: {type(e).__name__}")

        if response.status_code != 200:
            return None, f"HTTP failure {response.status_code}: {response.text}"

        channel_list = response.json().get("data")

        category_url = f"https://service-channels.clusters.pluto.tv/v2/guide/categories"

        try:
            response = self.session.get(category_url, params=params, headers=headers)
        except Exception as e:
            return None, (f"Error Exception type: {type(e).__name__}")
        
        if response.status_code != 200:
            return None, f"HTTP failure {response.status_code}: {response.text}"

        categories_data = response.json().get("data")

        categories_list = {}
        for elem in categories_data:
            category = elem.get('name')
            channelIDs = elem.get('channelIDs')
            for channel in channelIDs:
                categories_list.update({channel: category})

        stations = []
        for elem in channel_list:
            entry = {'id': elem.get('id'),
                    'name': elem.get('name'),
                    'slug': elem.get('slug'),
                    'tmsid': elem.get('tmsid'),
                    'summary': elem.get('summary'),
                    'group': categories_list.get(elem.get('id')),
                    'country_code': country_code}

            # Ensure number value is unique
            number = elem.get('number')
            existing_numbers = {channel["number"] for channel in stations}
            while number in existing_numbers:
                # print(f"Updating channel number for {elem.get('name')}")
                number += 1

            # Filter the list to find the element with "type" equal to "colorLogoPNG"
            color_logo_png = next((image["url"] for image in elem["images"] if image["type"] == "colorLogoPNG"), None)
            entry.update({'number': number, 'logo': color_logo_png})

            stations.append(entry)

        sorted_data = sorted(stations, key=lambda x: x["number"])
        # print(json.dumps(sorted_data[0], indent = 2))

        self.all_channels.update({country_code: sorted_data})
        return(sorted_data, None)

    def channels_all(self):
        all_channel_list = []
        for key, val in self.all_channels.items():
            all_channel_list.extend(val)

        # Using a set to keep track of slugs that have been seen and filter unique ones
        seen = set()
        filter_key = 'id'
        filtered_list = [d for d in all_channel_list if d[filter_key] not in seen and not seen.add(d[filter_key])]


        seen = set()
        for elem in filtered_list:
            # Ensure number value is unique
            number = elem.get('number')
            match elem.get('country_code').lower():
                case 'ca':
                    offset = 6000
                    if number < offset:
                        number += offset
                case 'uk':
                    offset = 7000
                    if number < offset:
                        number += offset
                case 'fr':
                    offset = 8000
                    if number < offset:
                        number += offset
            while number in seen:
                number += 1
            seen.add(number)
            if number != elem.get('number'):
                elem.update({'number': number})

        return(filtered_list, None)

    #########################################################################################
    # EPG Guide Data
    #########################################################################################
    def strip_illegal_characters(self, xml_string):
        # Define a regular expression pattern to match illegal characters
        illegal_char_pattern = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

        # Replace illegal characters with an empty string
        clean_xml_string = illegal_char_pattern.sub('', xml_string)

        return clean_xml_string


    def update_epg(self, country_code, range_count = 3):
        resp, error = self.resp_data(country_code)
        if error: return None, error

        token = resp.get('sessionToken', None)
        if token is None: return None, error

        desired_timezone = pytz.timezone('UTC')

        start_datetime = datetime.now(desired_timezone)
        start_time = start_datetime.strftime("%Y-%m-%dT%H:00:00.000Z")
        end_time = start_time

        url = f"https://service-channels.clusters.pluto.tv/v2/guide/timelines"

        epg_headers = {
            'authority': 'service-channels.clusters.pluto.tv',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {token}',
            'origin': 'https://pluto.tv',
            'referer': 'https://pluto.tv/',
            }

        epg_params = {
            'start': start_time,
            'channelIds': '',
            'duration': '720',
            }

        if country_code in self.x_forward.keys():
            epg_headers.update(self.x_forward.get(country_code))

        station_list, error = self.channels(country_code)
        if error: return None, error

        id_values = [d['id'] for d in station_list]
        group_size = 100
        grouped_id_values = [id_values[i:i + group_size] for i in range(0, len(id_values), group_size)]
        # country_data = self.epg_data.get(country_code, [])
        country_data = []

        for i in range(range_count):
            if end_time != start_time:
                start_time = end_time
                epg_params.update({'start': start_time})
            print(f'Retrieving {country_code} EPG data for {start_time}')

            for group in grouped_id_values:
                epg_params.update({"channelIds": ','.join(map(str, group))})
                try:
                    response = self.session.get(url, params=epg_params, headers=epg_headers)
                except Exception as e:
                    return None, (f"Error Exception type: {type(e).__name__}")
                
                if response.status_code != 200:
                    return None, f"HTTP failure {response.status_code}: {response.text}"
                country_data.append(response.json())


            end_time = datetime.strptime(response.json()["meta"]["endDateTime"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc).strftime("%Y-%m-%dT%H:00:00.000Z")


        self.epg_data.update({country_code: country_data})
        return None

    def epg_json(self, country_code):
        error_code = self.update_epg(country_code)
        if error_code:
            print("error")
            return None, error_code
        return self.epg_data, None

    def find_tuples_by_value(self, dictionary, target_value):
        result_list = []  # Initialize an empty list
        for key, values in dictionary.items():
            if target_value in values:
                result_list.extend(key)  # Add the first element of the tuple to the result list
        return result_list if result_list else [target_value]  # Return None if the value is not found in any list

    def read_epg_data(self, resp, root):
        seriesGenres = {
            ("Animated",): ["Family Animation", "Cartoons"],
            ("Educational",): ["Education & Guidance", "Instructional & Educational"],
            ("News",): ["News and Information", "General News", "News + Opinion", "General News"],
            ("History",): ["History & Social Studies"],
            ("Politics",): ["Politics"],
            ("Action",):
                [
                  "Action & Adventure",
                  "Action Classics",
                  "Martial Arts",
                  "Crime Action",
                  "Family Adventures",
                  "Action Sci-Fi & Fantasy",
                  "Action Thrillers",
                  "African-American Action",
                ],
            ("Adventure",): ["Action & Adventure", "Adventures", "Sci-Fi Adventure"],
            ("Reality",):
                [
                  "Reality",
                  "Reality Drama",
                  "Courtroom Reality",
                  "Occupational Reality",
                  "Celebrity Reality",
                ],
            ("Documentary",):
                [
                  "Documentaries",
                  "Social & Cultural Documentaries",
                  "Science and Nature Documentaries",
                  "Miscellaneous Documentaries",
                  "Crime Documentaries",
                  "Travel & Adventure Documentaries",
                  "Sports Documentaries",
                  "Military Documentaries",
                  "Political Documentaries",
                  "Foreign Documentaries",
                  "Religion & Mythology Documentaries",
                  "Historical Documentaries",
                  "Biographical Documentaries",
                  "Faith & Spirituality Documentaries",
                ],
            ("Biography",): ["Biographical Documentaries", "Inspirational Biographies"],
            ("Science Fiction",): ["Sci-Fi Thrillers", "Sci-Fi Adventure", "Action Sci-Fi & Fantasy"],
            ("Thriller",): ["Sci-Fi Thrillers", "Thrillers", "Crime Thrillers"],
            ("Biography",): ["Biographical Documentaries", "Inspirational Biographies"],
            ("Talk",): ["Talk & Variety", "Talk Show"],
            ("Variety",): ["Sketch Comedies"],
            ("Home Improvement",): ["Art & Design", "DIY & How To", "Home Improvement"],
            ("House/garden",): ["Home & Garden"],
            # ("Science",): ["Science and Nature Documentaries"],
            # ("Nature",): ["Science and Nature Documentaries", "Animals"],
            ("Cooking",): ["Cooking Instruction", "Food & Wine", "Food Stories"],
            ("Travel",): ["Travel & Adventure Documentaries", "Travel"],
            ("Western",): ["Westerns", "Classic Westerns"],
            ("LGBTQ",): ["Gay & Lesbian", "Gay & Lesbian Dramas", "Gay"],
            ("Game show",): ["Game Show"],
            ("Military",): ["Classic War Stories"],
            ("Comedy",):
                [
                  "Cult Comedies",
                  "Spoofs and Satire",
                  "Slapstick",
                  "Classic Comedies",
                  "Stand-Up",
                  "Sports Comedies",
                  "African-American Comedies",
                  "Showbiz Comedies",
                  "Sketch Comedies",
                  "Teen Comedies",
                  "Latino Comedies",
                  "Family Comedies",
                ],
            ("Crime",): ["Crime Action", "Crime Drama", "Crime Documentaries"],
            ("Sports",): ["Sports","Sports & Sports Highlights","Sports Documentaries", "Poker & Gambling"],
            ("Poker & Gambling",): ["Poker & Gambling"],
            ("Crime drama",): ["Crime Drama"],
            ("Drama",):
                [
                  "Classic Dramas",
                  "Family Drama",
                  "Indie Drama",
                  "Romantic Drama",
                  "Crime Drama",
                ],
            ("Children",): ["Kids", "Children & Family", "Kids' TV", "Cartoons", "Animals", "Family Animation", "Ages 2-4", "Ages 11-12",],
            ("Animated",): ["Family Animation", "Cartoons"]
            }

        for entry in resp["data"]:
            for timeline in entry["timelines"]:
                # Create programme element
                programme = ET.SubElement(root, "programme", attrib={"channel": entry["channelId"],
                                                                 "start": datetime.strptime(timeline["start"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc).strftime("%Y%m%d%H%M%S %z"),
                                                                 "stop": datetime.strptime(timeline["stop"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc).strftime("%Y%m%d%H%M%S %z")})
                # Add sub-elements to programme
                title = ET.SubElement(programme, "title")
                title.text = self.strip_illegal_characters(timeline["title"])
                if timeline["episode"].get("series", {}).get("type", "") == "live":
                    if timeline["episode"]["clip"]["originalReleaseDate"] == timeline["start"]:
                        live = ET.SubElement(programme, "live")
                    if timeline["episode"].get("season", None):
                        episode_num_onscreen = ET.SubElement(programme, "episode-num", attrib={"system": "onscreen"})
                        episode_num_onscreen.text = f'S{timeline["episode"]["season"]:02d}E{timeline["episode"]["number"]:02d}'
                        episode_num_pluto = ET.SubElement(programme, "episode-num", attrib={"system": "pluto"})
                        episode_num_pluto.text = timeline["episode"]["_id"]
                elif timeline["episode"].get("series", {}).get("type", "") == "tv":
                    episode_num_onscreen = ET.SubElement(programme, "episode-num", attrib={"system": "onscreen"})
                    episode_num_onscreen.text = f'S{timeline["episode"]["season"]:02d}E{timeline["episode"]["number"]:02d}'
                    episode_num_pluto = ET.SubElement(programme, "episode-num", attrib={"system": "pluto"})
                    episode_num_pluto.text = timeline["episode"]["_id"]
                episode_num_air_date = ET.SubElement(programme, "episode-num", attrib={"system": "original-air-date"})
                episode_num_air_date.text = datetime.strptime(timeline["episode"]["clip"]["originalReleaseDate"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z'
                desc = ET.SubElement(programme, "desc")
                desc.text = self.strip_illegal_characters(timeline["episode"]["description"]).replace('&quot;', '"')
                icon_programme = ET.SubElement(programme, "icon", attrib={"src": timeline["episode"]["series"]["tile"]["path"]})
                date = ET.SubElement(programme, "date")
                date.text = datetime.strptime(timeline["episode"]["clip"]["originalReleaseDate"], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y%m%d")
                # if timeline["episode"].get("series", {}).get("type", "") == "tv":
                series_id_pluto = ET.SubElement(programme, "series-id", attrib={"system": "pluto"})
                series_id_pluto.text = timeline["episode"]["series"]["_id"]
                if timeline["title"].lower() != timeline["episode"]["name"].lower():
                    sub_title = ET.SubElement(programme, "sub-title")
                    sub_title.text = self.strip_illegal_characters(timeline["episode"]["name"])
                categories = []
                if timeline["episode"].get("genre", None) is not None:
                    genre = timeline["episode"]["genre"]
                    result = self.find_tuples_by_value(seriesGenres, genre)
                    categories.extend(result)
                if timeline["episode"].get("series", {}).get("type", "") == "tv":
                    categories.append("Series")
                if timeline["episode"].get("series", {}).get("type", "") == "film":
                    categories.append("Movie")
                if timeline["episode"].get("subGenre", None) is not None:
                    subGenre = timeline["episode"]["subGenre"]
                    result = self.find_tuples_by_value(seriesGenres, subGenre)
                    categories.extend(result)
                # categories = sorted(categories)

                unique_list = []
                for item in categories:
                    if item not in unique_list:
                        unique_list.append(item)

                for category in unique_list:
                    category_elem = ET.SubElement(programme, "category")
                    category_elem.text = category
        return root

    def get_all_epg_data(self, country_code):
        all_epg_data = []
        # print (country_code)
        channelIds_seen = {}
        range_count = 3

        for country in country_code:
            error_code = self.update_epg(country, range_count)
            if error_code: return error_code

            for epg_list in self.epg_data.get(country):
                data_list = epg_list.get('data')
                # Make a copy of the list for iteration to avoid modifying the list while iterating
                for entry in data_list[:]:
                    channelId = entry.get('channelId')
                    if channelId in channelIds_seen:
                        if channelIds_seen.get(channelId, 0) < range_count:
                            channelIds_seen.update({channelId: (channelIds_seen.get(channelId, 0) + 1)})
                            # print(f"[INFO] Adding {country}: {channelId}")
                        else:
                            # print(f"[INFO] Beyond {range_count}: Skipping duplicate entry for {country}: {channelId}")
                            data_list.remove(entry)
                    else:
                        channelIds_seen.update({channelId: 1})
                epg_data_dict = {'data': data_list}
                all_epg_data.append(epg_data_dict)

            
        # print(f"[INFO] Length {len(all_epg_data)}")
        return(all_epg_data)


    def create_xml_file(self, country_code):
        if isinstance(country_code, str):
            error_code = self.update_epg(country_code)
            if error_code: return error_code

            station_list, error = self.channels(country_code)
            if error: return None, error

            xml_file_path = f"epg-{country_code}.xml"

        elif isinstance(country_code, list):
            xml_file_path = f"epg-all.xml"
            station_list, error = self.channels_all()
        else:
            print("The variable is neither a string nor a list.")
            return None

        compressed_file_path = f"{xml_file_path}.gz"
        root = ET.Element("tv", attrib={"generator-info-name": "jgomez177", "generated-ts": ""})

        # Create Channel Elements from list of Stations
        for station in station_list:
            channel = ET.SubElement(root, "channel", attrib={"id": station["id"]})
            display_name = ET.SubElement(channel, "display-name")
            display_name.text = self.strip_illegal_characters(station["name"])
            icon = ET.SubElement(channel, "icon", attrib={"src": station["logo"]})

        # Create Programme Elements
        if isinstance(country_code, str):
            program_data =  self.epg_data.get(country_code, [])
        else:
            # Write program_data for all countries
            program_data = self.get_all_epg_data(country_code)
            #print(len(program_data))
            #for elem in program_data:
            #    print(len(elem.get("data")))
            #program_data = []
        # print(f"Program data: {len(program_data)}")
        for elem in program_data:
            root = self.read_epg_data(elem, root)


        # Create an ElementTree object
        tree = ET.ElementTree(root)
        ET.indent(tree, '  ')

        # Create a DOCTYPE declaration
        doctype = '<!DOCTYPE tv SYSTEM "xmltv.dtd">'

        # Concatenate the XML and DOCTYPE declarations in the desired order
        xml_declaration = '<?xml version=\'1.0\' encoding=\'utf-8\'?>'
        output_content = xml_declaration + '\n' + doctype + '\n' + ET.tostring(root, encoding='utf-8').decode('utf-8')

        # Write the concatenated content to the output file
        with open(xml_file_path, "w", encoding='utf-8') as f:
            f.write(output_content)

        # Compress the XML file
        with open(xml_file_path, 'rb') as file:
            with gzip.open(compressed_file_path, 'wb') as compressed_file:
                compressed_file.writelines(file)

        # Clear the EPG data after writing full XML File
        self.epg_data = {}
        return None
