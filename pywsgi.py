from gevent.pywsgi import WSGIServer
from flask import Flask, redirect, request, Response, send_file
from threading import Thread
import os, sys, importlib, schedule, time, re, uuid, unicodedata
from urllib.parse import urlparse, urlencode, urlunparse, parse_qs
from datetime import datetime, timedelta

# import flask module
from gevent import monkey
monkey.patch_all()

port = os.environ.get("PLUTO_PORT")
if port is None:
    port = 8000
else:
    try:
        port = int(port)
    except:
        port = 8000

pluto_country_list = os.environ.get("PLUTO_CODE")
if pluto_country_list:
   pluto_country_list = pluto_country_list.split(',')
else:
   pluto_country_list = ['local', 'us_east', 'us_west', 'ca', 'uk']

ALLOWED_COUNTRY_CODES = ['local', 'us_east', 'us_west', 'ca', 'uk', 'all']
# instance of flask application
app = Flask(__name__)
provider = "pluto"
providers = {
    provider: importlib.import_module(provider).Client(),
}

def remove_non_printable(s):
    return ''.join([char for char in s if not unicodedata.category(char).startswith('C')])

url = f'<!DOCTYPE html>\
        <html>\
          <head>\
            <meta charset="utf-8">\
            <meta name="viewport" content="width=device-width, initial-scale=1">\
            <title>{provider.capitalize()} Playlist</title>\
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@0.9.1/css/bulma.min.css">\
            <style>\
              ul{{\
                margin-bottom: 10px;\
              }}\
            </style>\
          </head>\
          <body>\
          <section class="section">\
            <div class="container">\
              <h1 class="title">\
                {provider.capitalize()} Playlist\
                <span class="tag">v1.18</span>\
              </h1>\
              <p class="subtitle">\
                Last Updated: Nov. 7, 2024\
              '

@app.route("/")
def index():
    host = request.host
    ul = ""
    if all(item in ALLOWED_COUNTRY_CODES for item in pluto_country_list):
        pl = f"http://{host}/{provider}/all/playlist.m3u"
        ul += f"<li>{provider.upper()} ALL channel_id_format = \"{provider}-{{slug}}\" (default format): <a href='{pl}'>{pl}</a></li>\n"
        pl = f"http://{host}/{provider}/all/playlist.m3u?channel_id_format=id"
        ul += f"<li>{provider.upper()} ALL channel_id_format = \"{provider}-{{id}}\" (i.mjh.nz compatibility): <a href='{pl}'>{pl}</a></li>\n"
        pl = f"http://{host}/{provider}/all/playlist.m3u?channel_id_format=slug_only"
        ul += f"<li>{provider.upper()} ALL channel_id_format = \"{{slug}}\" (maddox compatibility): <a href='{pl}'>{pl}</a></li>\n"
        ul += f"<br>\n"
        pl = f"http://{host}/{provider}/epg/all/epg-all.xml"
        ul += f"<li>{provider.upper()} ALL EPG: <a href='{pl}'>{pl}</a></li>\n"
        pl = f"http://{host}/{provider}/epg/all/epg-all.xml.gz"
        ul += f"<li>{provider.upper()} ALL EPG GZ: <a href='{pl}'>{pl}</a></li>\n"
        ul += f"<br>\n"
        for code in pluto_country_list:
            pl = f"http://{host}/{provider}/{code}/playlist.m3u"
            ul += f"<li>{provider.upper()} {code.upper()} channel_id_format = \"{provider}-{{slug}}\" (default format): <a href='{pl}'>{pl}</a></li>\n"
            pl = f"http://{host}/{provider}/{code}/playlist.m3u?channel_id_format=id"
            ul += f"<li>{provider.upper()} {code.upper()} channel_id_format = \"{provider}-{{id}}\" (i.mjh.nz compatibility): <a href='{pl}'>{pl}</a></li>\n"
            pl = f"http://{host}/{provider}/{code}/playlist.m3u?channel_id_format=slug_only"
            ul += f"<li>{provider.upper()} {code.upper()} channel_id_format = \"{{slug}}\" (maddox compatibility): <a href='{pl}'>{pl}</a></li>\n"
            ul += f"<br>\n"
            pl = f"http://{host}/{provider}/epg/{code}/epg-{code}.xml"
            ul += f"<li>{provider.upper()} {code.upper()} EPG: <a href='{pl}'>{pl}</a></li>\n"
            pl = f"http://{host}/{provider}/epg/{code}/epg-{code}.xml.gz"
            ul += f"<li>{provider.upper()} {code.upper()} EPG GZ: <a href='{pl}'>{pl}</a></li>\n"
            ul += f"<br>\n"
    else:
        ul += f"<li>INVALID COUNTRY CODE in \"{', '.join(pluto_country_list).upper()}\"</li>\n"
    return f"{url}<ul>{ul}</ul></div></section></body></html>"

@app.route("/<country_code>/token")
def token(country_code):
    resp, error = providers[provider].resp_data(country_code)
    if error: return f"ERROR: {error}", 400
    token = resp.get('sessionToken', None)
    return(token)

