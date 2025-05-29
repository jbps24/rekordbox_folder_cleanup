import sqlite3
import os

class RekordboxLibrary:
    """
    A class to interact with a Rekordbox master.db file to extract track information.
    """

    def __init__(self, db_path=None):
        """
        Initializes the RekordboxLibrary class.

        Args:
            db_path (str, optional): The full path to the master.db file. 
                                     If not provided, it will try to locate it in the default
                                     Rekordbox data directories for Windows and macOS.
        """
        self.db_path = db_path if db_path else self._find_rekordbox_db()
        if not self.db_path or not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Could not find master.db at the specified path or default locations.")
        self.connection = None

    def _find_rekordbox_db(self):
        """
        Attempts to find the master.db file in the default Rekordbox locations.
        """
        home = os.path.expanduser('~')
        if os.name == 'nt':  # For Windows
            return os.path.join(home, 'AppData', 'Roaming', 'Pioneer', 'rekordbox', 'master.db')
        else:  # For macOS
            return os.path.join(home, 'Library', 'Pioneer', 'rekordbox', 'master.db')

    def connect(self):
        """
        Establishes a connection to the SQLite database.
        """
        try:
            self.connection = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            self.connection.row_factory = sqlite3.Row  # Access columns by name
            print(f"Successfully connected to {self.db_path}")
        except sqlite3.Error as e:
            print(f"Error connecting to database: {e}")
            self.connection = None

    def close(self):
        """
        Closes the database connection.
        """
        if self.connection:
            self.connection.close()
            self.connection = None
            print("Database connection closed.")

    def get_all_tracks(self):
        """
        Retrieves all tracks from the dj_PklsTrack table.

        Returns:
            list: A list of dictionaries, where each dictionary represents a track.
                  Returns an empty list if no tracks are found or an error occurs.
        """
        if not self.connection:
            print("Please connect to the database first.")
            return []

        tracks = []
        try:
            cursor = self.connection.cursor()
            # The primary table with track metadata is dj_PklsTrack
            cursor.execute("SELECT * FROM dj_PklsTrack")
            rows = cursor.fetchall()
            for row in rows:
                tracks.append(dict(row))
        except sqlite3.Error as e:
            print(f"An error occurred: {e}")
            # The table name might have changed in a newer Rekordbox version.
            # You might need to inspect the DB schema.
            print("Could not find the 'dj_PklsTrack' table. Please ensure you are using a valid Rekordbox database.")
        
        return tracks

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

if __name__ == '__main__':
    try:
        # The class will attempt to find the database in the default location.
        # If your master.db is elsewhere, provide the path like this:
        # rb_library = RekordboxLibrary(db_path='/path/to/your/master.db')
        
        with RekordboxLibrary() as rb_library:
            all_tracks = rb_library.get_all_tracks()

            if all_tracks:
                print(f"\nFound {len(all_tracks)} tracks in the library.")
                print("--- First 5 Tracks ---")
                for i, track in enumerate(all_tracks[:5]):
                    # These are some of the common column names.
                    # The exact column names can be explored by printing a full track dictionary.
                    artist = track.get('ArtistName', 'N/A')
                    title = track.get('TrackTitle', 'N/A')
                    album = track.get('AlbumName', 'N/A')
                    path = track.get('Path', 'N/A')
                    print(f"{i+1}. Artist: {artist}, Title: {title}, Album: {album}, Path: {path}")

                # To see all available data for the first track:
                if all_tracks:
                    print("\n--- All data for the first track ---")
                    print(all_tracks[0])

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")