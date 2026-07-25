# CarDoggo Daily Content Agent

A small, transparent script (not a black box) that:

1. Checks your existing posts so it never repeats a topic
2. Picks the next topic from a rotating list (`TOPIC_POOL` in `agent.py` — edit freely)
3. Asks Claude to research (via web search) and write the article
4. Grabs a genuinely free-to-use image from Pexels (fallback: Openverse CC0)
5. Uploads the image and creates the post on cardoggo.com via the WordPress REST API

It defaults to creating **drafts**, not auto-publishing, so you can review the first
week or two of output before trusting it to go fully live.

---

## 1. One-time setup

### a. WordPress Application Password
You're the admin, so:
1. Log into `cardoggo.com/wp-admin`
2. Go to **Users → Profile** (your own user)
3. Scroll to **Application Passwords**, enter a name like `content-agent`, click **Add New**
4. Copy the generated password (looks like `abcd efgh ijkl mnop`) — this is `WP_APP_PASSWORD`
   in the `.env` file. Your normal login username is `WP_USERNAME`.

This does NOT require installing any plugin — Application Passwords are built into
WordPress 5.6+.

### b. Anthropic API key
Get one at https://console.anthropic.com (this is separate from your claude.ai chat login,
and is billed per-use — article generation with web search will cost a small amount per post).

### c. Pexels API key (free)
Sign up at https://www.pexels.com/api/ — free tier is generous and images require
no attribution and are cleared for commercial use. If you skip this, the agent falls
back to Openverse CC0 images, which are also free.

### d. Install and configure
```bash
cd cardoggo_agent
pip install -r requirements.txt
cp .env.example .env
# now edit .env and fill in your real values
```

---

## 2. Test it

Dry run — generates an article and finds an image, but touches nothing on WordPress:
```bash
python3 agent.py --dry-run
```

Real run — creates an actual (draft) post on cardoggo.com:
```bash
python3 agent.py
```

Check `cardoggo.com/wp-admin/edit.php` — you should see a new draft post with a
featured image, categories, and tags already set.

---

## 3. Automate it (daily)

### Option A: cron (simplest, if you have a server / always-on machine)
```bash
crontab -e
# add a line to run every day at 8am:
0 8 * * * cd /full/path/to/cardoggo_agent && /usr/bin/python3 agent.py >> agent.log 2>&1
```

### Option B: Claude Code
Since you mentioned Claude Code — you can just point Claude Code at this folder and
ask it to "run agent.py daily" using its own scheduling, or wrap the cron line above
into a task. Claude Code can also help you debug/extend the script directly since
it's plain, readable Python — nothing hidden.

### Option C: GitHub Actions (free, no server needed)
Push this folder to a private repo, store your `.env` values as repo secrets, and
add a workflow that runs `python3 agent.py` on a schedule (`cron:` trigger). I can
write that workflow file too if you want to go this route instead of a server.

---

## 4. Once you trust the output

Flip `PUBLISH_STATUS=draft` to `PUBLISH_STATUS=publish` in `.env` to let it go
fully autonomous — genuinely "hire an employee" mode. I'd still recommend
spot-checking weekly; automated content on a real site benefits from an
occasional human sanity check (accuracy, tone drift, image relevance).

---

## Notes / things worth knowing

- **Costs**: Anthropic API usage (writing + web search) and nothing else — WordPress
  and Pexels/Openverse are free.
- **Topic list**: `TOPIC_POOL` in `agent.py` is a starting set of ~15 topics matched
  to your existing categories. Add more any time; the agent won't repeat a topic
  that's already used locally (`state.json`) or already exists as a post title on
  the live site.
- **SEO**: the model is prompted to write an SEO-friendly title + meta description,
  but this script doesn't set the meta description in an SEO plugin (e.g. Yoast) —
  if you use one, I can extend the script to also push that field via its
  REST API meta box, just let me know which plugin you're running.
- **Image licensing**: Pexels images are free for commercial use with no attribution
  required. The Openverse fallback is filtered to CC0 only, for the same reason —
  so you never end up needing to credit a photographer buried in a blog post.
- **Safety net**: nothing auto-publishes until you explicitly set `PUBLISH_STATUS=publish`.
