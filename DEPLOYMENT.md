# Deployment

Production deployment of GliderApp lives on the **racing** VM. The canonical public site is `https://gliders.whoi.edu/`. This document describes the host setup, access model, Apache vhosts, data paths, and the operational commands used to deploy and update the app.

## Host & install location

- Host: `racing`
- Install path: `/opt/gliderapp` (a clone of this repo)
- Service account: `gliderapp` (owns `/opt/gliderapp`)
- Group: `gliderapp` — members get read/write access to `/opt/gliderapp`

Current group members with rw access: `sbatchelder`, `rtodd`.

## Access model

### Becoming the `gliderapp` user

Members of the `gliderapp` group can run commands as the `gliderapp` service account without needing general `sudo` access. This is configured in `/etc/sudoers.d/gliderapp`:

```
Defaults:%gliderapp runcwd=*
%gliderapp ALL=(gliderapp) NOPASSWD: ALL
```

A convenience wrapper lives at `/opt/gliderapp/su-gliderapp` (also typically symlinked or copied into operators' home dirs):

```sh
sudo -u gliderapp --chdir=/opt/gliderapp -s
```

Run that to drop into an interactive shell as `gliderapp` in `/opt/gliderapp`.

### GitHub deploy key

The repo is pulled via a GitHub deploy key owned by the service account:

- Key path: `/home/gliderapp/.ssh/github_deploykey`
- Group-readable so `gliderapp` group members can also pull/push as the deploy identity.

Both the `gliderapp` user and group members have an SSH config entry that routes `github-gliderapp` through this key:

```sshconfig
Host github-gliderapp
  HostName github.com
  User git
  IdentityFile /home/gliderapp/.ssh/github_deploykey
  IdentitiesOnly yes
```

The repo's `origin` remote uses the `github-gliderapp` host alias so pulls always use the deploy key regardless of which user is invoking git.

## Running the app

The app runs under Docker Compose (`compose.yml`). Three services are defined:

- `gliderapp` — the Dash web app, exposed on host port `8050`
- `data-watcher` — background ingest from `/srv/data/sync` into `/srv/data/netcdf`
- `goatcounter` — self-hosted web analytics (see [Analytics](#analytics-goatcounter) below)

`gliderapp` and `data-watcher` share the `gliderapp:latest` image built from the repo's `Dockerfile`. `goatcounter` uses the upstream `arp242/goatcounter` image.

Apache is the public entrypoint. It terminates TLS for `gliders.whoi.edu`, serves the legacy `/data/` tree directly from disk, and proxies Dash routes to the `gliderapp` container on `127.0.0.1:8050`.

### Standard deploy / update

From `/opt/gliderapp`, as the `gliderapp` user (or a group member via the wrapper above):

```sh
git stash               # park any local edits so the pull is clean
git fetch
git pull
git stash pop           # optional: reapply local edits (skip if you don't need them)
docker compose up --build --force-recreate -d
```

`--build` rebuilds the image; `--force-recreate -d` recreates the containers in the background so the new image is actually picked up.

If the stashed/local changes are worth keeping, commit and push them rather than leaving them sitting on the prod box:

```sh
git add <files>
git commit -m "message"
git push
```

### Updating configs or regenerated content

For changes to `config/` (static pages, `map_config.yml`, `people.yml`) or to `publications.html` regenerated from `bibtex/`, the workflow is the same — recreate the containers so the new content is served:

```sh
docker compose up --build --force-recreate -d
```

Verify the change in the running app, and **only once you're satisfied**, commit and push:

```sh
git add <files>
git commit -m "message"
git push
```

### Other useful commands

```sh
docker compose ps          # status
docker compose logs -f     # tail logs
docker compose logs -f gliderapp
docker compose restart gliderapp
docker compose down        # stop everything
```

## Configuration

- **Environment / secrets:** `/opt/gliderapp/prod.env` — edit to change runtime settings (DB URLs, feature flags, etc.). Recreate containers after changes: `docker compose up -d`.
- **App configuration:** `/opt/gliderapp/config/` is bind-mounted read-only into the `gliderapp` container at `/app/config`. Contains:
  - `map_config.yml` — map layers / sites
  - `people.yml` — contributors
  - `homepage.html`, `datapage.html`, `publications.html` — static page content
  - `assets/` — static assets served by Dash

Changes to files in `config/` take effect on the next container restart (or immediately for files re-read on each request, depending on the code path).

## Apache vhosts

Reference Apache configs live in the repo under `apache/`:

- `apache/gliders.whoi.edu.conf` — canonical public site, Dash reverse proxy, and direct `/data/` static serving.
- `apache/analytics.gliders.whoi.edu.conf` — GoatCounter reverse proxy.

On `racing`, keep the live Apache site files symlinked to the repo copies so changes are versioned with the application:

```sh
sudo ln -s /opt/gliderapp/apache/gliders.whoi.edu.conf \
  /etc/apache2/sites-available/gliders.whoi.edu.conf
sudo ln -s /opt/gliderapp/apache/analytics.gliders.whoi.edu.conf \
  /etc/apache2/sites-available/analytics.gliders.whoi.edu.conf

sudo a2ensite gliders.whoi.edu.conf
sudo a2ensite analytics.gliders.whoi.edu.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Required Apache modules include `ssl`, `headers`, `rewrite`, `proxy`, and `proxy_http`. Enable any missing modules with `sudo a2enmod <module>`, then run `sudo apache2ctl configtest` and reload Apache.

TLS uses the Let's Encrypt lineage at `/etc/letsencrypt/live/gliders.whoi.edu/`. The certificate must cover both `gliders.whoi.edu` and `analytics.gliders.whoi.edu`.

## Data volumes

Host paths mounted into the containers:

| Host path             | Container path                       | Service       | Mode |
|-----------------------|--------------------------------------|---------------|------|
| `/srv/data/sync`      | `/app/data/sync`                     | data-watcher  | ro   |
| `/srv/data/netcdf`    | `/app/data/netcdf`                   | data-watcher  | rw   |
| `/srv/data`           | `/app/data`                          | gliderapp     | ro   |
| `./config`            | `/app/config`                        | gliderapp     | ro   |
| `/srv/data/analytics`   | `/home/goatcounter/goatcounter-data` | goatcounter   | rw   |

`/srv/data` is managed outside this repo; the data-watcher is the writer for `netcdf/`, and the web app reads everything under `/srv/data` read-only. `analytics/` holds GoatCounter's SQLite database — it sits under `/srv/data` for convenience but is written only by the `goatcounter` container, not by the app.

The public `https://gliders.whoi.edu/data/` path is separate from the Dash app. Apache serves it directly from the legacy host directory:

```text
/var/www/gliders.whoi.edu/data
```

That tree contains static mission pages, plot images, and directory indexes that are updated by external processing outside this repo. The Dash app intentionally links to files under `/data/` for section details and all-plots pages, so the main Apache vhost excludes `/data/` from proxying.

## Analytics (GoatCounter)

Site traffic is tracked by a self-hosted [GoatCounter](https://www.goatcounter.com/) instance — privacy-friendly, cookieless, no third-party (e.g. Google) involvement. It runs as the `goatcounter` service in `compose.yml`.

### How it fits together

- The container listens HTTP-only on `127.0.0.1:8051` (loopback — not directly reachable from the network).
- Apache serves `analytics.gliders.whoi.edu`, terminates TLS, and reverse-proxies to that port. The GoatCounter dashboard (and its login) lives there — that login *is* the analytics admin page.
- The tracking snippet is injected into every page by `src/app.py` when `ANALYTICS_ENDPOINT` is set in `prod.env`. A clientside callback in `src/layout.py` counts each Dash route change (Dash navigation is client-side, so a plain onload counter would miss it).
- The SQLite database is stored on the host at `/srv/data/analytics`.

### First-time setup

1. **DNS** — create an `A` record for `analytics.gliders.whoi.edu` pointing at `racing`.

2. **Data directory** — create the host directory and give the container's user write access. The `arp242/goatcounter` image runs as a non-root user; find its uid/gid and chown to match:

   ```sh
   docker run --rm arp242/goatcounter id        # note the uid:gid
   sudo mkdir -p /srv/data/analytics
   sudo chown <uid>:<gid> /srv/data/analytics
   ```

3. **Start the container:**

   ```sh
   docker compose up -d goatcounter
   ```

4. **Create the analytics site and the first admin user.** With `-it` the password is prompted interactively (kept out of shell history). The image is minimal and has no shell, so run `goatcounter` directly — not via `bash`:

   ```sh
   docker compose exec -it goatcounter goatcounter db create site \
     -vhost=analytics.gliders.whoi.edu \
     -user.email=<first-admin-email>
   ```

5. **Add the second admin user:**

   ```sh
   docker compose exec -it goatcounter goatcounter db create user \
     -site=analytics.gliders.whoi.edu \
     -email=<second-admin-email> -access=admin
   ```

   (Run `goatcounter db create user -h` if the flags differ in the installed version.) Both `rtodd` and `sbatchelder` should be created as admins.

6. **Apache vhost** — a reference copy of the site config lives in the repo at [`apache/analytics.gliders.whoi.edu.conf`](apache/analytics.gliders.whoi.edu.conf). Install it on `racing`:

   ```sh
   sudo ln -sf /opt/gliderapp/apache/analytics.gliders.whoi.edu.conf \
     /etc/apache2/sites-available/analytics.gliders.whoi.edu.conf
   sudo a2ensite analytics.gliders.whoi.edu.conf
   sudo apache2ctl configtest
   sudo systemctl reload apache2
   ```

   TLS uses the shared Let's Encrypt certificate:

   - Certificate: `/etc/letsencrypt/live/gliders.whoi.edu/fullchain.pem`
   - Private key: `/etc/letsencrypt/live/gliders.whoi.edu/privkey.pem`

   This certbot lineage **must include `analytics.gliders.whoi.edu` as a SAN** — if it currently covers only `gliders.whoi.edu`, expand it (e.g. re-run certbot with `-d gliders.whoi.edu -d analytics.gliders.whoi.edu`) before reloading Apache.

   `ProxyPreserveHost On` is required so GoatCounter sees the `analytics.gliders.whoi.edu` host and matches the site; `X-Forwarded-Proto` tells it the public connection is HTTPS.

### Day-to-day

- View analytics: log in at `https://analytics.gliders.whoi.edu`.
- `-automigrate` in `compose.yml` applies schema migrations automatically when the image is updated (`docker compose pull goatcounter && docker compose up -d goatcounter`).
- To disable tracking (e.g. local dev), leave `ANALYTICS_ENDPOINT` unset in the environment — the snippet is then not injected.
