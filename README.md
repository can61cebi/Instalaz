# 📸 Instalaz - Professional Instagram Content Management Platform

<div align="center">
  <h3>🚀 Upload, Process & Auto-Post 4K Content to Instagram</h3>
  
  [![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
  [![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com)
  [![Instagram API](https://img.shields.io/badge/Instagram-API-E4405F.svg)](https://instagram.com)
  [![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
</div>

---

## 🌟 Overview

**Instalaz** is a comprehensive web-based Instagram Content Management Platform built with Flask. It empowers content creators and businesses to efficiently manage their Instagram presence by providing automated 4K media processing, intelligent optimization, and seamless posting capabilities.

### ✨ Key Features

- 🎯 **4K Media Processing** - Automatically optimize high-resolution images and videos
- 📱 **Multi-Format Support** - Handle images (JPG, PNG, HEIC, RAW, TIFF, BMP) and videos (MP4, MOV, AVI, MKV, WebM, M4V)
- 🎬 **Content Type Optimization** - Specific processing for Posts, Stories, and Reels
- ⚡ **Queue Management** - Background processing for batch uploads
- 🔒 **Secure Sessions** - Persistent Instagram authentication with 2FA support
- 🛡️ **Rate Limiting** - Built-in protection (50 uploads/hour, 5 login attempts max)
- 💧 **Watermarking** - Custom watermark support for brand protection
- 🎞️ **Video Processing** - FFmpeg integration with MoviePy fallback

---

## 📱 Screenshots

<p align="center">
  <img src="https://github.com/can61cebi/Instalaz/blob/master/images/image1.png" alt="Main Dashboard Interface" width="500">
</p>
<p align="center"><em>Figure 1. Main Dashboard - Content Overview & Management</em></p>

<p align="center">
  <img src="https://github.com/can61cebi/Instalaz/blob/master/images/image2.png" alt="Upload Interface" width="500">
</p>
<p align="center"><em>Figure 2. Upload Interface - Drag & Drop 4K Media Processing</em></p>

<p align="center">
  <img src="https://github.com/can61cebi/Instalaz/blob/master/images/image3.png" alt="Queue Management" width="500">
</p>
<p align="center"><em>Figure 3. Queue Management - Real-time Processing Status</em></p>

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.8+, Flask |
| **Instagram API** | instagrapi |
| **Media Processing** | FFmpeg, MoviePy, PIL, OpenCV |
| **Caching** | Redis (with in-memory fallback) |
| **Frontend** | HTML5, CSS3, JavaScript |
| **Authentication** | Session-based with 2FA support |

---

## 🚀 Installation & Setup

### Prerequisites

Before installing Instalaz, ensure you have the following installed on your system:

- **Python 3.8+** - [Download here](https://python.org/downloads/)
- **FFmpeg** - [Installation guide](https://ffmpeg.org/download.html)
- **Redis** (Optional, for better performance) - [Installation guide](https://redis.io/download)

### 📥 Installation Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/can61cebi/Instalaz.git
   cd Instalaz
   ```

2. **Install Dependencies**
   ```bash
   pip install flask flask-cors instagrapi moviepy pillow opencv-python redis requests
   ```

3. **Setup Environment Variables** (Optional)
   ```bash
   export SECRET_KEY="your-secret-key-here"
   export REDIS_URL="redis://localhost:6379"
   export PROXY_URL="your-proxy-url" # Optional
   ```

4. **Create Required Directories**
   ```bash
   mkdir -p uploads temp sessions static
   ```

5. **Install FFmpeg** (Required for video processing)
   
   **Ubuntu/Debian:**
   ```bash
   sudo apt update
   sudo apt install ffmpeg
   ```
   
   **macOS:**
   ```bash
   brew install ffmpeg
   ```
   
   **Windows:**
   Download from [FFmpeg official site](https://ffmpeg.org/download.html) and add to PATH

6. **Start Redis** (Optional but recommended)
   ```bash
   redis-server
   ```

7. **Run the Application**
   ```bash
   python app.py
   ```

The application will be available at `http://localhost:5000`

---

## 📖 Usage Guide

### 🔐 Getting Started

1. **Launch Application**: Navigate to `http://localhost:5000`
2. **Instagram Login**: Enter your Instagram credentials
3. **2FA Setup**: If enabled, complete two-factor authentication
4. **Upload Media**: Drag and drop or select your 4K images/videos
5. **Configure Settings**: Choose content type (Post/Story/Reel)
6. **Process & Post**: Let Instalaz optimize and schedule your content

### 📁 Supported File Formats

#### Images
- **Formats**: JPG, JPEG, PNG, HEIC, RAW, TIFF, BMP
- **Max Size**: 2GB
- **Output**: Optimized for Instagram (1080x1350 for posts, 1080x1920 for stories)

#### Videos
- **Formats**: MP4, MOV, AVI, MKV, WebM, M4V
- **Max Size**: 2GB
- **Processing**: 10Mbps bitrate, CRF 23, H.264 encoding
- **Output**: Instagram-ready formats with optimal compression

### ⚙️ Configuration Options

The application can be configured through the `Config` class in `app.py`:

```python
# File upload limits
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB

# Instagram dimensions
INSTAGRAM_STORY_SIZE = (1080, 1920)
INSTAGRAM_POST_SIZE = (1080, 1350)
INSTAGRAM_REEL_SIZE = (1080, 1920)

# Video processing settings
VIDEO_BITRATE = '10M'
VIDEO_CRF = 23
VIDEO_PRESET = 'slow'

# Rate limiting
UPLOAD_RATE_LIMIT = 50  # uploads per hour
LOGIN_RATE_LIMIT = 5    # login attempts max
```

---

## 🏗️ Architecture

### Core Components

| Component | Description | Location |
|-----------|-------------|----------|
| **InstagramManager** | Handles Instagram authentication & sessions | `app.py:114-249` |
| **MediaProcessor** | 4K media optimization & format conversion | `app.py:275-606` |
| **CacheManager** | Redis caching with in-memory fallback | `app.py:252-272` |
| **Config** | Application configuration management | `app.py:36-80` |

### Directory Structure

```
Instalaz/
├── app.py                 # Main Flask application
├── topla.py              # File scanning utility
├── templates/            # Jinja2 HTML templates
├── static/               # Static assets (CSS, JS, images)
├── uploads/              # User uploaded files
├── temp/                 # Temporary processed files
├── sessions/             # Instagram session storage
└── README.md            # This file
```

---

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/upload` | GET/POST | File upload interface |
| `/queue` | GET | Processing queue status |
| `/login` | POST | Instagram authentication |
| `/logout` | POST | Session termination |
| `/process` | POST | Media processing trigger |

---

## 🛡️ Security Features

- **🔐 Session Management**: Secure Instagram session persistence
- **🚦 Rate Limiting**: Protection against abuse (50 uploads/hour)
- **🔒 File Validation**: Comprehensive file type and size checks
- **🛡️ CSRF Protection**: Built-in Flask security measures
- **📝 Secure Logging**: No sensitive data in logs

---

## 📋 Requirements

### System Requirements
- **OS**: Windows 10+, macOS 10.14+, Ubuntu 18.04+
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 10GB free space for media processing
- **Network**: Stable internet connection for Instagram API

### Python Dependencies
```
flask>=2.0.0
flask-cors>=3.0.0
instagrapi>=1.16.0
moviepy>=1.0.3
pillow>=8.0.0
opencv-python>=4.5.0
redis>=4.0.0
requests>=2.25.0
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🆘 Support & Troubleshooting

### Common Issues

**❌ FFmpeg not found**
```bash
# Install FFmpeg and ensure it's in your PATH
which ffmpeg  # Should show installation path
```

**❌ Instagram login failed**
- Check credentials
- Verify 2FA settings
- Ensure stable internet connection

**❌ Redis connection error**
- Install and start Redis server
- Application will fallback to in-memory caching

### Getting Help

- 📧 **Email**: [can@cebi.tr](mailto:can@cebi.tr)
- 🐛 **Issues**: [GitHub Issues](https://github.com/can61cebi/Instalaz/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/can61cebi/Instalaz/discussions)

---

<div align="center">
  <h3>⭐ Star this repository if you found it helpful!</h3>
  
  **Made with ❤️ for the Instagram community**
  
  [🔗 Repository](https://github.com/can61cebi/Instalaz)