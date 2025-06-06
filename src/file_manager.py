import json
import os
from urllib.parse import urlparse, unquote
import unicodedata  # <--- IMPORT ADDED

class FileManager:
    """
    Manages audio files in a target folder based on a Rekordbox track list.
    It can identify and delete audio files not present in the provided track list.
    """
    def __init__(self, tracks_json_path, target_folder_path):
        """
        Initializes the FileManager.

        Args:
            tracks_json_path (str): Path to the JSON file containing track data
                                    (e.g., from RekordBoxLibraryExtractor).
            target_folder_path (str): Path to the folder to scan for audio files.
        """
        self.tracks_json_path = tracks_json_path
        self.target_folder_path = os.path.abspath(target_folder_path)
        self.audio_extensions = ('.mp3', '.wav', '.flac')
        self.rekordbox_file_paths = self._load_rekordbox_paths()

    def _uri_to_path(self, uri_string):
        """
        Converts a file URI (e.g., from Rekordbox XML Location field)
        to a normalized absolute file system path, fixing Unicode differences.

        Args:
            uri_string (str): The file URI.

        Returns:
            str or None: The normalized absolute path, or None if conversion fails.
        """
        if not uri_string:
            return None
        try:
            parsed_uri = urlparse(uri_string)
            if parsed_uri.scheme != 'file':
                return None

            decoded_path = unquote(parsed_uri.path)
            abs_path = os.path.abspath(decoded_path)
            norm_path = os.path.normpath(abs_path)
            
            # --- FIX APPLIED HERE ---
            # Normalize the Unicode representation to 'NFC' (composed).
            # This handles filesystem differences, e.g., macOS using NFD (decomposed)
            # characters in filenames, while the XML/JSON uses NFC.
            return unicodedata.normalize('NFC', norm_path)
            
        except ValueError as e:
            print(f"Warning: Could not parse URI '{uri_string}': {e}")
            return None
        except Exception as e:
            print(f"Warning: Unexpected error converting URI '{uri_string}': {e}")
            return None

    def _load_rekordbox_paths(self):
        """
        Loads track locations from the JSON file, decodes them from URI format,
        and stores them as a set of normalized absolute paths.
        """
        rekordbox_paths = set()
        try:
            with open(self.tracks_json_path, 'r', encoding='utf-8') as f:
                tracks_data = json.load(f)
            
            if not isinstance(tracks_data, list):
                print(f"Error: Expected a list of tracks in '{self.tracks_json_path}', but got {type(tracks_data)}.")
                return rekordbox_paths

            for track in tracks_data:
                location_uri = track.get("Location")
                if location_uri:
                    path = self._uri_to_path(location_uri)
                    if path:
                        rekordbox_paths.add(path)
                        
        except FileNotFoundError:
            print(f"Error: Tracks JSON file not found at '{self.tracks_json_path}'.")
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from '{self.tracks_json_path}'.")
        except Exception as e:
            print(f"An unexpected error occurred while loading Rekordbox paths: {e}")
        
        return rekordbox_paths

    def find_unlisted_audio_files(self):
        """
        Scans the target folder for audio files and returns a list of those
        not found in the Rekordbox track list after normalizing for Unicode differences.
        """
        if not os.path.isdir(self.target_folder_path):
            print(f"Error: Target folder '{self.target_folder_path}' does not exist or is not a directory.")
            return []

        unlisted_files = []
        print(f"Scanning '{self.target_folder_path}' for audio files...")
        for root, _, files in os.walk(self.target_folder_path):
            for filename in files:
                if filename.lower().endswith(self.audio_extensions):
                    file_path_on_disk = os.path.abspath(os.path.join(root, filename))
                    normalized_disk_path = os.path.normpath(file_path_on_disk)
                    
                    # --- FIX APPLIED HERE ---
                    # Normalize the path from the disk to NFC for a consistent comparison.
                    comparison_path = unicodedata.normalize('NFC', normalized_disk_path)
                    
                    if comparison_path not in self.rekordbox_file_paths:
                        # Add the original, non-normalized path to the list for deletion.
                        unlisted_files.append(normalized_disk_path)
        
        print(f"Found {len(unlisted_files)} unlisted audio files.")
        return unlisted_files

    def manage_unlisted_files(self, dry_run=True, dry_run_output_json="files_to_delete.json"):
        """
        Manages unlisted audio files.
        If dry_run is True, creates a JSON file listing files that would be deleted.
        If dry_run is False, attempts to delete the unlisted files.

        Args:
            dry_run (bool): If True, only lists files for deletion. If False, deletes them.
            dry_run_output_json (str): Path for the JSON file in dry run mode.
        """
        files_to_action = self.find_unlisted_audio_files()

        if not files_to_action:
            print("No unlisted audio files found to manage.")
            return

        if dry_run:
            abs_dry_run_output_path = os.path.abspath(dry_run_output_json)
            try:
                output_dir = os.path.dirname(abs_dry_run_output_path)
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)

                with open(abs_dry_run_output_path, 'w', encoding='utf-8') as f:
                    json.dump(files_to_action, f, indent=4, ensure_ascii=False)
                print(f"Dry run complete. {len(files_to_action)} files that would be deleted are listed in '{abs_dry_run_output_path}'.")
            except IOError as e:
                print(f"Error writing dry run JSON file '{abs_dry_run_output_path}': {e}")
        else:
            deleted_count = 0
            failed_to_delete = []
            print(f"\n--- Attempting to delete {len(files_to_action)} unlisted audio files ---")
            confirm = input(f"Are you sure you want to PERMANENTLY DELETE {len(files_to_action)} files from '{self.target_folder_path}'? (yes/no): ")
            if confirm.lower() != 'yes':
                print("Deletion cancelled by user.")
                return

            for file_path in files_to_action:
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}")
                    deleted_count += 1
                except OSError as e:
                    print(f"Error deleting file '{file_path}': {e}")
                    failed_to_delete.append(file_path)
            
            print(f"\n--- Deletion Summary ---")
            print(f"Successfully deleted: {deleted_count} files.")
            if failed_to_delete:
                print(f"Failed to delete: {len(failed_to_delete)} files.")
            print("Deletion process complete.")

# In another script, or at the end of file_manager.py (outside the class)
if __name__ == "__main__":
    # --- USER CONFIGURATION ---
    rekordbox_tracks_file = "resources/rekordbox/extracted_unique_tracks.json"
    music_folder_to_scan = "/Volumes/Samsung_T5/Privat/Musik"
    dry_run_report_file = "files_that_would_be_deleted.json"
    # --- END USER CONFIGURATION ---

    if not os.path.exists(rekordbox_tracks_file):
        print(f"Error: Rekordbox tracks JSON file not found: {rekordbox_tracks_file}")
    elif not os.path.isdir(music_folder_to_scan):
        print(f"Error: Music folder to scan not found or not a directory: {music_folder_to_scan}")
    else:
        manager = FileManager(tracks_json_path=rekordbox_tracks_file, 
                              target_folder_path=music_folder_to_scan)

        # Perform a dry run first to see what would be deleted
        print("\n--- Performing DRY RUN ---")
        manager.manage_unlisted_files(dry_run=True, dry_run_output_json=dry_run_report_file)
        print(f"Review '{os.path.abspath(dry_run_report_file)}' before actual deletion.")

        # # To perform actual deletion (USE WITH EXTREME CAUTION):
        # print("\n--- Performing ACTUAL DELETION ---")
        # # The manage_unlisted_files method will ask for confirmation again.
        # manager.manage_unlisted_files(dry_run=False)