import os, sys, ruamel.yaml
from json import JSONDecodeError
from urllib.parse import urlparse, parse_qs
 # https://www.themoviedb.org/list/10
 # https://trakt.tv/users/movistapp/lists/christmas-movies
 # https://mdblist.com/lists/linaspurinis/top-watched-movies-of-the-week
 # https://www.imdb.com/list/ls006405458
try:
    import requests
    from pmmutils import logging, util
    from pmmutils.args import PMMArgs
    from pmmutils.exceptions import Failed
    from pmmutils.yaml import YAML
    from tmdbapis import TMDbAPIs, TMDbException
except (ModuleNotFoundError, ImportError):
    print("Requirements Error: Requirements are not installed")
    sys.exit(0)

if sys.version_info[0] != 3 or sys.version_info[1] < 11:
    print("Version Error: Version: %s.%s.%s incompatible please use Python 3.11+" % (sys.version_info[0], sys.version_info[1], sys.version_info[2]))
    sys.exit(0)

options = [
    {"arg": "pc", "key": "pmm-config",   "env": "PMM_CONFIG",   "type": "str",  "default": None,  "help": "PMM Config File"},
    {"arg": "u",  "key": "url",          "env": "URL",          "type": "str",  "default": None,  "help": "Trakt, MDbList, IMDb, or TMDb List URL"},
    {"arg": "ti", "key": "timeout",      "env": "TIMEOUT",      "type": "int",  "default": 600,   "help": "Timeout can be any number greater then 0. (Default: 600)"},
    {"arg": "s",  "key": "season",       "env": "SEASON",       "type": "bool", "default": False, "help": "Add Season posters placeholders."},
    {"arg": "e",  "key": "episode",      "env": "EPISODE",      "type": "bool", "default": False, "help": "Add Episode posters placeholders."},
    {"arg": "tr", "key": "trace",        "env": "TRACE",        "type": "bool", "default": False, "help": "Run with extra trace logs."},
    {"arg": "lr", "key": "log-requests", "env": "LOG_REQUESTS", "type": "bool", "default": False, "help": "Run with every request logged."}
]
script_name = "Metadata Set Creator"
base_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(base_dir, "config")

pmmargs = PMMArgs("meisnate12/Metadata-Set-Creator", base_dir, options, use_nightly=False)
logger = logging.PMMLogger(script_name, "set_creator", os.path.join(config_dir, "logs"), is_trace=pmmargs["trace"], log_requests=pmmargs["log-requests"])
#logger.secret([pmmargs["tmdbapi"]])
requests.Session.send = util.update_send(requests.Session.send, pmmargs["timeout"])

logger.header(pmmargs, sub=True)
logger.separator("Validating Options", space=False, border=False)

if not pmmargs["pmm-config"]:
    pmmargs["pmm-config"] = os.path.join(config_dir, "config.yml")
if not os.path.exists(pmmargs["pmm-config"]):
    raise Failed(f"PMM Config Not Found at: {pmmargs['pmm-config']}")
config = YAML(path=pmmargs["pmm-config"])

if "tmdb" not in config:
    raise Failed("tmdb attribute not in config")
elif not config["tmdb"]:
    raise Failed("tmdb attribute blank")
elif "apikey" not in config["tmdb"]:
    raise Failed("apikey attribute not in tmdb")
elif not config["tmdb"]["apikey"]:
    raise Failed("apikey attribute blank")
tmdbapi = None
try:
    tmdbapi = TMDbAPIs(config["tmdb"]["apikey"])
    logger.info("TMDb Connection Successful")
except TMDbException as e:
    logger.error("TMDb Connection Failed")
    raise Failed(e)

movies = {}
shows = {}
if not pmmargs["url"]:
    raise Failed("No URL Provided")
elif pmmargs["url"].startswith("https://trakt.tv/"):
    if "trakt" not in config:
        raise Failed("trakt attribute not in config")
    elif not config["trakt"]:
        raise Failed("trakt attribute blank")
    elif "client_id" not in config["trakt"]:
        raise Failed("client_id attribute not in trakt")
    elif not config["trakt"]["client_id"]:
        raise Failed("client_id attribute blank")
    elif "authorization" not in config["trakt"]:
        raise Failed("authorization attribute not in trakt")
    elif not config["trakt"]["authorization"]:
        raise Failed("authorization attribute blank")
    elif "access_token" not in config["trakt"]["authorization"]:
        raise Failed("access_token attribute not in authorization")
    elif not config["trakt"]["authorization"]["access_token"]:
        raise Failed("access_token attribute blank")

    trakt_id = config["trakt"]["client_id"]
    trakt_token = config["trakt"]["authorization"]["access_token"]
    logger.secret([trakt_id, trakt_token])
    base_url = "https://api.trakt.tv"
    url = requests.utils.urlparse(pmmargs["url"]).path.replace("/official/", "/")
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {trakt_token}",
            "trakt-api-version": "2",
            "trakt-api-key": trakt_id
        }
        output_json = []
        params = {}
        pages = 1
        current = 1
        while current <= pages:
            if pages > 1:
                params["page"] = current
            response = requests.get(f"{base_url}{url}/items", headers=headers, params=params)
            if pages == 1 and "X-Pagination-Page-Count" in response.headers and not params:
                pages = int(response.headers["X-Pagination-Page-Count"])
            if response.status_code >= 400:
                raise Failed(f"({response.status_code}) {response.reason}")
            json_data = response.json()
            output_json.extend(json_data)
            current += 1
        logger.info(output_json)
    except Failed:
        raise Failed(f"Trakt Error: List {pmmargs['url']} not found")
    if len(output_json) == 0:
        raise Failed(f"Trakt Error: List {pmmargs['url']} is empty")

    id_translation = {"movie": "movie", "show": "show", "season": "show", "episode": "show"}
    id_types = {
        "movie": ("tmdb", "TMDb ID"),
        "show": ("tvdb", "TVDb ID"),
        "season": ("tvdb", "TVDb ID"),
        "episode": ("tvdb", "TVDb ID")
    }
    for item in output_json:
        if "type" in item and item["type"] in id_translation:
            data = item[id_translation[item["type"]]]
            _type = item["type"]
        else:
            continue
        id_type, id_display = id_types[_type]
        _id = int(data["ids"][id_type]) if id_type in data["ids"] and data["ids"][id_type] else data["title"]
        if _type == "movie":
            if _id not in movies:
                movies[_id] = {"title": data["title"], "year": data["year"]}
        else:
            if _id not in shows:
                shows[_id] = {"title": data["title"], "year": data["year"]}
