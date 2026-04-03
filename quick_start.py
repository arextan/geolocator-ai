import duckdb
con = duckdb.connect('geoguessr.db', read_only=True)
print('=== Low scores where Claude guessed USA ===')
rows = con.execute("""
    SELECT round_id, guessed_city, actual_lat, actual_lng, distance_km, geoguessr_score 
    FROM rounds 
    WHERE guessed_country = 'United States' AND geoguessr_score < 1000 
    ORDER BY geoguessr_score LIMIT 10
""").fetchall()
for r in rows:
    print(f'{r[0]}: guessed {r[1]}, actual ({r[2]:.1f}, {r[3]:.1f}), {r[4]:.0f}km, {r[5]}pts')
con.close()