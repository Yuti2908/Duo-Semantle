import boto3
import os
import json

s3 = boto3.client('s3')
BUCKET = os.environ['BUCKET_NAME']
KEY = os.environ.get('WORDS_KEY', 'words.txt')
WORDS_PATH = '/tmp/words.txt'

valid_words = None

def load_words():
    global valid_words
    if valid_words is None:
        if not os.path.exists(WORDS_PATH):
            s3.download_file(BUCKET, KEY, WORDS_PATH)
        with open(WORDS_PATH, 'r', encoding='utf-8') as f:
            valid_words = set(line.strip() for line in f)
    return valid_words

def handler(event, context):
    params = event.get('queryStringParameters') or {}
    word = params.get('word', '')
    word = word.strip().casefold()

    if not word:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "missing 'word' query parameter"})
        }

    words = load_words()
    return {
        "statusCode": 200,
        "body": json.dumps({"word": word, "valid": word in words})
    }
