class DownloadManager:
    def __init__(self):
        self._storage = {} # may change this to Redis in future

    def add(self, download_id: str, data: dict):
        self._storage[download_id] = data

    def get_and_pop(self, download_id: str):
        return self._storage.pop(download_id, None)

dm_instance = DownloadManager() # singleton object