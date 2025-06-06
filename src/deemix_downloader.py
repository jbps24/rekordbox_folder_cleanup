import os
import json
import logging
from pathlib import Path
import requests # For making HTTP requests to Deezer API
import deezer as Deezer # For the main Deezer API client
import traceback # For more detailed error logging

# Import deemix components if available
try:
    from deemix.downloader import Downloader as DeemixFileDownloader # Renamed to avoid confusion
    from deemix import generateDownloadObject # To create download objects for DeemixFileDownloader
    from deemix.types.DownloadObjects import Single as DeemixSingle, Collection as DeemixCollection
    from deezer import TrackFormats as DeemixTrackFormats # To map bitrate strings to int formats
    from deemix.errors import GenerationError as DeemixGenerationError, DownloadError as DeemixDownloadError, DownloadCanceled as DeemixDownloadCanceled
    DEEMIX_AVAILABLE = True
    from deemix.settings import FeaturesOption # Import FeaturesOption enum
except ImportError:
    DEEMIX_AVAILABLE = False
    # Define placeholders if deemix is not available
    class DeemixFileDownloader: # type: ignore
        def __init__(self, *args, **kwargs):
            # This will be caught by the check in DeemixDownloader.__init__
            # but good to have a more specific error if somehow instantiated.
            logger.error("deemix.downloader.Downloader is not installed or import failed.")
            raise ImportError("Deemix library is not installed or failed to import.")
        def downloadLink(self, *args, **kwargs):
            logger.error("Deemix library is not installed. Cannot download.")
            raise ImportError("Deemix library is not installed.")



