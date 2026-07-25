# Running CarDoggo Agent on GitHub Actions (no terminal, no local install)

Everything below happens in your web browser. GitHub's servers will run the
script every day for you, for free (public or private repos both get free
Actions minutes for a project this small).

**Before you start:** if you pasted any real credentials into a chat with me
earlier, rotate them first (revoke the old ones, generate new ones) — see the
message where I flagged that. Use the *new* credentials below.

---

## Step 1 — Create a GitHub account (skip if you have one)
Go to https://github.com and sign up. It's free.

## Step 2 — Create a new repository
1. Click the **+** icon top-right → **New repository**
2. Name it something like `cardoggo-agent`
3. Set visibility to **Private** (recommended — keeps your setup out of public view)
4. Leave everything else default → **Create repository**

## Step 3 — Upload the files
On your new (empty) repo page:
1. Click **"uploading an existing file"** (or Add file → Upload files)
2. Drag in these files from the folder I gave you:
   - `agent.py`
   - `requirements.txt`
   - `README.md`
   - `state.json`
3. **Do NOT upload `.env` or `env.example`** — those either contain secrets
   or are just templates; secrets go into GitHub's secret vault instead (next step)
4. Scroll down, click **Commit changes**

Now add the workflow file:
1. Click **Add file → Create new file**
2. In the "Name your file" box, type exactly: `.github/workflows/daily-post.yml`
   (typing the slashes creates the folders automatically)
3. Paste in the contents of the `daily-post.yml` file I gave you
4. Click **Commit changes**

## Step 4 — Add your secrets
Go to your repo's **Settings** tab → left sidebar **Secrets and variables** → **Actions**.

Click **New repository secret** four times, once for each of these
(name on the left exactly as shown, value = your real credential):

| Secret name | Value |
|---|---|
| `WP_USERNAME` | your WordPress username |
| `WP_APP_PASSWORD` | your WordPress Application Password |
| `ANTHROPIC_API_KEY` | your Anthropic API key |
| `PEXELS_API_KEY` | your Pexels API key |

(Optional) Under the **Variables** tab in that same screen, add one more if
you want to control draft-vs-publish without editing the workflow file:
- Name: `PUBLISH_STATUS`, Value: `draft` (or `publish` once you trust it)

## Step 5 — Test it manually
1. Go to the **Actions** tab of your repo
2. You should see "CarDoggo Daily Post" listed on the left — click it
3. Click **Run workflow** (dropdown on the right) → **Run workflow** button
4. Wait ~30–60 seconds, refresh — click into the run to watch the logs live
5. If it succeeds (green checkmark), go check `cardoggo.com/wp-admin/edit.php`
   — you should see a new draft post waiting for you

If it fails (red X), click into the run → click the failed step → read the
error text and send it to me, I'll help you fix it.

## Step 6 — Let it run daily
Nothing else to do — the `schedule:` line in the workflow file already has it
running once a day automatically. You can change the time it runs by editing
the `cron:` line (it's in UTC).

## Step 7 — Go live
Once you've checked a few days of draft output and you're happy with it,
change the `PUBLISH_STATUS` variable from `draft` to `publish` (Settings →
Secrets and variables → Actions → Variables tab) and future posts will go
live automatically with no review step.