@app.route("/<country_code>/resp")
def resp(country_code):
    resp, error = providers[provider].resp_data(country_code)
    if error: return f"ERROR: {error}", 400
    # token = resp.get('sessionToken', None)
    return(resp)

@app.route("/<provider>/<country_code>/channels")
def channels(provider, country_code):
    # host = request.host
    channels, error = providers[provider].channels(country_code)
    if error: return f"ERROR: {error}", 400
    return(channels)

@app.get("/<provider>/<country_code>/epg.json")
def epg_json(provider, country_code):
        epg, err = providers[provider].epg_json(country_code)
        if err: return err
        return epg.get(country_code)

@app.get("/<provider>/<country_code>/stitcher.json")
def stitch_json(provider, country_code):
    resp, error= providers[provider].resp_data(country_code)
    if error: return error, 500
    return resp

@app.get("/<provider>/<country_code>/playlist.m3u")
def playlist(provider, country_code):
    if country_code.lower() == 'all':
        stations, err = providers[provider].channels_all()
    elif country_code.lower() in ALLOWED_COUNTRY_CODES:
        stations, err = providers[provider].channels(country_code)
    else: # country_code not in ALLOWED_COUNTRY_CODES
        return "Invalid county code", 400

    host = request.host
    channel_id_format = request.args.get('channel_id_format','').lower()
    
    if err is not None:
        return err, 500
    stations = sorted(stations, key = lambda i: i.get('number', 0))

    client_id = providers[provider].load_device()
    sid = uuid.uuid4()
    stitcher = "https://cfd-v4-service-channel-stitcher-use1-1.prd.pluto.tv"
    base_path = f"/stitch/hls/channel/{id}/master.m3u8"
    jwt_required_list = ['625f054c5dfea70007244612', '625f04253e5f6c000708f3b7', '5421f71da6af422839419cb3']
    params = {'advertisingId': '',
              'appName': 'web',
              'appVersion': 'unknown',
              'appStoreUrl': '',
              'architecture': '',
              'buildVersion': '',
              'clientTime': '0',
              'deviceDNT': '0',
              'deviceId': client_id,
              'deviceMake': 'Chrome',
              'deviceModel': 'web',
              'deviceType': 'web',
              'deviceVersion': 'unknown',
              'includeExtendedEvents': 'false',
              'sid': sid,
              'userId': '',
              'serverSideAds': 'false'
    }
    
    m3u = "#EXTM3U\r\n\r\n"
    for s in stations:
        url = f"http://{host}/{provider}/{country_code}/watch/{s.get('watchId') or s.get('id')}\n\n"

        if channel_id_format == 'id':
            m3u += f"#EXTINF:-1 channel-id=\"{provider}-{s.get('id')}\""
        elif channel_id_format == 'slug_only':
            m3u += f"#EXTINF:-1 channel-id=\"{s.get('slug')}\""
        else:
            m3u += f"#EXTINF:-1 channel-id=\"{provider}-{s.get('slug')}\""
        m3u += f" tvg-id=\"{s.get('id')}\""
        m3u += f" tvg-chno=\"{''.join(map(str, str(s.get('number', []))))}\"" if s.get('number') else ""
        m3u += f" group-title=\"{''.join(map(str, s.get('group', [])))}\"" if s.get('group') else ""
        m3u += f" tvg-logo=\"{''.join(map(str, s.get('logo', [])))}\"" if s.get('logo') else ""
        m3u += f" tvg-name=\"{''.join(map(str, s.get('tmsid', [])))}\"" if s.get('tmsid') else ""
        m3u += f" tvc-guide-title=\"{''.join(map(str, s.get('name', [])))}\"" if s.get('name') else ""
        m3u += f" tvc-guide-description=\"{remove_non_printable(''.join(map(str, s.get('summary', []))))}\"" if s.get('summary') else ""
        m3u += f" tvg-shift=\"{''.join(map(str, s.get('timeShift', [])))}\"" if s.get('timeShift') else ""
        m3u += f",{s.get('name') or s.get('call_sign')}\n"
        m3u += f"{stitcher}/stitch/hls/channel/{s.get('id')}/master.m3u8?advertisingId=&appName=web&appVersion=unknown&appStoreUrl=&architecture=&buildVersion=&clientTime=0&deviceDNT=0&deviceId={client_id}&deviceMake=Chrome&deviceModel=web&deviceType=web&deviceVersion=unknown&includeExtendedEvents=false&sid={sid}&userId=&serverSideAds=false\n\n"


    response = Response(m3u, content_type='audio/x-mpegurl')
    return (response)

@app.get("/mjh_compatible/<provider>/<country_code>/playlist.m3u")
def playlist_mjh_compatible(provider, country_code):
    host = request.host
    return (redirect(f"http://{host}/{provider}/{country_code}/playlist.m3u?compatibility=id"))

@app.get("/maddox_compatible/<provider>/<country_code>/playlist.m3u")
def playlist_maddox_compatible(provider, country_code):
    host = request.host
    return (redirect(f"http://{host}/{provider}/{country_code}/playlist.m3u?compatibility=slug_only"))

