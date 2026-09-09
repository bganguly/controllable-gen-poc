# LLM Implementations Workspace

## Practice sessions

Interview questions come from https://rainbow-crumble-167502.netlify.app/
The backing repo is **bganguly/company-interviews-since-2026** — that is the only repo
where practice attempts are saved. Do NOT write attempt files to this directory.

### How to handle a [PRACTICE: ...] prompt

When the user pastes a prompt that starts with a marker like:

```
[PRACTICE: question=la-2-setup company=2026-isrg level=2]
```

1. Use that marker to identify `<qid>` (question value) and `<cid>` (company value).
2. Help the user work through the question in this conversation.
3. When the user says "save attempt", "save this", or similar — send the solution to
   the backend API (no local file needed):

```bash
python3 -c "
import json, urllib.request
content = '''PASTE_SOLUTION_HERE'''
body = json.dumps({'content': content}).encode()
req = urllib.request.Request(
    'https://company-interviews-since-2026.onrender.com/api/practice/<cid>/<qid>',
    data=body, method='POST',
    headers={'Content-Type': 'application/json'}
)
resp = urllib.request.urlopen(req)
d = json.loads(resp.read())
print(f'Saved: {d[\"vname\"]} ({d[\"sha\"]})')
print(f'Diff:  {d[\"commit_url\"]}')
"
```

Replace `<cid>` and `<qid>` with the values from the marker, and the solution code
in place of `PASTE_SOLUTION_HERE` before running.

4. Show the user the version name and diff link from the output.
