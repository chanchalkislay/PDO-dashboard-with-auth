# Oracle Cloud VM Migration Plan
**PDO Dashboard → Oracle Always Free ARM VM**  
**Date:** July 2026 | **Estimated total time:** 3–4 hours (one-time)

---

## Overview

Move the PDO Dashboard from Streamlit Cloud to a self-hosted Oracle ARM VM.
No code changes required. Same Streamlit app, running on your own server with:
- 12GB RAM (vs 1GB on Streamlit Cloud)
- Persistent SQLite on 200GB disk
- No sleep/spin-down
- Ollama support for the LLM layer

---

## Phase 1 — Oracle Cloud Account & VM (45 min)

### Step 1.1 — Create Oracle Cloud Account

1. Go to https://www.oracle.com/cloud/free/
2. Click **Start for free**
3. Fill in details — use a real phone number (OTP verification required)
4. **Region selection is critical** — choose one with ARM availability:
   - `ap-mumbai-1` (Mumbai) — closest for India
   - `eu-frankfurt-1` (Frankfurt) — reliable alternative
   - Avoid US regions — ARM capacity is often exhausted there
5. Add credit card — required for identity verification only, not charged for Always Free
6. Wait for account activation email (can take 15–30 minutes)

> ⚠️ If signup rejects your card, try a different browser or incognito mode.
> This is a known Oracle signup quirk.

---

### Step 1.2 — Provision the ARM VM

1. Log into Oracle Cloud Console → **Compute → Instances → Create Instance**

2. **Name:** `pdo-dashboard`

3. **Image:** Click *Edit* → Canonical Ubuntu → **Ubuntu 22.04** (not 24.04 — better package support)

4. **Shape:** Click *Edit* → *Change Shape*
   - Select **Ampere** (ARM) → `VM.Standard.A1.Flex`
   - Set **OCPUs: 2** and **Memory: 12 GB**
   - (This stays within Always Free limits running 24/7)

5. **Networking:** Leave defaults (a VCN will be auto-created)

6. **SSH Keys:**
   - Select *Generate a key pair*
   - **Download both keys immediately** — you cannot get the private key later
   - Save as `oracle_pdo.key` somewhere safe on your Windows machine

7. **Boot Volume:** Leave at default 50GB (comes from your 200GB block storage allocation)

8. Click **Create**. VM reaches Running state in ~3 minutes.

9. **Note down the Public IP address** shown on the instance detail page.

---

### Step 1.3 — Open Firewall Ports in Oracle Console

Oracle's default VCN blocks all inbound traffic except SSH. You must open ports manually.

1. In the instance detail page → click the **VCN name** link
2. Go to **Security Lists** → click the default security list
3. Click **Add Ingress Rules** → add these two rules:

| Source CIDR | Protocol | Port | Description |
|-------------|----------|------|-------------|
| 0.0.0.0/0 | TCP | 80 | HTTP |
| 0.0.0.0/0 | TCP | 443 | HTTPS |

4. Save changes.

---

## Phase 2 — Connect & Set Up the Server (30 min)

### Step 2.1 — SSH from Windows

Open **Windows Terminal** (or PowerShell):

```powershell
# Fix key permissions first (required — SSH will reject world-readable keys)
icacls "C:\path\to\oracle_pdo.key" /inheritance:r /grant:r "%USERNAME%:R"

# Connect (default username for Ubuntu on Oracle is 'ubuntu')
ssh -i "C:\path\to\oracle_pdo.key" ubuntu@YOUR_VM_IP
```

You should see a Ubuntu welcome message. You're in.

---

### Step 2.2 — Initial Server Setup

Run these commands on the VM (paste in sequence):

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install essentials
sudo apt install -y python3-pip python3-venv git nginx certbot python3-certbot-nginx ufw

# Configure Ubuntu's own firewall (separate from Oracle's VCN rules)
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
# Type 'y' when prompted

# Verify nginx is running
sudo systemctl status nginx
# Should show: active (running)
```

Open a browser and go to `http://YOUR_VM_IP` — you should see the nginx welcome page. ✅

---

## Phase 3 — Deploy the App (45 min)

### Step 3.1 — Clone the Repository

```bash
# Create app directory
mkdir -p /home/ubuntu/apps
cd /home/ubuntu/apps

# Clone your GitHub repo
git clone https://github.com/YOUR_USERNAME/PDO-Dashboard-Demo.git
cd PDO-Dashboard-Demo

# Verify DB is present
ls -lh app/pune_do.db
# Should show the file with its size
```

---

### Step 3.2 — Python Environment & Dependencies

```bash
cd /home/ubuntu/apps/PDO-Dashboard-Demo

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install streamlit pandas openpyxl plotly

# If you have a requirements.txt:
# pip install -r requirements.txt

# Test the app starts (Ctrl+C to stop after confirming)
streamlit run app/app.py --server.port 8501 --server.headless true
```

If you see `You can now view your Streamlit app in your browser` — ✅

---

### Step 3.3 — Streamlit Config File

