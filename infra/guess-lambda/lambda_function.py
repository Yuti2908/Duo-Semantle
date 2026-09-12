import boto3
import os
import json
from datetime import datetime, timezone
from decimal import Decimal
from boto3.dynamodb.conditions import Key

from duo_semantle_common.validation import is_valid_word
from duo_semantle_common.scoring import cosine_similarity, semantle_score
from duo_semantle_common.embeddings import EmbeddingLookup

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

WORDS_BUCKET = os.environ['WORDS_BUCKET']
WORDS_KEY = os.environ.get('WORDS_KEY', 'words.txt')
EMBEDDINGS_BUCKET = os.environ['EMBEDDINGS_BUCKET']
EMBEDDINGS_PREFIX = os.environ.get('EMBEDDINGS_PREFIX', 'embeddings/')
TARGETS_TABLE_NAME = os.environ['TARGETS_TABLE_NAME']
GUESSES_TABLE_NAME = os.environ['GUESSES_TABLE_NAME']

TMP_WORDS_PATH = '/tmp/words.txt'
TMP_EMBEDDINGS_DIR = '/tmp/embeddings'

targets_table_ref = dynamodb.Table(TARGETS_TABLE_NAME)
guesses_table_ref = dynamodb.Table(GUESSES_TABLE_NAME)
embeddings = EmbeddingLookup(s3, EMBEDDINGS_BUCKET, EMBEDDINGS_PREFIX, TMP_EMBEDDINGS_DIR)

_word_set_cache = None

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Allow-Methods': '*',
}


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, default=str),
    }


def load_word_set():
    global _word_set_cache
    if _word_set_cache is None:
        if not os.path.exists(TMP_WORDS_PATH):
            s3.download_file(WORDS_BUCKET, WORDS_KEY, TMP_WORDS_PATH)
        with open(TMP_WORDS_PATH, 'r', encoding='utf-8') as f:
            _word_set_cache = set(line.strip() for line in f)
    return _word_set_cache


def get_todays_targets():
    today = datetime.now(timezone.utc).date().isoformat()
    resp = targets_table_ref.get_item(Key={'pk': 'target', 'date': today})
    item = resp.get('Item')
    if not item:
        raise RuntimeError(f"No targets configured for {today}")
    return item['target_a'], item['target_b']


def get_session_history(session_id):
    resp = guesses_table_ref.query(
        KeyConditionExpression=Key('session_id').eq(session_id)
    )
    items = resp.get('Items', [])
    items.sort(key=lambda g: max(float(g['score_a']), float(g['score_b'])), reverse=True)
    return items


def handler(event, context):
    params = event.get('queryStringParameters') or {}
    session_id = params.get('session_id', '')
    guess = params.get('guess', '')

    if not session_id or not guess:
        return response(400, {'error': "both 'session_id' and 'guess' query parameters are required"})

    guess = guess.strip().casefold()
    word_set = load_word_set()

    if not is_valid_word(guess, word_set):
        return response(200, {'valid': False, 'reason': 'not a valid English word'})

    target_a, target_b = get_todays_targets()

    guess_vec = embeddings.vector_for(guess)
    if guess_vec is None:
        return response(200, {'valid': True, 'scored': False, 'reason': 'embedding unavailable'})

    vec_a = embeddings.vector_for(target_a)
    vec_b = embeddings.vector_for(target_b)

    sim_a = cosine_similarity(guess_vec, vec_a)
    sim_b = cosine_similarity(guess_vec, vec_b)
    score_a = semantle_score(sim_a)
    score_b = semantle_score(sim_b)

    timestamp = datetime.now(timezone.utc).isoformat()
    guesses_table_ref.put_item(Item={
        'session_id': session_id,
        'timestamp': timestamp,
        'word': guess,
        'score_a': Decimal(str(score_a)),
        'score_b': Decimal(str(score_b)),
    })

    history = get_session_history(session_id)

    return response(200, {
        'valid': True,
        'scored': True,
        'word': guess,
        'score_a': score_a,
        'score_b': score_b,
        'history': [
            {
                'word': g['word'],
                'score_a': float(g['score_a']),
                'score_b': float(g['score_b']),
                'timestamp': g['timestamp'],
            }
            for g in history
        ],
    })
