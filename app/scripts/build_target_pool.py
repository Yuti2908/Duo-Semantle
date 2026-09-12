import re

WORD_FORM = re.compile(r"^(?:[a-z]+|'[a-z]+)(?:['-]+[a-z]+)*'?$")
TOP_N = 15000

STOP_WORDS = {
    "a","an","the","and","or","but","if","of","at","by","for","with","about",
    "against","between","into","through","during","before","after","above",
    "below","to","from","up","down","in","out","on","off","over","under",
    "again","further","then","once","is","are","was","were","be","been",
    "being","have","has","had","having","do","does","did","doing","would",
    "should","could","ought","i","me","my","myself","we","our","ours",
    "ourselves","you","your","yours","yourself","yourselves","he","him",
    "his","himself","she","her","hers","herself","it","its","itself",
    "they","them","their","theirs","themselves","what","which","who",
    "whom","this","that","these","those","am","as","until","while","not",
    "no","nor","so","than","too","very","s","t","can","will","just","don",
    "now","d","ll","m","o","re","ve","y","ain","aren","couldn","didn",
    "doesn","hadn","hasn","haven","isn","ma","mightn","mustn","needn",
    "shan","shouldn","wasn","weren","won","wouldn","each","few","more",
    "most","other","some","such","own","same","there","here","when",
    "where","why","how","all","any","both","only",
}

with open("data/dictionary/words_full.txt", encoding="utf-8") as f:
    validated = set(line.strip() for line in f)

pool = []
with open("data/dictionary/count_1w.txt", encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) != 2:
            continue
        word, count = parts
        word = word.casefold()
        if word in STOP_WORDS:
            continue
        if word in validated and WORD_FORM.fullmatch(word):
            pool.append(word)
        if len(pool) >= TOP_N:
            break

with open("data/dictionary/target_pool.txt", "w", encoding="utf-8") as f:
    for w in pool:
        f.write(w + "\n")

print(f"Target pool: {len(pool)} words")
print(f"Sample (first 20): {pool[:20]}")
print(f"Sample (last 20): {pool[-20:]}")