@app.route("/<provider>/<country_code>/watch/<id>")
def watch(provider, country_code, id):
    client_id = providers[provider].load_device()
    sid = uuid.uuid4()
    stitcher = "https://cfd-v4-service-channel-stitcher-use1-1.prd.pluto.tv"
    base_path = f"/stitch/hls/channel/{id}/master.m3u8"

    jwt_required_list = ['625f054c5dfea70007244612', '625f04253e5f6c000708f3b7', '5421f71da6af422839419cb3']
    

    params = {'advertisingId': '',
              'appName': 'web',
              'appVersion': 'unknown',
              'appStoreUrl': '',
              'architecture': '',
              'buildVersion': '',
              'clientTime': '0',
              'deviceDNT': '0',
              'deviceId': client_id,
              'deviceMake': 'Chrome',
              'deviceModel': 'web',
              'deviceType': 'web',
              'deviceVersion': 'unknown',
              'includeExtendedEvents': 'false',
              'sid': sid,
              'userId': '',
              'serverSideAds': 'true'
    }

    if id in jwt_required_list:
        resp, error= providers[provider].resp_data(country_code)
        if error: return error, 500
        # print(json.dumps(resp, indent=2))
        token = resp.get('sessionToken','')
        stitcherParams = resp.get("stitcherParams",'')
        video_url = f'{stitcher}/v2{base_path}?{stitcherParams}&jwt={token}&masterJWTPassthrough=true&includeExtendedEvents=true'
    else:
        parsed_url = urlparse(f"{stitcher}{base_path}")
        base_query_params = parse_qs(parsed_url.query)
        # Update base query parameters with the provided parameters
        for key, value in params.items():
            if key in base_query_params:
                # Extend the existing values with new values if the parameter already exists
                base_query_params[key].extend(value)
            else:
                # Add new parameter and its values
                base_query_params[key] = value

        # Construct updated query string
        updated_query = urlencode(base_query_params, doseq=True)

        # Generate the final URL
        video_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path,
                               parsed_url.params, updated_query, parsed_url.fragment))

    print(video_url)
    return (redirect(video_url))


@app.get("/<provider>/epg/<country_code>/<filename>")
def epg_xml(provider, country_code, filename):

    # Generate ALLOWED_FILENAMES and ALLOWED_GZ_FILENAMES based on ALLOWED_COUNTRY_CODES
    ALLOWED_EPG_FILENAMES = {f'epg-{code}.xml' for code in ALLOWED_COUNTRY_CODES}
    ALLOWED_GZ_FILENAMES = {f'epg-{code}.xml.gz' for code in ALLOWED_COUNTRY_CODES}

    # Specify the file path
    # file_path = 'epg.xml'
    try:
        if country_code not in ALLOWED_COUNTRY_CODES:
            return "Invalid county code", 400

        # Check if the provided filename is allowed in either format
        if filename not in ALLOWED_EPG_FILENAMES and filename not in ALLOWED_GZ_FILENAMES:
        # Check if the provided filename is allowed
        # if filename not in ALLOWED_EPG_FILENAMES:
            return "Invalid filename", 400
        
        # Specify the file path based on the provider and filename
        file_path = f'{filename}'

        # Return the file without explicitly opening it
        if filename in ALLOWED_EPG_FILENAMES: 
            return send_file(file_path, as_attachment=False, download_name=file_path, mimetype='text/plain')
        elif filename in ALLOWED_GZ_FILENAMES:
            return send_file(file_path, as_attachment=True, download_name=file_path)

    except FileNotFoundError:
        # Handle the case where the file is not found
        return "XML file not found", 404
    except Exception as e:
        # Handle other unexpected errors
        return f"An error occurred: {str(e)}", 500


    except Exception as e:
        # Handle other unexpected errors
        return f"An error occurred: {str(e)}", 500


# Define the function you want to execute every four hours
def epg_scheduler():
    if all(item in ALLOWED_COUNTRY_CODES for item in pluto_country_list):
        for code in pluto_country_list:
            # print("Scheduled EPG Data Update")
            error = providers[provider].create_xml_file(code)
            if error: print(f"{error}")
        print(f"Initialize XML File for ALL")
        error = providers[provider].create_xml_file(pluto_country_list)
        if error: print(f"{error}")
    

# Schedule the function to run every four hours
schedule.every(2).hours.do(epg_scheduler)

# Define a function to run the scheduler in a separate thread
def scheduler_thread():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    if all(item in ALLOWED_COUNTRY_CODES for item in pluto_country_list):
        for code in pluto_country_list:
            print(f"Initialize XML File for {code}")
            error = providers[provider].create_xml_file(code)
            if error: 
                print(f"{error}")
        print(f"Initialize XML File for ALL")
        error = providers[provider].create_xml_file(pluto_country_list)
        if error: print(f"{error}")

    sys.stdout.write(f"⇨ http server started on [::]:{port}\n")
    try:
        # Start the scheduler thread
        thread = Thread(target=scheduler_thread)
        thread.start()

        WSGIServer(('', port), app, log=None).serve_forever()
    except OSError as e:
        print(str(e))
