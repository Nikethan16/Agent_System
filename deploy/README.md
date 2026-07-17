# deploy/ — systemd units for the always-on VM

These are the units referenced by `docs/SETUP_GUIDE.md`. Install them on the VM (paths
assume the project lives at `/home/ubuntu/agent_system`).

## `agentcore.service` — the app (already in SETUP_GUIDE Step G)

Runs uvicorn on `:8800`, restarts on crash, starts on boot. Its full contents are in
`docs/SETUP_GUIDE.md` (Step G).

## `agentfunnel.service` — keep the public Tailscale Funnel URL alive across reboots

The funnel (`tailscale funnel --bg 8800`) is what makes the app reachable at your
`*.ts.net` HTTPS URL. Applying it once by hand does **not** reliably survive a reboot —
the cause of "the VM link stopped working." This oneshot unit waits for `tailscaled` and
re-publishes the funnel on every boot.

```bash
# copy the unit into place
sudo cp /home/ubuntu/agent_system/deploy/agentfunnel.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now agentfunnel

# confirm it's up and see the public URL
systemctl status agentfunnel
tailscale funnel status
```

Notes:
- Requires `tailscaled` to be installed and logged in (`sudo tailscale up`) and the node
  to have Funnel enabled in the Tailscale admin console (HTTPS + Funnel node attribute).
- To take the funnel down: `sudo systemctl disable --now agentfunnel` (its `ExecStop`
  turns the funnel off), or `tailscale funnel reset`.
- If the app runs on a different port, change `8800` in both this unit and
  `agentcore.service`.
