# Mobile Panel

Run the local server:

```bash
python3 scripts/run_mobile_panel_server.py --host 0.0.0.0 --port 8765
```

Then open the LAN URL from an Android browser on the same Wi-Fi network.

Current capabilities:

- View queue status and recent logs
- Submit an existing post into the local queue
- Record a new idea into the mobile inbox
- Import the inbox into the local queue
- Preview the next reconcile plan
- Optionally trigger a real reconcile
