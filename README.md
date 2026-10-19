# CV agenda

Every Tuesday morning a GitHub Action fetches the CV Amsterdam programme for the next 10 days (Tuesday to the Thursday after) and saves it to `data/latest.json`:

- weekdays: screenings starting 18:00–20:00
- Saturday and Sunday: all screenings

A scheduled Claude task then picks out the classics, horror and sci-fi films and emails an overview.

Run it by hand: Actions → "Fetch CV programme" → Run workflow.
