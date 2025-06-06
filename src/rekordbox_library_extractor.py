import xml.etree.ElementTree as ET
import json
import os

class RekordBoxLibraryExtractor:
    """
    Extracts and manages playlist and track information from a Rekordbox XML library,
    allowing for selective track retrieval based on playlist configuration.
    """
    def __init__(self, resource_dir="resources/rekordbox", 
                 library_xml_filename="library.xml", 
                 config_json_filename="rekordbox_config.json"):
        """
        Initializes the extractor with paths for resources.

        Args:
            resource_dir (str): Directory containing Rekordbox files.
            library_xml_filename (str): Name of the Rekordbox XML library file.
            config_json_filename (str): Name of the output JSON configuration file.
        """
        self.resource_dir = resource_dir
        self.library_xml_path = os.path.join(self.resource_dir, library_xml_filename)
        self.config_json_path = os.path.join(self.resource_dir, config_json_filename)
        
        # Ensure resource directory exists
        os.makedirs(self.resource_dir, exist_ok=True)

    def _get_xml_root(self):
        """Parses the XML file and returns the root element."""
        try:
            tree = ET.parse(self.library_xml_path)
            return tree.getroot()
        except (ET.ParseError, FileNotFoundError) as e:
            print(f"Error reading or parsing XML file at {self.library_xml_path}: {e}")
            return None

    def _extract_all_playlist_names_from_xml(self, root):
        """
        Extracts all playlist names (NODE Type="1") from the Rekordbox library XML.

        Args:
            root: The root ElementTree element of the XML file.

        Returns:
            list: A list of all playlist names. Returns an empty list if root is None or no playlists are found.
        """
        if root is None:
            return []
            
        playlist_names = []
        # Correct XPath to find all NODE elements with Type="1" (playlists)
        # anywhere under the PLAYLISTS tag.
        playlists_element = root.find('PLAYLISTS')
        if playlists_element is None:
            return []
        playlist_nodes = playlists_element.findall('.//NODE[@Type="1"]')
        for node in playlist_nodes:
            name = node.get('Name')
            if name:
                playlist_names.append(name)
        return playlist_names

    def update_playlist_config_json(self):
        """
        Creates or updates a JSON config file. It preserves existing playlist settings
        and adds new playlists found in the XML with a default value of 'true'.
        """
        root = self._get_xml_root()
        if not root:
            return

        playlist_names = self._extract_all_playlist_names_from_xml(root)
        
        # Load existing config if it exists
        try:
            with open(self.config_json_path, 'r') as f:
                playlist_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            playlist_config = {}

        # Add new playlists with a default value of True
        new_playlists_added = False
        for name in playlist_names:
            if name not in playlist_config:
                playlist_config[name] = True
                new_playlists_added = True

        # Write the updated config back to the file
        try:
            with open(self.config_json_path, 'w') as f:
                json.dump(playlist_config, f, indent=2, sort_keys=True)
            if new_playlists_added:
                print(f"Successfully updated playlist configuration: {self.config_json_path}")
            else:
                print(f"Playlist configuration is already up-to-date: {self.config_json_path}")

        except IOError:
            print(f"Error: Could not write to JSON file at {self.config_json_path}")
            
    def get_unique_tracks_from_selected_playlists(self):
        """
        Reads the config JSON, and for every playlist set to 'true',
        extracts all unique tracks (across all selected playlists) and their details.

        Returns:
            list: A list of dictionaries, where each dictionary represents a track.
                  Returns an empty list if no playlists are selected, on XML error, or config error.
        """
        try:
            with open(self.config_json_path, 'r') as f:
                playlist_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Error: Could not load config file at '{self.config_json_path}'. "
                  "Please run update_playlist_config_json() first.")
            return []

        selected_playlists = {name for name, selected in playlist_config.items() if selected}
        
        if not selected_playlists:
            print("No playlists are selected (set to 'true') in the config file.")
            return []

        root = self._get_xml_root()
        if not root:
            return []

        # Create a dictionary of all tracks in the collection for fast lookups
        track_collection = {
            track.get('TrackID'): {
                'Name': track.get('Name'),
                'Artist': track.get('Artist'),
                'Album': track.get('Album'),
                'Genre': track.get('Genre'),
                'TotalTime': track.get('TotalTime'),
                'Year': track.get('Year'),
                'AverageBpm': track.get('AverageBpm'),
                'Location': track.get('Location'),
                'TrackID': track.get('TrackID')
            } 
            for track in root.findall('.//COLLECTION/TRACK')
        }

        all_tracks = []
        processed_track_ids = set()

        playlists_element = root.find('PLAYLISTS')
        if playlists_element is None: return []
        for node in playlists_element.findall('.//NODE[@Type="1"]'): # Corrected XPath
            playlist_name = node.get('Name')
            if playlist_name in selected_playlists:
                track_keys = node.findall('TRACK')
                for track in track_keys:
                    track_id = track.get('Key')
                    if track_id and track_id not in processed_track_ids:
                        track_details = track_collection.get(track_id)
                        if track_details:
                            all_tracks.append(track_details)
                            processed_track_ids.add(track_id)
        
        print(f"Found {len(all_tracks)} unique tracks in {len(selected_playlists)} selected playlists.")
        return all_tracks

    def get_tracks_per_selected_playlist(self):
        """
        Reads the config JSON, and for every playlist set to 'true',
        extracts all tracks and their details, organized by playlist.

        Returns:
            dict: A dictionary where keys are selected playlist names and
                  values are lists of track dictionaries for that playlist.
                  Returns an empty dictionary on error or if no playlists are selected.
        """
        try:
            with open(self.config_json_path, 'r') as f:
                playlist_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Error: Could not load config file at '{self.config_json_path}'. "
                  "Please run update_playlist_config_json() first.")
            return {}

        selected_playlists_names = {name for name, selected in playlist_config.items() if selected}
        
        if not selected_playlists_names:
            print("No playlists are selected (set to 'true') in the config file.")
            return {}

        root = self._get_xml_root()
        if not root:
            return {}

        track_collection = {
            track.get('TrackID'): {attr: track.get(attr) for attr in ['Name', 'Artist', 'Album', 'Genre', 'TotalTime', 'Year', 'AverageBpm', 'Location', 'TrackID']}
            for track in root.findall('.//COLLECTION/TRACK')
        }

        tracks_by_playlist = {}
        playlists_element = root.find('PLAYLISTS')
        if playlists_element is None: return {}
        for node in playlists_element.findall('.//NODE[@Type="1"]'): # Corrected XPath
            playlist_name = node.get('Name')
            if playlist_name in selected_playlists_names:
                current_playlist_tracks = []
                for track_node in node.findall('TRACK'):
                    track_id = track_node.get('Key')
                    if track_id and track_collection.get(track_id):
                        current_playlist_tracks.append(track_collection[track_id])
                tracks_by_playlist[playlist_name] = current_playlist_tracks
        return tracks_by_playlist


