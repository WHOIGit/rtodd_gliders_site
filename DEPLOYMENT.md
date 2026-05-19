# Deployment

Production deployment of GliderApp lives on the **racing** VM. This document describes the host setup, access model, and the operational commands used to deploy and update the app.

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

The app runs under Docker Compose (`compose.yml`). Two services are defined:

- `gliderapp` — the Dash web app, exposed on host port `8050`
- `data-watcher` — background ingest from `/srv/data/sync` into `/srv/data/netcdf`

Both share the `gliderapp:latest` image built from the repo's `Dockerfile`.

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

## Data volumes

Host paths mounted into the containers:

| Host path           | Container path       | Service       | Mode |
|---------------------|----------------------|---------------|------|
| `/srv/data/sync`    | `/app/data/sync`     | data-watcher  | ro   |
| `/srv/data/netcdf`  | `/app/data/netcdf`   | data-watcher  | rw   |
| `/srv/data`         | `/app/data`          | gliderapp     | ro   |
| `./config`          | `/app/config`        | gliderapp     | ro   |

`/srv/data` is managed outside this repo; the data-watcher is the writer for `netcdf/`, and the web app reads everything under `/srv/data` read-only.
