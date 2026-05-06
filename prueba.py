import feedparser
feed = feedparser.parse('https://lunmas.cl/feed/')
print('Entradas:', len(feed.entries))
for e in feed.entries[:10]:
    print(' -', e.get('title','?')[:80])
    print('  ', e.get('published','?')[:30])