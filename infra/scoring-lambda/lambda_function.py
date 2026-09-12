import boto3
import os
import json
import numpy as np

s3 = boto3.client('s3')
BUCKET = os.environ['BUCKET_NAME']
PREFIX = os.environ.get('EMBEDDINGS_PREFIX', 'embeddings/')
TMP_DIR = '/tmp/embeddings'

_partition_cache = {}


def partition_name(word):
    letters = ''.join(c for c in word.casefold() if 'a' <= c <= 'z')
    return letters[:2] if len(letters) >= 2 else '__'


def load_partition(name):
    if name in _partition_cache:
        return _partition_cache[name]

    os.makedirs(TMP_DIR, exist_ok=True)
    local_path = f'{TMP_DIR}/{name}.bin'
    if not os.path.exists(local_path):
        try:
            s3.download_file(BUCKET, f'{PREFIX}{name}.bin', local_path)
        except s3.exceptions.ClientError:
            _partition_cache[name] = {}
            return {}

    with open(local_path, 'rb') as f:
        archive = np.load(f, allow_pickle=False)
        words, vectors = archive['words'], archive['vectors']

    partition = {str(w): vectors[i].astype(np.float64, copy=False) for i, w in enumerate(words)}
    _partition_cache[name] = partition
    return partition


def vector_for(word):
    word = word.strip().casefold()
    return load_partition(partition_name(word)).get(word)


def cosine_similarity(a, b):
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return None
    return float(np.dot(a, b) / denom)


def handler(event, context):
    params = event.get('queryStringParameters') or {}
    guess = params.get('guess', '')
    target = params.get('target', '')

    if not guess or not target:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "both 'guess' and 'target' query parameters are required"})
        }

    guess_vec = vector_for(guess)
    target_vec = vector_for(target)

    if guess_vec is None or target_vec is None:
        return {
            'statusCode': 200,
            'body': json.dumps({'guess': guess, 'target': target, 'scored': False, 'reason': 'embedding unavailable'})
        }

    similarity = cosine_similarity(guess_vec, target_vec)
    bounded = min(1.0, max(-1.0, similarity))
    score = round(bounded * 100, 2)

    return {
        'statusCode': 200,
        'body': json.dumps({'guess': guess, 'target': target, 'scored': True, 'similarity': round(similarity, 4), 'score': score})
    }
