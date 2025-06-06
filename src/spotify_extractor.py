import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import json # For handling config file
import re # For sanitizing filenames

class SpotifyClient:
    """
    A client to interact with the Spotify API, handling authentication
    and providing methods to access user data like playlists.
    Credentials are read from a config file or prompted if not found.
    """
    DEFAULT_CONFIG_DIR = "resources/spotify"
    CONFIG_FILE_NAME = "spotify_credentials.json"
    PLAYLIST_CONFIG_FILE_NAME = "spotify_playlists.json"
    PLAYLIST_TRACKS_SUBDIR = "playlist_tracks"

    def __init__(self, username=None, config_dir=None):
        """
        Initializes the SpotifyClient.

        Args:
            username (str, optional): Your Spotify username. Useful for cache management
                                      if multiple users might use this script. Defaults to None.
            config_dir (str, optional): Directory to store/read the Spotify credentials config file.
                                        Defaults to "resources/spotify".
        """
        self.username = username
        _config_dir = config_dir if config_dir is not None else self.DEFAULT_CONFIG_DIR
        self.credentials_config_file_path = os.path.join(_config_dir, self.CONFIG_FILE_NAME)
        self.playlists_config_file_path = os.path.join(_config_dir, self.PLAYLIST_CONFIG_FILE_NAME)
        self.playlist_tracks_dir = os.path.join(_config_dir, self.PLAYLIST_TRACKS_SUBDIR)
        
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = None
        
        self.sp = None  # This will hold the authenticated Spotipy instance

        # Attempt to load credentials on initialization, but don't prompt yet.
        # Prompting will happen during the first authenticate() call if needed.
        self._try_load_credentials()

    def authenticate(self, scope="playlist-read-private playlist-read-collaborative"):
        """
        Authenticates the user with Spotify using OAuth 2.0.
        Credentials will be loaded from config or prompted if not found.
        This method will open a browser window for user login and authorization
        the first time it's run or when the token is expired/invalid.

        Args:
            scope (str): A space-separated string of Spotify API scopes you need.
                         Defaults to scopes for reading private and collaborative playlists.

        Returns:
            bool: True if authentication was successful, False otherwise.
        """
        if not self._ensure_credentials_loaded():
            print("Authentication failed: Spotify API credentials are not available.")
            self.sp = None
            return False
        
        try:
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=scope,
                username=self.username,  # Helps in creating a user-specific cache file
                open_browser=True # Explicitly open browser, default is True
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            
            # Test authentication by fetching current user
            current_user = self.sp.current_user()
            if current_user:
                print(f"Successfully authenticated as: {current_user['display_name']} (ID: {current_user['id']})")
                return True
            else:
                # This case should ideally not be reached if auth_manager didn't raise an exception
                # and sp was initialized, but as a safeguard:
                print("Authentication seemed to succeed but could not fetch user details.")
                self.sp = None # Ensure sp is None if user details can't be fetched
                return False
        except Exception as e:
            print(f"Authentication failed: {e}")
            self.sp = None
            return False

    def _ensure_config_dir_exists(self):
        """Ensures the configuration directory exists."""
        # Ensures the directory containing the config files exists.
        # For simplicity, assuming both files are in the same directory.
        target_dir = os.path.dirname(self.credentials_config_file_path) # or self.playlists_config_file_path
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
                print(f"Created configuration directory: {target_dir}")
            except OSError as e:
                print(f"Error creating configuration directory {target_dir}: {e}")
                return False
        return True

    def _try_load_credentials(self):
        """
        Tries to load credentials from the config file.
        Returns True if successful, False otherwise.
        """
        if not os.path.exists(self.credentials_config_file_path):
            return False
        try:
            with open(self.credentials_config_file_path, 'r') as f:
                config = json.load(f)
            self.client_id = config.get("SPOTIPY_CLIENT_ID")
            self.client_secret = config.get("SPOTIPY_CLIENT_SECRET")
            self.redirect_uri = config.get("SPOTIPY_REDIRECT_URI")
            if self.client_id and self.client_secret and self.redirect_uri:
                print(f"Credentials loaded from {self.credentials_config_file_path}")
                return True
            else:
                print(f"Warning: Config file {self.credentials_config_file_path} is missing one or more credential keys.")
                self.client_id = self.client_secret = self.redirect_uri = None
                return False
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {self.credentials_config_file_path}.")
            return False
        except Exception as e:
            print(f"Error loading credentials from {self.credentials_config_file_path}: {e}")
            return False

    def _prompt_and_save_credentials(self):
        """
        Prompts the user for credentials and saves them to the config file.
        Returns True if credentials were obtained and saved, False otherwise.
        """
        print("Spotify API credentials not found or incomplete.")
        print("Please provide your Spotify App credentials.")
        print("You can create an app and find these at: https://developer.spotify.com/dashboard/applications")
        
        client_id = input("Enter your SPOTIPY_CLIENT_ID: ").strip()
        client_secret = input("Enter your SPOTIPY_CLIENT_SECRET: ").strip()
        redirect_uri = input("Enter your SPOTIPY_REDIRECT_URI (e.g., http://localhost:8888/callback): ").strip()

        if not all([client_id, client_secret, redirect_uri]):
            print("Error: All credential fields are required. Cannot save.")
            return False

        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        if not self._ensure_config_dir_exists():
            print("Cannot save credentials due to directory creation failure.")
            return False
            
        config_data = {
            "SPOTIPY_CLIENT_ID": self.client_id,
            "SPOTIPY_CLIENT_SECRET": self.client_secret,
            "SPOTIPY_REDIRECT_URI": self.redirect_uri
        }
        try:
            with open(self.credentials_config_file_path, 'w') as f:
                json.dump(config_data, f, indent=4)
            print(f"Credentials saved to {self.credentials_config_file_path}")
            return True
        except Exception as e:
            print(f"Error saving credentials to {self.credentials_config_file_path}: {e}")
            return False

    def _ensure_credentials_loaded(self):
        """
        Ensures credentials are loaded, trying from file first, then prompting if necessary.
        Returns True if credentials are set, False otherwise.
        """
        if self.client_id and self.client_secret and self.redirect_uri:
            return True # Already loaded
        
        if self._try_load_credentials():
            return True # Loaded from file successfully

        # If not loaded, prompt the user
        if self._prompt_and_save_credentials():
            return True # Prompted and saved successfully
        
        return False # Failed to get credentials

    def get_my_playlists(self):
        """
        Fetches all playlists for the currently authenticated user.

        Returns:
            list: A list of playlist dictionaries, each containing details like
                  'name', 'id', 'owner', and 'tracks_total'.
                  Returns None if not authenticated or an error occurs.
        """
        if not self.sp:
            print("Error: Not authenticated. Please call the authenticate() method first.")
            return None

        user_playlists = []
        try:
            offset = 0
            limit = 50 # Spotify API limit per request
            while True:
                results = self.sp.current_user_playlists(limit=limit, offset=offset)

                if not results:  # Check if results itself is None
                    print("Warning: Spotify API returned no result object for current_user_playlists.")
                    break
                
                if not results['items']: # Now it's safer to access 'items'
                    break # No items in the current page, or no playlists at all
                for item in results['items']:
                    user_playlists.append({
                        'name': item['name'],
                        'id': item['id'],
                        'owner': item['owner']['display_name'],
                        'tracks_total': item['tracks']['total'],
                        'uri': item['uri']
                    })
                offset += len(results['items'])
                if results['next'] is None: # No more pages
                    break # Also safe, as results is confirmed not to be None
            
            print(f"Found {len(user_playlists)} playlists.")
            return user_playlists
        except Exception as e:
            print(f"Error fetching playlists: {e}")
            return None

    def _sanitize_filename(self, name):
        """
        Sanitizes a string to be used as a valid filename.
        Removes or replaces invalid characters.
        """
        if not name:
            return "untitled"
        # Remove invalid characters
        name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
        # Replace whitespace with underscore
        name = re.sub(r'\s+', '_', name)
        # Truncate if too long (most filesystems have a limit around 255)
        return name[:100] # Keep it reasonably short

    def update_playlist_selection_file(self):
        """
        Fetches all user playlists and updates the spotify_playlists.json file.
        New playlists are added with "selected": False.
        Existing playlists retain their "selected" status.
        Playlists no longer on Spotify are removed from the file.

        Returns:
            bool: True if the file was updated successfully, False otherwise.
        """
        if not self.sp:
            print("Error: Not authenticated. Please call authenticate() before updating playlist file.")
            return False

        print("Fetching playlists from Spotify to update local selection file...")
        api_playlists_list = self.get_my_playlists()

        if api_playlists_list is None:
            print("Could not fetch playlists from Spotify. Playlist selection file not updated.")
            return False

        # Create a dictionary of API playlists for easy lookup by ID
        api_playlists_dict = {p['id']: p for p in api_playlists_list}

        existing_playlist_selections = {}
        if os.path.exists(self.playlists_config_file_path):
            try:
                with open(self.playlists_config_file_path, 'r') as f:
                    loaded_playlists = json.load(f)
                    for p in loaded_playlists:
                        if 'id' in p and 'selected' in p: # Ensure basic structure
                             existing_playlist_selections[p['id']] = p['selected']
                print(f"Loaded existing selections from {self.playlists_config_file_path}")
            except json.JSONDecodeError:
                print(f"Error decoding JSON from {self.playlists_config_file_path}. Will create a new file.")
            except Exception as e:
                print(f"Error loading {self.playlists_config_file_path}: {e}. Will create a new file.")

        updated_playlists_for_file = []
        for api_playlist_id, api_playlist_data in api_playlists_dict.items():
            # Preserve existing selection if playlist was already in the file, otherwise default to False
            selected_status = existing_playlist_selections.get(api_playlist_id, False)
            
            # Create the entry for the file, ensuring all necessary fields from API are present
            playlist_entry = api_playlist_data.copy() # Start with all data from API
            playlist_entry['selected'] = selected_status # Set/update selected status
            updated_playlists_for_file.append(playlist_entry)
        
        if not self._ensure_config_dir_exists(): # Ensures "resources/spotify" exists
            print("Cannot save playlist selection file due to directory creation failure.")
            return False
        try:
            with open(self.playlists_config_file_path, 'w') as f:
                json.dump(updated_playlists_for_file, f, indent=4)
            print(f"Playlist selection file updated successfully at {self.playlists_config_file_path}")
            return True
        except Exception as e:
            print(f"Error saving playlist selection file to {self.playlists_config_file_path}: {e}")
            return False

    def _ensure_playlist_tracks_dir_exists(self):
        """Ensures the playlist_tracks subdirectory exists."""
        if not os.path.exists(self.playlist_tracks_dir):
            try:
                os.makedirs(self.playlist_tracks_dir)
                print(f"Created directory for playlist tracks: {self.playlist_tracks_dir}")
            except OSError as e:
                print(f"Error creating directory {self.playlist_tracks_dir}: {e}")
                return False
        return True

    def get_playlist_tracks(self, playlist_id, playlist_name_for_logging="Unknown Playlist"):
        """
        Fetches all tracks for a given playlist ID.

        Args:
            playlist_id (str): The ID of the playlist.
            playlist_name_for_logging (str): The name of the playlist, for logging purposes.

        Returns:
            list: A list of track dictionaries, or None if an error occurs.
        """
        if not self.sp:
            print("Error: Not authenticated. Please call authenticate() first.")
            return None

        print(f"Fetching tracks for playlist: '{playlist_name_for_logging}' (ID: {playlist_id})")
        all_tracks = []
        offset = 0
        limit = 100 # Max limit for playlist_items is 100
        
        try:
            while True:
                results = self.sp.playlist_items(playlist_id, limit=limit, offset=offset, 
                                                 fields="items(added_at,track(name,id,uri,artists(name),album(name),duration_ms,track_number,disc_number,popularity,explicit,preview_url)),next")
                if not results or not results['items']:
                    break
                
                for item in results['items']:
                    track_info = item.get('track')
                    if track_info and track_info.get('id'): # Ensure track and its ID exist
                        artists = [artist['name'] for artist in track_info.get('artists', [])]
                        album_name = track_info.get('album', {}).get('name', 'N/A')
                        
                        all_tracks.append({
                            'name': track_info.get('name', 'N/A'),
                            'id': track_info['id'],
                            'uri': track_info.get('uri'),
                            'artists': artists,
                            'album': album_name,
                            'duration_ms': track_info.get('duration_ms'),
                            'track_number': track_info.get('track_number'),
                            'disc_number': track_info.get('disc_number'),
                            'popularity': track_info.get('popularity'),
                            'explicit': track_info.get('explicit'),
                            'preview_url': track_info.get('preview_url'),
                            'added_at': item.get('added_at')
                        })
                    else:
                        print(f"  Skipping an item in playlist '{playlist_name_for_logging}' as it has no track data or ID (possibly a local or deleted track). Item: {item}")

                offset += len(results['items'])
                if not results['next']:
                    break
            print(f"  Fetched {len(all_tracks)} tracks for playlist '{playlist_name_for_logging}'.")
            return all_tracks
        except Exception as e:
            print(f"Error fetching tracks for playlist '{playlist_name_for_logging}' (ID: {playlist_id}): {e}")
            return None

    def sync_selected_playlist_tracks(self):
        """
        For each playlist marked as "selected": true in spotify_playlists.json,
        fetches its tracks and saves them to a new JSON file in the playlist_tracks directory.
        """
        if not self.sp:
            print("Error: Not authenticated. Please call authenticate() first.")
            return False
        
        if not os.path.exists(self.playlists_config_file_path):
            print(f"Playlist selection file not found: {self.playlists_config_file_path}")
            print("Please run 'update_playlist_selection_file()' first and select playlists.")
            return False

        if not self._ensure_playlist_tracks_dir_exists():
            return False

        with open(self.playlists_config_file_path, 'r') as f:
            playlists_to_sync = json.load(f)

        for playlist in playlists_to_sync:
            if playlist.get("selected") is True:
                playlist_id = playlist.get("id")
                playlist_name = playlist.get("name", "Unknown Playlist")
                tracks = self.get_playlist_tracks(playlist_id, playlist_name)
                if tracks is not None: # Tracks could be an empty list, which is fine
                    sanitized_name = self._sanitize_filename(playlist_name)
                    filename = f"{playlist_id}_{sanitized_name}.json"
                    filepath = os.path.join(self.playlist_tracks_dir, filename)
                    try:
                        with open(filepath, 'w') as f_track:
                            json.dump(tracks, f_track, indent=4)
                        print(f"  Successfully saved tracks for '{playlist_name}' to {filepath}")
                    except Exception as e:
                        print(f"  Error saving tracks for '{playlist_name}' to {filepath}: {e}")
        print("Finished processing selected playlists.")
        return True

