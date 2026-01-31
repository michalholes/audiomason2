# 🌐 AudioMason v2 - Web Server

**Complete Web UI + REST API**

---

## ✅ **Features**

### **Web UI** 🎨
- ✅ Beautiful responsive interface
- ✅ Dashboard with real-time stats
- ✅ File upload (drag & drop)
- ✅ Job queue monitoring
- ✅ Configuration editor
- ✅ Checkpoint management
- ✅ Live progress updates (WebSocket)

### **REST API** 🔌
- ✅ Full AudioMason control via HTTP
- ✅ File upload endpoint
- ✅ Job management
- ✅ Configuration API
- ✅ Checkpoint API
- ✅ WebSocket for real-time updates

---

## 🚀 **Quick Start**

### **1. Install Dependencies**

```bash
pip install fastapi uvicorn python-multipart websockets
```

### **2. Start Web Server**

```bash
# Default port (8080)
./audiomason web

# Custom port
./audiomason web --port 3000

# With config
./audiomason web --port 8080 --host 0.0.0.0
```

### **3. Open Browser**

```
http://localhost:8080
```

---

## 📖 **Web UI Guide**

### **Dashboard Tab** 📊

Shows:
- Active jobs count
- Completed jobs count
- Errors count
- System status
- Recent activity

### **Process Books Tab** 🎵

1. **Upload file:** Click to select M4A/Opus/MP3
2. **Fill metadata:** Author, Title, Year
3. **Set options:**
   - Audio bitrate (96k - 320k)
   - Loudness normalization
   - Chapter splitting
   - Pipeline (minimal/standard)
4. **Start processing:** Click "Start Processing"

**Auto-fill:** Filename is parsed for author/title!

### **Queue Tab** 📋

- View all active jobs
- Real-time progress bars
- Job status (processing/done/error)
- Current step display

### **Config Tab** ⚙️

- View all configuration
- See config source (cli/env/config/default)
- Edit values (coming soon)

### **Checkpoints Tab** 💾

- List all saved checkpoints
- Resume interrupted processing
- View checkpoint details (progress, state)

---

## 🔌 **REST API**

Base URL: `http://localhost:8080/api`

### **Endpoints**

#### **GET /api/status**

Get system status.

**Response:**
```json
{
  "status": "running",
  "active_jobs": 2,
  "version": "2.0.0"
}
```

#### **GET /api/config**

Get configuration.

**Response:**
```json
{
  "bitrate": {
    "value": "128k",
    "source": "default"
  },
  "output_dir": {
    "value": "/home/user/Audiobooks/output",
    "source": "user_config"
  }
}
```

#### **POST /api/upload**

Upload audio file.

**Request:** `multipart/form-data`
- `file`: Audio file (M4A, Opus, MP3)

**Response:**
```json
{
  "message": "File uploaded",
  "filename": "book.m4a",
  "path": "/tmp/audiomason/uploads/book.m4a",
  "size": 52428800
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8080/api/upload \
  -F "file=@book.m4a"
```

#### **POST /api/process**

Start processing.

**Request:** `application/x-www-form-urlencoded`
- `filename`: Uploaded filename
- `author`: Book author
- `title`: Book title
- `year`: Publication year (optional)
- `bitrate`: Audio bitrate (default: 128k)
- `loudnorm`: Enable loudness normalization (boolean)
- `split_chapters`: Split by chapters (boolean)
- `pipeline`: Pipeline name (default: standard)

**Response:**
```json
{
  "message": "Processing started",
  "job_id": "abc123-def456"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8080/api/process \
  -F "filename=book.m4a" \
  -F "author=George Orwell" \
  -F "title=1984" \
  -F "year=1949" \
  -F "bitrate=320k" \
  -F "loudnorm=true" \
  -F "pipeline=standard"
```

#### **GET /api/jobs**

List all jobs.

**Response:**
```json
[
  {
    "id": "abc123",
    "title": "1984",
    "author": "George Orwell",
    "state": "processing",
    "progress": 0.45,
    "current_step": "convert"
  }
]
```

#### **GET /api/jobs/{job_id}**

Get job details.

**Response:**
```json
{
  "id": "abc123",
  "source": "/tmp/audiomason/uploads/book.m4a",
  "title": "1984",
  "author": "George Orwell",
  "year": 1949,
  "state": "processing",
  "progress": 0.45,
  "current_step": "convert",
  "completed_steps": ["import"],
  "warnings": [],
  "timings": {
    "import": 1.2
  }
}
```

#### **DELETE /api/jobs/{job_id}**

Cancel job.

**Response:**
```json
{
  "message": "Job cancelled"
}
```

#### **GET /api/checkpoints**

List checkpoints.

**Response:**
```json
[
  {
    "id": "ctx123",
    "title": "Foundation",
    "author": "Isaac Asimov",
    "state": "processing",
    "progress": 0.75,
    "file": "/home/user/.audiomason/checkpoints/ctx123.json"
  }
]
```

#### **POST /api/checkpoints/{checkpoint_id}/resume**

Resume from checkpoint.

**Response:**
```json
{
  "message": "Processing resumed",
  "job_id": "ctx123"
}
```

---

## 🔌 **WebSocket**

URL: `ws://localhost:8080/ws`

### **Messages**

Server sends JSON messages:

**Status Update:**
```json
{
  "type": "status",
  "active_jobs": 2
}
```

**Job Update:**
```json
{
  "type": "job_update",
  "event": "complete",
  "job_id": "abc123",
  "progress": 1.0,
  "state": "done"
}
```

### **JavaScript Example:**

```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'job_update') {
    console.log(`Job ${data.job_id}: ${data.state}`);
  }
};
```

