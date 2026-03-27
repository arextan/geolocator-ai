import duckdb

con = duckdb.connect('geoguessr.db', read_only=True)

print('=== OVERVIEW ===')
print('total rounds:', con.execute('SELECT COUNT(*) FROM rounds').fetchone()[0])
print('failed extractions:', con.execute('SELECT COUNT(*) FROM rounds WHERE extraction_failed = true').fetchone()[0])

print('\n=== SCORE DISTRIBUTION ===')
print('avg score:', con.execute('SELECT ROUND(AVG(geoguessr_score),0) FROM rounds WHERE geoguessr_score IS NOT NULL').fetchone()[0])
print('median score:', con.execute('SELECT ROUND(MEDIAN(geoguessr_score),0) FROM rounds WHERE geoguessr_score IS NOT NULL').fetchone()[0])
print('scores > 4000:', con.execute('SELECT COUNT(*) FROM rounds WHERE geoguessr_score > 4000').fetchone()[0])
print('scores < 500:', con.execute('SELECT COUNT(*) FROM rounds WHERE geoguessr_score < 500').fetchone()[0])

print('\n=== PATH DISTRIBUTION ===')
for row in con.execute('SELECT path_taken, COUNT(*), ROUND(AVG(geoguessr_score),0) FROM rounds GROUP BY path_taken').fetchall():
    print(f'  {row[0]}: {row[1]} rounds, avg {row[2]} pts')

print('\n=== GUESS CONFIDENCE BUCKETS ===')
for row in con.execute("""
    SELECT
        CASE
            WHEN guess_confidence >= 0.7 THEN 'high (>=0.7)'
            WHEN guess_confidence >= 0.4 THEN 'medium (0.4-0.7)'
            WHEN guess_confidence IS NOT NULL THEN 'low (<0.4)'
            ELSE 'null'
        END AS bucket,
        COUNT(*),
        ROUND(AVG(geoguessr_score), 0)
    FROM rounds
    GROUP BY bucket
    ORDER BY bucket
""").fetchall():
    print(f'  {row[0]}: {row[1]} rounds, avg {row[2]} pts')

print('\n=== NULL RATES FOR KEY FEATURES ===')
total = con.execute('SELECT COUNT(*) FROM rounds').fetchone()[0]
for col in ['language','script','driving_side','biome','architecture','road_markings','plate_format','pole_type','soil_color','vegetation_specific']:
    nulls = con.execute(f'SELECT COUNT(*) FROM rounds WHERE {col} IS NULL').fetchone()[0]
    print(f'  {col:<24} {100*nulls/total:.0f}% null')

print('\n=== TOP 5 WORST ROUNDS ===')
for row in con.execute('SELECT round_id, guess_confidence, guess_lat, guess_lng, actual_lat, actual_lng, distance_km, geoguessr_score FROM rounds ORDER BY geoguessr_score ASC LIMIT 5').fetchall():
    print(f'  {row[0]}: {row[6]:.0f}km away, {row[7]} pts, conf={row[1]}')

print('\n=== READABLE TEXT RATE ===')
has_text = con.execute("SELECT COUNT(*) FROM rounds WHERE readable_text != '[]' AND readable_text IS NOT NULL").fetchone()[0]
print(f'rounds with any readable text: {has_text}/{total} ({100*has_text/total:.0f}%)')

con.close()