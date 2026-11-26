Server health check (read-only)
================================
1. Open PowerShell and go to the project folder:
     cd C:\Users\shiwansh\Dialeasypro

2. Run this, replacing the SSH part with the command you normally use to log in
   to the server (same user, same key file):

     Get-Content -Raw .\ops\server_check.sh | ssh -i <your-key.pem> <user>@<server-ip> "tr -d '\r' | bash -s" | Out-File -Encoding utf8 .\ops\server_report.txt

3. It takes about 30 seconds. When it finishes, tell Claude — the result is in
   ops\server_report.txt. The script only reads; it restarts and changes nothing.