---

## ⚙️ **Configuration**

### **Config File** (`~/.config/audiomason/config.yaml`):

```yaml
web_server:
  host: "0.0.0.0"  # Listen on all interfaces
  port: 8080        # Default port
  reload: false     # Auto-reload on code changes (dev only)
  upload_dir: "/tmp/audiomason/uploads"
  cors_origins:     # CORS settings
    - "http://localhost:3000"
    - "https://yourdomain.com"
```

### **Environment Variables:**

```bash
export AUDIOMASON_WEB_HOST="0.0.0.0"
export AUDIOMASON_WEB_PORT="8080"
export AUDIOMASON_WEB_UPLOAD_DIR="/var/tmp/uploads"
```

### **CLI Arguments:**

```bash
./audiomason web --port 3000 --host 127.0.0.1
```

---

## 🔒 **Security**

### **Current Status:**

⚠️ **No authentication** - suitable for local use only!

### **Production Recommendations:**

1. **Use reverse proxy** (nginx, Apache) with authentication
2. **Enable HTTPS** with SSL certificate
3. **Firewall rules** to restrict access
4. **Run as non-root user**

### **Example nginx Config:**

```nginx
server {
    listen 80;
    server_name audiomason.yourdomain.com;
    
    # Basic auth
    auth_basic "AudioMason";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## 🐳 **Docker**

### **Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg

# Copy project
COPY . /app

# Install Python dependencies
RUN pip install -e ".[all]"

# Expose port
EXPOSE 8080

# Run web server
CMD ["./audiomason", "web", "--host", "0.0.0.0", "--port", "8080"]
```

### **Build & Run:**

```bash
# Build
docker build -t audiomason-web .

# Run
docker run -p 8080:8080 -v ~/Audiobooks:/output audiomason-web
```

---

## 📱 **API Clients**

### **Python Client Example:**

```python
import requests

API_URL = "http://localhost:8080/api"

# Upload file
with open("book.m4a", "rb") as f:
    response = requests.post(
        f"{API_URL}/upload",
        files={"file": f}
    )
    print(response.json())

# Start processing
response = requests.post(
    f"{API_URL}/process",
    data={
        "filename": "book.m4a",
        "author": "George Orwell",
        "title": "1984",
        "bitrate": "320k",
        "loudnorm": True,
    }
)
job_id = response.json()["job_id"]

# Check status
response = requests.get(f"{API_URL}/jobs/{job_id}")
print(response.json())
```

### **JavaScript Fetch Example:**

```javascript
// Upload file
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const uploadResponse = await fetch('/api/upload', {
  method: 'POST',
  body: formData
});
const uploadData = await uploadResponse.json();

// Start processing
const processFormData = new FormData();
processFormData.append('filename', uploadData.filename);
processFormData.append('author', 'George Orwell');
processFormData.append('title', '1984');

const processResponse = await fetch('/api/process', {
  method: 'POST',
  body: processFormData
});
const processData = await processResponse.json();

console.log('Job ID:', processData.job_id);
```

---

## 🚀 **Advanced Usage**

### **Multiple Users:**

Run multiple instances on different ports:

```bash
# User 1
./audiomason web --port 8080

# User 2
./audiomason web --port 8081
```

### **Remote Access:**

```bash
# Listen on all interfaces
./audiomason web --host 0.0.0.0 --port 8080

# Access from another machine
http://raspberrypi.local:8080
```

### **Systemd Service:**

```ini
# /etc/systemd/system/audiomason-web.service
[Unit]
Description=AudioMason Web Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/audiomason-v2-implementation
ExecStart=/home/pi/audiomason-v2-implementation/audiomason web --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable & start:**
```bash
sudo systemctl enable audiomason-web
sudo systemctl start audiomason-web
```

---

## 📊 **API Documentation**

Full interactive API docs available at:

- **Swagger UI:** `http://localhost:8080/docs`
- **ReDoc:** `http://localhost:8080/redoc`

---

## 🎯 **Use Cases**

### **1. Home Media Server**

Run on Raspberry Pi, access from any device on home network.

### **2. Batch Processing**

Upload multiple files, queue them, process in background.

### **3. Remote Processing**

Process audiobooks from phone/tablet while away from home.

### **4. Integration**

Integrate with other tools via REST API (Home Assistant, scripts, etc.)

### **5. Mobile App Backend**

Use as backend for custom mobile app.

---

## 🐛 **Troubleshooting**

### **Port already in use:**

```bash
# Check what's using port 8080
sudo lsof -i :8080

# Use different port
./audiomason web --port 3000
```

### **Can't access from another machine:**

```bash
# Make sure listening on 0.0.0.0
./audiomason web --host 0.0.0.0 --port 8080

# Check firewall
sudo ufw allow 8080
```

### **Upload fails:**

```bash
# Check upload directory exists and is writable
mkdir -p /tmp/audiomason/uploads
chmod 777 /tmp/audiomason/uploads
```

---

## 📝 **Notes**

- **File size limit:** 500MB default (configurable)
- **Concurrent uploads:** Unlimited
- **Concurrent processing:** Controlled by parallel settings
- **WebSocket:** Auto-reconnects on disconnect

---

## ✅ **Status**

**Web Server:** ✅ COMPLETE

**Features Implemented:**
- ✅ REST API (all endpoints)
- ✅ Web UI (complete interface)
- ✅ File upload
- ✅ Job management
- ✅ Real-time updates (WebSocket)
- ✅ Configuration API
- ✅ Checkpoint management
- ✅ API documentation (auto-generated)

**Ready for Production!** 🚀
