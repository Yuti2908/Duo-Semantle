import os
import numpy as np


def partition_name(word):
    letters = ''.join(c for c in word.casefold() if 'a' <= c <= 'z')
    return letters[:2] if len(letters) >= 2 else '__'


class EmbeddingLookup:
    """Lazy S3-backed partition loader with an in-memory cache."""

    def __init__(self, s3_client, bucket, prefix, tmp_dir):
        self.s3 = s3_client
        self.bucket = bucket
        self.prefix = prefix
        self.tmp_dir = tmp_dir
        self._cache = {}

    def load_partition(self, name):
        if name in self._cache:
            return self._cache[name]

        os.makedirs(self.tmp_dir, exist_ok=True)
        local_path = f'{self.tmp_dir}/{name}.bin'
        if not os.path.exists(local_path):
            try:
                self.s3.download_file(self.bucket, f'{self.prefix}{name}.bin', local_path)
            except self.s3.exceptions.ClientError:
                self._cache[name] = {}
                return {}

        with open(local_path, 'rb') as f:
            archive = np.load(f, allow_pickle=False)
            words, vectors = archive['words'], archive['vectors']

        partition = {str(w): vectors[i].astype(np.float64, copy=False) for i, w in enumerate(words)}
        self._cache[name] = partition
        return partition

    def vector_for(self, word):
        word = word.strip().casefold()
        return self.load_partition(partition_name(word)).get(word)