elif pmmargs["url"].startswith("https://mdblist.com/lists/"):
    params = {}
    parsed_url = urlparse(pmmargs["url"])
    query = parse_qs(parsed_url.query)
    if "sort" in query:
        params["sort"] = query["sort"][0]
    if "sortorder" in query:
        params["sortorder"] = query["sortorder"][0]
    url_base = str(parsed_url._replace(query=None).geturl())
    url_base = url_base if url_base.endswith("/") else f"{url_base}/"
    url_base = url_base if url_base.endswith("json/") else f"{url_base}json/"
    try:
        response = requests.get(url_base, headers={"User-Agent": "Plex-Meta-Manager"}, params=params).json()
        if (isinstance(response, dict) and "error" in response) or (isinstance(response, list) and response and "error" in response[0]):
            err = response["error"] if isinstance(response, dict) else response[0]["error"]
            if err in ["empty", "empty or private list"]:
                raise Failed(f"Mdblist Error: No Items Returned. Lists can take 24 hours to update so try again later.")
            raise Failed(f"Mdblist Error: Invalid Response {response}")
    except JSONDecodeError:
        raise Failed(f"Mdblist Error: Invalid Response")
    results = []
    for data in response:
        if data["mediatype"] == "movie":
            if data["id"] not in movies:
                movies[data["id"]] = {"title": data["title"], "year": data["release_year"]}
        elif data["mediatype"] == "show":
            if data["tvdbid"] not in shows:
                shows[data["tvdbid"]] = {"title": data["title"], "year": data["release_year"]}
elif pmmargs["url"].startswith("https://www.themoviedb.org/list/"):
    if "tmdb" not in config:
        raise Failed("tmdb attribute not in config")
    elif not config["tmdb"]:
        raise Failed("tmdb attribute blank")
    elif "apikey" not in config["tmdb"]:
        raise Failed("apikey attribute not in tmdb")
    elif not config["tmdb"]["apikey"]:
        raise Failed("apikey attribute blank")
    tmdbapi = None
    try:
        tmdbapi = TMDbAPIs(config["tmdb"]["apikey"])
        logger.info("TMDb Connection Successful")
    except TMDbException as e:
        raise Failed(e)
#elif pmmargs["url"].startswith("https://www.imdb.com/"):
else:
    raise Failed(f"URL Invalid: {pmmargs['url']}")

if movies:
    metadata = {}
    set_data = {}
    for k, v in movies.items():
        title = f"{v['title']} ({v['year']})"
        metadata[title] = {"template": YAML.inline({"name": "images", "id": k if isinstance(k, int) else "???"})}
        set_data[title] = YAML.inline({"poster_tpdb": None})

    yaml_out = YAML(os.path.join(config_dir, "movie_list.yml"), start_empty=True)
    yaml_out["metadata"] = metadata
    yaml_out.save()

    yaml_out = YAML(os.path.join(config_dir, "movie_set.yml"), start_empty=True)
    yaml_out["set"] = set_data
    yaml_out.save()

if shows:
    metadata = {}
    set_data = {}
    for k, v in shows.items():
        title = f"{v['title']} ({v['year']})"
        metadata[title] = {"template": YAML.inline({"name": "images", "id": k if isinstance(k, int) else "???"})}
        show = {"poster_tpdb": None}
        if isinstance(k, int) and (pmmargs["season"] or pmmargs["episode"]):
            try:
                results = tmdbapi.find_by_id(tvdb_id=str(k))
                if not results.tv_results:
                    raise TMDbException(f"No Results were found for tvdb_id: {k}")
                tmdb_show = results.tv_results[0]
                for season in tmdb_show.seasons:
                    if "seasons" not in show:
                        show["seasons"] = {}
                    if pmmargs["episode"]:
                        show["seasons"][season.season_number] = {"poster_tpdb": None, "episodes": {}} if pmmargs["season"] else {"episodes": {}}
                        for episode in season.episodes:
                            show["seasons"][season.season_number]["episodes"][episode.episode_number] = YAML.inline({"poster_tpdb": None})
                    else:
                        show["seasons"][season.season_number] = YAML.inline({"poster_tpdb": None})
            except TMDbException as e:
                logger.error(f"TMDb Error: {e}")
        set_data[title] = YAML.inline(show) if len(show) == 1 else show

    yaml_out = YAML(os.path.join(config_dir, "show_list.yml"), start_empty=True)
    yaml_out["metadata"] = metadata
    yaml_out.save()

    yaml_out = YAML(os.path.join(config_dir, "show_set.yml"), start_empty=True)
    yaml_out["set"] = set_data
    yaml_out.save()
