# Deployment Guide

The dashboard is a single Streamlit app, so it can be hosted anywhere Python runs.
Three simple options:

## Option A — Streamlit Community Cloud (easiest, free)
1. Push this repo to GitHub.
2. Go to <https://share.streamlit.io>, sign in with GitHub, and choose **New app**.
3. Select the repo, branch `main`, and main file `app.py`.
4. Note: the large household dataset is not in the repo (see README → *Datasets*).
   Use the bundled *Online Retail* sample or upload a CSV in the sidebar.

## Option B — Your own server / VPS
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```
Run it under `systemd` (or `tmux`) and put a reverse proxy in front of it.

## Option C — Cloudflare Tunnel / Tailscale Funnel (no open ports)
Both tools make an **outbound-only** connection from your machine to the edge, so
no inbound firewall ports are needed.

```bash
# Cloudflare quick tunnel (temporary public URL, no account needed)
cloudflared tunnel --url http://localhost:8501
```
For a permanent hostname, create a named tunnel in the Cloudflare dashboard and
follow its install command. **Never commit tunnel tokens, API keys or credential
JSON files to this repository.**

## Security notes
- The app is a read-only analytics demo over public data; it has no login.
- If exposing it publicly, consider adding a password gate or Cloudflare Access.
