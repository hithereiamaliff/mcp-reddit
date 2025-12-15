# MCP Reddit Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction) server that provides tools for fetching and analyzing Reddit content. Self-hosted on VPS with Streamable HTTP transport.

> **Fork Notice**: This project is a fork of [ruradium/mcp-reddit](https://github.com/ruradium/mcp-reddit). See [What's New](#whats-new-in-this-fork) for improvements and additions.

## Features

- Fetch hot threads from any subreddit
- Get detailed post content including comments
- Support for different post types (text, link, gallery)
- Self-hosted VPS deployment with Docker and Nginx
- Streamable HTTP transport for remote access
- **Multiple API key input methods** (URL query, header, or environment variable)

## What's New in This Fork

This fork extends the original [ruradium/mcp-reddit](https://github.com/ruradium/mcp-reddit) with the following improvements:

### VPS Deployment Support
- **Streamable HTTP Transport**: Added `http_server.py` for remote access via HTTP instead of stdio-only
- **Docker & Docker Compose**: Production-ready containerization with health checks and non-root user
- **Nginx Reverse Proxy Config**: Ready-to-use location block for SSL termination
- **GitHub Actions CI/CD**: Auto-deployment workflow on push to main branch

### Enhanced Security & Flexibility
- **Multiple API Key Methods**: Pass Reddit credentials via:
  1. URL query parameters (`?client_id=xxx&client_secret=xxx`)
  2. HTTP headers (`X-Reddit-Client-ID`, `X-Reddit-Client-Secret`)
  3. Environment variables (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`)
- **CORS Middleware**: Configured for browser-based MCP clients
- **Health Check Endpoint**: `/health` for monitoring and load balancer integration

### Code Improvements
- **FastMCP v2**: Upgraded to FastMCP 2.0+ with native HTTP transport support
- **Starlette Integration**: ASGI app with middleware support
- **Structured Logging**: Better debugging and monitoring

## Quick Start

### Client Configuration

Add this to your MCP client configuration (Claude Desktop, Cursor, Windsurf, etc.):

**Option 1: URL with API credentials (recommended for personal use)**
```json
{
  "mcpServers": {
    "reddit": {
      "transport": "streamable-http",
      "url": "https://mcp.techmavie.digital/reddit/mcp?client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET"
    }
  }
}
```

**Option 2: Without credentials (if server has env vars configured)**
```json
{
  "mcpServers": {
    "reddit": {
      "transport": "streamable-http",
      "url": "https://mcp.techmavie.digital/reddit/mcp"
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `fetch_reddit_hot_threads` | Fetch hot threads from any subreddit |
| `fetch_reddit_post_content` | Get detailed post content with comments |

## API Key Configuration

You can provide Reddit API credentials in three ways (in order of priority):

| Method | Example |
|--------|---------|
| **URL Query Params** | `?client_id=xxx&client_secret=xxx` |
| **HTTP Headers** | `X-Reddit-Client-ID: xxx` and `X-Reddit-Client-Secret: xxx` |
| **Environment Variables** | `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env` |

To get Reddit API credentials:
1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps)
2. Click "Create App" or "Create Another App"
3. Select "script" as the app type
4. Note your `client_id` (under the app name) and `client_secret`

## Self-Hosting Guide

### Prerequisites

- Ubuntu/Debian VPS with Docker and Docker Compose
- Nginx with SSL certificate
- Domain pointing to your VPS

### VPS Deployment

1. **Clone and deploy on VPS:**
```bash
ssh root@your-vps-ip
mkdir -p /opt/mcp-servers/mcp-reddit
cd /opt/mcp-servers/mcp-reddit
git clone https://github.com/hithereiamaliff/mcp-reddit.git .
docker compose up -d --build
```

2. **Add Nginx location block** (from `deploy/nginx-mcp.conf`):
```bash
sudo nano /etc/nginx/sites-available/mcp.yourdomain.com
# Add the location block from deploy/nginx-mcp.conf
sudo nginx -t
sudo systemctl reload nginx
```

3. **Verify deployment:**
```bash
curl https://mcp.yourdomain.com/reddit/health
```

### GitHub Actions Auto-Deploy

Configure these secrets in your GitHub repository:
- `VPS_HOST` - Your VPS IP address
- `VPS_USERNAME` - SSH username (e.g., `root`)
- `VPS_SSH_KEY` - Private SSH key
- `VPS_PORT` - SSH port (usually `22`)

Push to `main` branch to trigger auto-deployment.

## Usage Example

Ask your AI assistant:

> "What are the latest hot threads in r/technology?"

The assistant will use the `fetch_reddit_hot_threads` tool to retrieve and summarize the posts.

## Architecture

```
Client (Claude, Cursor, Windsurf, etc.)
    ↓ HTTPS
https://mcp.techmavie.digital/reddit/mcp
    ↓
Nginx (SSL termination + reverse proxy)
    ↓ HTTP
Docker Container (port 8088 → 8080)
    ↓
MCP Server (Streamable HTTP Transport)
    ↓
Reddit API
```

## License

[MIT](LICENSE) 