if __name__ == "__main__":
    # This is an example of how to use the class.
    # --- STEP 1 ---
    # Create an instance of the extractor.
    # IMPORTANT: Make sure your Rekordbox XML is named 'library.xml' and located in the 'resources/rekordbox' directory.
    # If your files have different names, pass them to the constructor, e.g.:
    # extractor = RekordBoxLibraryExtractor(library_xml_filename="my_export.xml", config_json_filename="my_config.json")
    extractor = RekordBoxLibraryExtractor()
    
    # --- STEP 2 ---
    # Update the JSON configuration file.
    # This will create the file if it doesn't exist, or add new playlists if it does.
    extractor.update_playlist_config_json()
    
    print("\n--- ACTION REQUIRED ---")
    print(f"Please review and edit '{extractor.config_json_path}'.")
    print("Set the playlists you want to process to 'true' and others to 'false'.\n")
    input("Press Enter to continue after you have saved the configuration file...")

    # --- STEP 3 ---
    # Extract all unique tracks from the playlists marked as 'true' in the config.
    unique_selected_tracks = extractor.get_unique_tracks_from_selected_playlists()
    
    # --- STEP 4 ---
    # You can now process the list of unique tracks. Here, we'll just print the first 5.
    if unique_selected_tracks:
        print(f"\n--- First 5 Unique Tracks from All Selected Playlists ---")
        for i, track in enumerate(unique_selected_tracks[:5]):
            print(f"  {i+1}. Artist: {track['Artist']}, Title: {track['Name']}, BPM: {track['AverageBpm']}")
        
        # Example of saving the full list to a separate JSON file
        output_unique_tracks_path = os.path.join(extractor.resource_dir, "extracted_unique_tracks.json")
        try:
            with open(output_unique_tracks_path, 'w') as f:
                json.dump(unique_selected_tracks, f, indent=2, sort_keys=True)
            print(f"\nSuccessfully saved all {len(unique_selected_tracks)} unique tracks to '{output_unique_tracks_path}'")
        except IOError:
            print(f"Error: Could not write unique tracks to {output_unique_tracks_path}")

    # --- STEP 5 ---
    # Extract tracks per selected playlist.
    tracks_per_playlist = extractor.get_tracks_per_selected_playlist()
    if tracks_per_playlist:
        print(f"\n--- Tracks per Selected Playlist (Summary) ---")
        for playlist_name, tracks in tracks_per_playlist.items():
            print(f"Playlist: '{playlist_name}' contains {len(tracks)} tracks.")
            # Optionally print first few tracks of each playlist
            # for i, track in enumerate(tracks[:2]): # Print first 2 tracks as example
            #     print(f"  {i+1}. {track['Artist']} - {track['Name']}")
        output_per_playlist_path = os.path.join(extractor.resource_dir, "extracted_tracks_per_playlist.json")
        try:
            with open(output_per_playlist_path, 'w') as f:
                json.dump(tracks_per_playlist, f, indent=2, sort_keys=True)
            print(f"\nSuccessfully saved tracks per playlist to '{output_per_playlist_path}'")
        except IOError:
            print(f"Error: Could not write tracks per playlist to {output_per_playlist_path}")