```bash
mkdir -p /home/ubuntu/apps/PDO-Dashboard-Demo/.streamlit
cat > /home/ubuntu/apps/PDO-Dashboard-Demo/.streamlit/config.toml << 'EOF'
[server]
headless = true
port = 8501
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
EOF
```

---

### Step 3.4 — Systemd Service (Auto-start on reboot)

```bash
sudo nano /etc/systemd/system/pdodashboard.service
```

Paste this content (adjust path if needed):

```ini
[Unit]
Description=PDO Dashboard Streamlit App
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/apps/PDO-Dashboard-Demo
Environment="PATH=/home/ubuntu/apps/PDO-Dashboard-Demo/venv/bin"
ExecStart=/home/ubuntu/apps/PDO-Dashboard-Demo/venv/bin/streamlit run app/app.py --server.port 8501 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save (Ctrl+X → Y → Enter), then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pdodashboard
sudo systemctl start pdodashboard

# Check it's running
sudo systemctl status pdodashboard
# Should show: active (running)
```

---

### Step 3.5 — Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/pdodashboard
```

Paste this (replace `YOUR_VM_IP` with actual IP, or domain if you have one):

```nginx
server {
    listen 80;
    server_name YOUR_VM_IP;   # or yourdomain.com

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    location /healthz {
        return 200 'ok';
    }
}
```

Save, then activate:

```bash
sudo ln -s /etc/nginx/sites-available/pdodashboard /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default   # remove the nginx welcome page
sudo nginx -t                               # test config — should say OK
sudo systemctl reload nginx
```

Now open `http://YOUR_VM_IP` in a browser → your dashboard should load. ✅

---

### Step 3.6 — SSL Certificate (if you have a domain)

If you point a domain's DNS A-record to your VM's IP:

```bash
sudo certbot --nginx -d yourdomain.com
# Follow prompts — email, agree to terms
# Choose option 2: Redirect HTTP to HTTPS
```

Certbot auto-renews every 90 days. Dashboard is now on HTTPS. ✅

**No domain?** The app works fine on `http://IP:80` without SSL.

---

## Phase 4 — DB Update Workflow (New Monthly Process)

After ingesting a new month's data locally, two options to push to the server:

### Option A — Git Push (current workflow, minimal change)

```powershell
# On your Windows machine — same as today
git add app/pune_do.db
git commit -m "Add July 2026 data"
git push origin main
```

Then on the VM:

```bash
cd /home/ubuntu/apps/PDO-Dashboard-Demo
git pull origin main
sudo systemctl restart pdodashboard
```

Dashboard picks up new data immediately.

---

### Option B — Direct SCP Copy (faster, no git commit needed)

```powershell
# From Windows Terminal — copy DB directly to VM
scp -i "C:\path\to\oracle_pdo.key" "D:\Github\PDO-Dashboard-Demo\app\pune_do.db" ubuntu@YOUR_VM_IP:/home/ubuntu/apps/PDO-Dashboard-Demo/app/pune_do.db
```

No restart needed — Streamlit reads the file fresh on each query.

---

### Option C — GitHub Webhook (fully automated)

Set up a webhook so every `git push` auto-triggers `git pull` on the server.
More complex — set this up after basic deployment is stable.

---

## Phase 5 — Ollama Install (When Ready for LLM Layer)

```bash
# Install Ollama (runs as a systemd service automatically)
curl -fsSL https://ollama.com/install.sh | sh

# Verify it's running
ollama list

# Pull models (do one at a time — each takes a few minutes)
ollama pull llama3.2        # ~2GB — for narrative generator
ollama pull mistral         # ~4GB — better quality, slower

# Test
ollama run llama3.2 "Summarize: BPCL grew 10% in June 2026"
```

Ollama listens on `localhost:11434` — same URL as in `planned_incorporation_of_LLM.md`.
No code changes needed; the `app/llm.py` file connects to this automatically.

---

## Quick Reference — Day-to-Day Commands

```bash
# SSH into server
ssh -i "C:\path\to\oracle_pdo.key" ubuntu@YOUR_VM_IP

# Check app status
sudo systemctl status pdodashboard

# Restart app (after code changes)
sudo systemctl restart pdodashboard

# View live logs
journalctl -u pdodashboard -f

# Pull latest code
cd /home/ubuntu/apps/PDO-Dashboard-Demo && git pull

# Check disk usage
df -h
```

---

## Checklist

- [ ] Oracle account created, region selected
- [ ] ARM VM provisioned (2 OCPU, 12GB RAM, Ubuntu 22.04)
- [ ] VCN ports 80 + 443 opened
- [ ] SSH key saved and tested
- [ ] Nginx installed and serving on port 80
- [ ] Repo cloned, DB present
- [ ] Virtual environment created, dependencies installed
- [ ] Systemd service running and enabled
- [ ] Nginx reverse proxy configured
- [ ] Dashboard accessible at http://YOUR_VM_IP
- [ ] (Optional) SSL certificate via certbot
- [ ] DB update workflow tested
- [ ] (Later) Ollama installed and tested

---

*Document created: July 2026 · No code changes required — existing Streamlit app runs unchanged*
