import boto3
import os
import json
import random
import numpy as np
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from boto3.dynamodb.conditions import Key

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

WORDS_BUCKET = os.environ['WORDS_BUCKET']
EMBEDDINGS_BUCKET = os.environ['EMBEDDINGS_BUCKET']
EMBEDDINGS_PREFIX = os.environ.get('EMBEDDINGS_PREFIX', 'embeddings/')
TABLE_NAME = os.environ['TABLE_NAME']
POOL_KEY = os.environ.get('POOL_KEY', 'target_pool.txt')

REPEAT_WINDOW_DAYS = 30
DISSIMILARITY_THRESHOLD = 0.15
CANDIDATE_SAMPLE_SIZE = 40
RANK_TABLE_SIZE = 1000

TMP_POOL = '/tmp/target_pool.txt'
TMP_EMBEDDINGS_DIR = '/tmp/embeddings'

table = dynamodb.Table(TABLE_NAME)
_partition_cache = {}
_full_vocab_cache = None


def load_pool():
    if not os.path.exists(TMP_POOL):
        s3.download_file(WORDS_BUCKET, POOL_KEY, TMP_POOL)
    with open(TMP_POOL, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def partition_name(word):
    letters = ''.join(c for c in word.casefold() if 'a' <= c <= 'z')
    return letters[:2] if len(letters) >= 2 else '__'


def load_partition(name):
    if name in _partition_cache:
        return _partition_cache[name]

    os.makedirs(TMP_EMBEDDINGS_DIR, exist_ok=True)
    local_path = f'{TMP_EMBEDDINGS_DIR}/{name}.bin'
    if not os.path.exists(local_path):
        try:
            s3.download_file(EMBEDDINGS_BUCKET, f'{EMBEDDINGS_PREFIX}{name}.bin', local_path)
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


def list_all_partition_keys():
    keys = []
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=EMBEDDINGS_BUCKET, Prefix=EMBEDDINGS_PREFIX):
        for obj in page.get('Contents', []):
            if obj['Key'].endswith('.bin'):
                keys.append(obj['Key'])
    return keys


def download_partition_file(key):
    local_path = f"{TMP_EMBEDDINGS_DIR}/{key.split('/')[-1]}"
    if not os.path.exists(local_path):
        s3.download_file(EMBEDDINGS_BUCKET, key, local_path)
    return local_path


def load_full_vocabulary():
    global _full_vocab_cache
    if _full_vocab_cache is not None:
        return _full_vocab_cache

    os.makedirs(TMP_EMBEDDINGS_DIR, exist_ok=True)
    keys = list_all_partition_keys()

    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = [executor.submit(download_partition_file, key) for key in keys]
        local_paths = [f.result() for f in as_completed(futures)]

    all_words = []
    all_vectors = []
    for path in local_paths:
        with open(path, 'rb') as f:
            archive = np.load(f, allow_pickle=False)
            words = archive['words']
            vectors = archive['vectors']
        all_words.extend(str(w) for w in words)
        all_vectors.append(vectors.astype(np.float32, copy=False))

    matrix = np.vstack(all_vectors)
    _full_vocab_cache = (all_words, matrix)
    return _full_vocab_cache


def compute_rank_table(target_word):
    words, matrix = load_full_vocabulary()
    if target_word not in words:
        return []

    target_idx = words.index(target_word)
    target_vec = matrix[target_idx]

    norms = np.linalg.norm(matrix, axis=1)
    target_norm = np.linalg.norm(target_vec)

    valid_mask = norms > 0
    dots = matrix @ target_vec
    similarities = np.full(len(words), -2.0, dtype=np.float32)
    similarities[valid_mask] = dots[valid_mask] / (norms[valid_mask] * target_norm)

    ranked_indices = np.argsort(-similarities)[:RANK_TABLE_SIZE]
    return [{'word': words[i], 'score': round(float(similarities[i]), 4)} for i in ranked_indices]


def recently_used_words(as_of):
    cutoff = (as_of - timedelta(days=REPEAT_WINDOW_DAYS)).isoformat()
    response = table.query(
        KeyConditionExpression=Key('pk').eq('target') & Key('date').gte(cutoff)
    )
    used = set()
    for item in response.get('Items', []):
        used.add(item['target_a'])
        used.add(item['target_b'])
    return used


def select_targets(pool, excluded):
    eligible = [w for w in pool if w not in excluded]
    if len(eligible) < 2:
        raise RuntimeError("Not enough eligible words left in the pool.")

    random.shuffle(eligible)

    target_a = None
    vec_a = None
    for word in eligible:
        vec = vector_for(word)
        if vec is not None:
            target_a = word
            vec_a = vec
            break
    if target_a is None:
        raise RuntimeError("No eligible word in the pool has an embedding.")

    candidates = [w for w in eligible if w != target_a]
    random.shuffle(candidates)
    candidates = candidates[:CANDIDATE_SAMPLE_SIZE]

    scored = []
    for word in candidates:
        vec_b = vector_for(word)
        if vec_b is None:
            continue
        sim = cosine_similarity(vec_a, vec_b)
        scored.append((word, sim))

    below_threshold = [w for w, sim in scored if sim < DISSIMILARITY_THRESHOLD]
    if below_threshold:
        target_b = random.choice(below_threshold)
    else:
        scored.sort(key=lambda pair: pair[1])
        target_b = scored[0][0]

    return target_a, target_b


def handler(event, context):
    today = date.today()

    pool = load_pool()
    excluded = recently_used_words(today)
    target_a, target_b = select_targets(pool, excluded)

    vec_a = vector_for(target_a)
    vec_b = vector_for(target_b)
    similarity = cosine_similarity(vec_a, vec_b)

    rank_table_a = compute_rank_table(target_a)
    rank_table_b = compute_rank_table(target_b)

    item = {
        'pk': 'target',
        'date': today.isoformat(),
        'target_a': target_a,
        'target_b': target_b,
        'similarity': str(round(similarity, 4)),
        'rank_table_a': [{'word': r['word'], 'score': str(r['score'])} for r in rank_table_a],
        'rank_table_b': [{'word': r['word'], 'score': str(r['score'])} for r in rank_table_b],
    }
    table.put_item(Item=item)

    return {
        'statusCode': 200,
        'body': json.dumps({
            'date': today.isoformat(),
            'target_a': target_a,
            'target_b': target_b,
            'similarity': round(similarity, 4),
            'rank_table_a_size': len(rank_table_a),
            'rank_table_b_size': len(rank_table_b),
        })
    }