# Setup basic logging
logger = logging.getLogger(__name__)
if not logger.handlers: # Avoid adding multiple handlers if reloaded
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class DeemixDownloader:
    """
    A client to interact with Deezer via the deemix library for downloading tracks.
    Handles ARL credential management.
    """
    DEFAULT_CONFIG_DIR_NAME = "deezer"
    RESOURCES_DIR_NAME = "resources"
    CONFIG_FILE_NAME = "deemix_credentials.json"
    DEFAULT_DOWNLOAD_ROOT_DIR = "downloaded_music/deezer_downloads"

    # Default settings for Deemix. Users can override these.
    # Refer to deemix documentation for all available options.
    DEFAULT_DEEMIX_SETTINGS = {
        "tracknameTemplate": "%artist% - %title%",
        "albumTracknameTemplate": "%album%/%number% - %title%",
        "foldernameTemplate": "%artist%/%album%", # General structure for artist/album
        "playlistTracknameTemplate": "%playlist%/%number% - %artist% - %title%",
        "createPlaylistFolder": True,
        "playlistNameTemplate": "%playlist%",
        "createArtistFolder": True, # Deemix handles this based on foldernameTemplate
        "createSingleFolder": True, # For tracks not part of an album (e.g., artist/single_title)
        "bitrate": "320",  # Options: "128", "320", "FLAC" (if available & account supports)
        "outputFormat": "mp3", # or "flac"
        "maxBitrate": False,
        "fallbackBitrate": True,
        "syncedLyrics": False,
        "saveArtwork": True, # Added: Save album artwork
        "dateFormat": "%Y-%m-%d", # Added: Format for dates in tags/filenames
        "saveArtworkArtist": False, # Added: Save artist artwork (less common by default)
        "embeddedArtworkSize": 800,
        "showTrackFound": True, # Print message when track is found by deemix
        "feelingLucky": False, # Added: For "feeling lucky" download mode
        "logSearched": False,  # Added: Log if a track was found via fallback search
        "executeCommand": "",  # Added: Command to execute after download
        "albumVariousArtists": False,
        "removeDuplicateArtists": False,
        "featuredToTitle": FeaturesOption.NO_CHANGE, # Added: How to handle featured artists in title
        "removeAlbumVersion": False, # Added: Remove "(Album Version)" from title
        "titleCasing": "nothing", # Added: Change title casing ("nothing", "capitalize", "lower", "upper")
        "artistCasing": "nothing", # Added: Change artist casing ("nothing", "capitalize", "lower", "upper")
        "tags": { # Added: Nested dictionary for tag-specific settings
            "savePlaylistAsCompilation": False, # Added: Save playlist as compilation album
            "multiArtistSeparator": "default" # Added: Separator for multiple artists tag ("default", "andFeat", or custom string)
        }
        # Add more deemix-specific settings here if needed
    }
    def __init__(self, arl=None, config_dir_parent=None, download_root_dir=None, custom_deemix_settings=None):
        """
        Initializes the DeemixDownloader.

        Args:
            arl (str, optional): Deezer ARL token. If None, will try to load from config or prompt.
            config_dir_parent (str, optional): Parent directory for 'resources'. Defaults to current dir.
            download_root_dir (str, optional): Root directory to download tracks.
                                               Defaults to DEFAULT_DOWNLOAD_ROOT_DIR.
            custom_deemix_settings (dict, optional): Custom settings to pass to Deemix.
        """
        if not DEEMIX_AVAILABLE:
            logger.error("Deemix library is not installed. Please install it with 'pip install deemix'")
            raise ImportError("Deemix library not found.")
        _config_parent = Path(config_dir_parent) if config_dir_parent else Path.cwd()
        self.config_dir = _config_parent / self.RESOURCES_DIR_NAME / self.DEFAULT_CONFIG_DIR_NAME
        self.credentials_file_path = self.config_dir / self.CONFIG_FILE_NAME

        self.download_root_dir = Path(download_root_dir or self.DEFAULT_DOWNLOAD_ROOT_DIR)

        self.deemix_settings = self.DEFAULT_DEEMIX_SETTINGS.copy()
        if custom_deemix_settings:
            self.deemix_settings.update(custom_deemix_settings)

        self.arl = arl
        self.deezer_client = None  # Deezer API client instance (deezer.Deezer)

        if not self.arl:
            self._load_or_prompt_arl()

    def _ensure_config_dir_exists(self):
        """Ensures the configuration directory exists."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Config directory ensured: {self.config_dir}")
            return True
        except OSError as e:
            logger.error(f"Error creating configuration directory {self.config_dir}: {e}")
            return False

    def _load_or_prompt_arl(self):
        """Loads ARL from config file, or prompts user if not found/invalid."""
        if self.credentials_file_path.exists():
            try:
                with open(self.credentials_file_path, 'r') as f:
                    creds = json.load(f)
                loaded_arl = creds.get("DEEZER_ARL")
                if loaded_arl:
                    self.arl = loaded_arl
                    logger.info(f"Deezer ARL loaded from {self.credentials_file_path}")
                    return True
                else:
                    logger.warning(f"DEEZER_ARL not found in {self.credentials_file_path}.")
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {self.credentials_file_path}.")
            except Exception as e:
                logger.error(f"Error loading credentials from {self.credentials_file_path}: {e}")

        # Prompt if ARL not loaded
        print("Deezer ARL token not found or invalid.")
        print("Please provide your Deezer ARL token. You can find this in your browser's cookies for deezer.com.")
        new_arl = input("Enter your DEEZER_ARL: ").strip()
        if new_arl:
            self.arl = new_arl
            if self._ensure_config_dir_exists():
                try:
                    with open(self.credentials_file_path, 'w') as f:
                        json.dump({"DEEZER_ARL": self.arl}, f, indent=4)
                    logger.info(f"Deezer ARL saved to {self.credentials_file_path}")
                    return True
                except Exception as e:
                    logger.error(f"Error saving ARL to {self.credentials_file_path}: {e}")
        else:
            logger.error("No ARL token provided. Cannot proceed.")
        return False

    def _initialize_api(self):
        """Initializes the Deemix API instance if not already done."""
        if self.deezer_client and getattr(self.deezer_client, 'logged_in', False):
            return True
        if not self.arl:
            logger.error("ARL token is not set. Cannot initialize Deemix API.")
            if not self._load_or_prompt_arl(): # Try one more time
                return False
        try:
            # Ensure download directory exists
            self.download_root_dir.mkdir(parents=True, exist_ok=True)

            self.deezer_client = Deezer.Deezer()
            if not self.deezer_client.login_via_arl(self.arl):
                logger.error("Failed to login to Deezer with the provided ARL.")
                self.deezer_client = None # Clear on failure
                return False

            user_name = "Unknown User"
            if self.deezer_client.current_user and 'name' in self.deezer_client.current_user:
                user_name = self.deezer_client.current_user['name']
            logger.info(f"Deezer API client initialized for user: {user_name}")
            logger.info(f"Downloads will be saved to: {self.download_root_dir.resolve()}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Deezer API client: {e}")
            logger.debug(traceback.format_exc())
            self.deezer_client = None
            return False

    def search_track(self, artist_name, track_name):
        """
        Searches for a track on Deezer using their unofficial API.
        Note: This uses an unofficial API endpoint (api.deezer.com/search)
        which might change or have limitations.

        Args:
            artist_name (str): The name of the artist.
            track_name (str): The name of the track.

        Returns:
            dict: A dictionary containing track details {'id', 'title', 'artist', 'link', 'album'}
                  if found, otherwise None.
        """
        search_query = f'artist:"{artist_name}" track:"{track_name}"'
        url = f"https://api.deezer.com/search?q={search_query}"
        logger.info(f"Searching Deezer for: {artist_name} - {track_name} (Query: {search_query})")
        logger.debug(f"Deezer search URL: {url}")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            results = response.json()

            if results and results.get("data"):
                # For simplicity, take the first result.
                # More sophisticated matching could be added here.
                track_data = results["data"][0]
                found_artist = track_data.get('artist', {}).get('name', 'Unknown Artist')
                found_title = track_data.get('title', 'Unknown Title')
                logger.info(f"Found: '{found_artist} - {found_title}' (ID: {track_data.get('id')}) for search '{artist_name} - {track_name}'.")
                return {
                    'id': track_data.get('id'),
                    'title': found_title,
                    'artist': found_artist,
                    'link': track_data.get('link'),
                    'album': track_data.get('album', {}).get('title', 'N/A')
                }
            logger.warning(f"No results found on Deezer for '{artist_name} - {track_name}'.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching Deezer for '{artist_name} - {track_name}': {e}")
        return None

    def download_url(self, deezer_url_or_id):
        """
        Downloads a track, album, or playlist from Deezer given its URL or ID.

        Args:
            deezer_url_or_id (str): The Deezer URL or ID.

        Returns:
            bool: True if download process was initiated, False otherwise.
        """
        if not self._initialize_api():
            logger.error("Cannot download: Deezer API client not initialized.")
            return False

        logger.info(f"Attempting to download: {deezer_url_or_id}")
        try:
            # Convert bitrate string from settings to TrackFormats integer
            bitrate_str = self.deemix_settings.get("bitrate", "320")
            target_bitrate_int = DeemixTrackFormats.MP3_320  # Default
            if bitrate_str == "FLAC":
                target_bitrate_int = DeemixTrackFormats.FLAC
            elif bitrate_str == "128":
                target_bitrate_int = DeemixTrackFormats.MP3_128
            # Add more mappings if other bitrates are supported/used in settings

            # Generate the download object(s)
            # The listener for generateDownloadObject is for artist progress, can be None for single items
            download_object_or_list = generateDownloadObject(
                self.deezer_client,
                deezer_url_or_id,
                target_bitrate_int,
                listener=None # Or a deemix-compatible listener if needed for artist progress
            )

            if not download_object_or_list:
                logger.error(f"Could not generate download object for {deezer_url_or_id}")
                return False

            download_items = []
            if isinstance(download_object_or_list, list):
                download_items.extend(download_object_or_list)
            else:
                download_items.append(download_object_or_list)

            all_successful = True
            for item_to_download in download_items:
                if not (isinstance(item_to_download, DeemixSingle) or isinstance(item_to_download, DeemixCollection)):
                    logger.warning(f"Skipping an unrecognized item from generateDownloadObject: {type(item_to_download)}")
                    all_successful = False
                    continue

                logger.info(f"Processing download for: {item_to_download.type} {getattr(item_to_download, 'id', 'N/A')}")
                downloader_settings = self.deemix_settings.copy()
                downloader_settings["downloadLocation"] = str(self.download_root_dir.resolve())

                # Instantiate and start the deemix.downloader.Downloader
                dl_instance = DeemixFileDownloader(self.deezer_client, item_to_download, downloader_settings, listener=None)
                dl_instance.start() # This call is blocking for the current item/collection
                # Error handling for individual items within a list (e.g. artist's albums)
                # would require checking dl_instance.downloadObject.errors after start()

            logger.info(f"Download process completed for {deezer_url_or_id}. Check deemix logs/output for status.")
            return all_successful # Or True if at least one started, depends on desired behavior
        except (DeemixDownloadCanceled, DeemixGenerationError, DeemixDownloadError) as e:
            logger.error(f"Error initiating download for {deezer_url_or_id} with deemix: {e}")
            return False
        except Exception as e: # Catch other generic errors
            logger.error(f"Unexpected error during download for {deezer_url_or_id}: {e}")
            logger.error(traceback.format_exc())
            return False

    def search_and_download_track(self, artist_name, track_name):
        """
        Searches for a track on Deezer and, if found, initiates its download.

        Args:
            artist_name (str): The name of the artist.
            track_name (str): The name of the track.

        Returns:
            bool: True if the track was found and download was initiated, False otherwise.
        """
        track_info = self.search_track(artist_name, track_name)
        if track_info and track_info.get('link'):
            logger.info(f"Proceeding to download '{track_info['artist']} - {track_info['title']}' using URL: {track_info['link']}")
            return self.download_url(track_info['link'])
        elif track_info and track_info.get('id'):
            logger.info(f"Proceeding to download '{track_info['artist']} - {track_info['title']}' using ID: {track_info['id']}")
            return self.download_url(str(track_info['id']))
        else:
            logger.warning(f"Could not download '{artist_name} - {track_name}' as it was not found or missing link/ID.")
            return False


if __name__ == '__main__':
    print("DeemixDownloader Module - Example Usage")
    
    # Ensure Deemix is available for the example to run
    if not DEEMIX_AVAILABLE:
        print("Deemix library not found. Example usage cannot proceed.")
    else:
        try:
            # Initialize the downloader.
            # It will prompt for ARL if not found in resources/deezer/deemix_credentials.json
            # By default, it looks for 'resources' in the current working directory.
            # Example: downloader = DeemixDownloader(config_dir_parent="/path/to/your/project_root")
            
            # You can customize download location and other deemix settings:
            # custom_settings = {"bitrate": "FLAC"} # Example
            # downloader = DeemixDownloader(download_root_dir="my_deezer_music", custom_deemix_settings=custom_settings)
            downloader = DeemixDownloader()

            if downloader.arl: # Check if ARL was successfully loaded/provided
                # Example: Search for a track and download it
                artist_to_search = "deadmau5"
                track_to_search = "Strobe" # A well-known track
                
                print(f"\nAttempting to search and download: {artist_to_search} - {track_to_search}")
                if downloader.search_and_download_track(artist_to_search, track_to_search):
                    print(f"Search and download process initiated for '{artist_to_search} - {track_to_search}'.")
                    print(f"Check your download folder: {downloader.download_root_dir.resolve()} and deemix output.")
                else:
                    print(f"Failed to find or initiate download for '{artist_to_search} - {track_to_search}'.")

            else:
                print("Could not obtain Deezer ARL. Download examples skipped.")
        except ImportError:
             print("Deemix library is not installed. Cannot run example.")
        except Exception as e:
            print(f"An error occurred during example execution: {e}")
        else:
            print("Could not obtain ARL. Download examples skipped.")