# --- Example Usage ---
# To use this class, you would do something like the following.
# Make sure to replace placeholder values with your actual Spotify API credentials.

# if __name__ == "__main__":
#     # Username is optional, helps with cache file naming if multiple users run this.
#     # You could get it from an environment variable, e.g.:
#     # SPOTIFY_USERNAME = os.getenv("SPOTIFY_USERNAME")

#     # Initialize the client. Credentials will be handled internally.
#     # spotify_dev_client = SpotifyClient(username=SPOTIFY_USERNAME)
#     #
#     # You can also specify a custom config directory:
#     # spotify_dev_client = SpotifyClient(username=SPOTIFY_USERNAME, config_dir="custom_spotify_config")
#     spotify_dev_client = SpotifyClient()
#
#     if spotify_dev_client.authenticate():
#         print("\nAttempting to update local playlist selection file...")
#         if spotify_dev_client.update_playlist_selection_file():
#             print("Local playlist file processed.")
#         else:
#             print("Failed to process local playlist file.")
#
#         spotify_dev_client.sync_selected_playlist_tracks()

#         # You can still fetch and print playlists if needed for other operations
#         # print("\nFetching your playlists (for display)...")
#         # playlists = spotify_dev_client.get_my_playlists()
#         # if playlists:
#         #     print("\n--- Your Spotify Playlists (from API) ---")
#         #     for i, playlist in enumerate(playlists):
#         #         print(f"{i+1}. Name: {playlist['name']}")
#         #         print(f"   ID: {playlist['id']}")
#         #         print(f"   Owner: {playlist['owner']}")
#         #         print(f"   Total Tracks: {playlist['tracks_total']}")
#         #         print(f"   URI: {playlist['uri']}")
#         #     print("-----------------------------")
#         # elif playlists is None: # Error occurred
#         #     print("Could not retrieve playlists due to an error.")
#         # else: # Empty list, no playlists
#         #     print("You have no playlists or they could not be retrieved.")
#     else:
#         print("Spotify authentication failed. Cannot proceed.")
if __name__ == "__main__":
    sp = SpotifyClient()
    sp.authenticate()
    # sp.update_playlist_selection_file() # Run this first to generate/update spotify_playlists.json
    # # Then, manually edit spotify_playlists.json to set "selected": true for desired playlists.
    sp.sync_selected_playlist_tracks() # Then run this to get tracks for selected playlists.