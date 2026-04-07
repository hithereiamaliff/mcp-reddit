# MCP Reddit Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction) server that provides tools for fetching and analyzing Reddit content. Self-hosted on VPS with Streamable HTTP transport.

> **Fork Notice**: This project is a fork of [ruradium/mcp-reddit](https://github.com/ruradium/mcp-reddit). See [What's New](#whats-new-in-this-fork) for improvements and additions.

## Features

- Fetch threads from any subreddit with flexible sorting (hot, new, top, rising, controversial)
- Get detailed post content with configurable comment sorting
- Search Reddit by query, optionally scoped to a subreddit
- Fetch subreddit metadata, stats, and rules
- Fetch user profiles and recent activity with pagination and time filters
- Search for user posts even when profiles are hidden (author: search workaround)
- Cursor-based pagination for browsing through large result sets
- Support for different post types (text, link, gallery, poll, crosspost)
- Self-hosted VPS deployment with Docker and Nginx
- Streamable HTTP transport for remote access
- **MCP Key Service integration** for secure hosted credential management
- **Multiple API key input methods** (key service, URL query, header, or environment variable)

## What's New in This Fork

This fork extends the original [ruradium/mcp-reddit](https://github.com/ruradium/mcp-reddit) with the following improvements:

### VPS Deployment Support
- **Streamable HTTP Transport**: Added `http_server.py` for remote access via HTTP instead of stdio-only
- **Docker & Docker Compose**: Production-ready containerization with health checks and non-root user
- **Nginx Reverse Proxy Config**: Ready-to-use location block for SSL termination
- **GitHub Actions CI/CD**: Auto-deployment workflow on push to main branch

### Enhanced Security & Flexibility
- **MCP Key Service**: Secure hosted credential management via [mcp-key-service](https://github.com/hithereiamaliff/mcp-key-service) — users connect with a `usr_xxx` key instead of raw Reddit credentials
- **Multiple API Key Methods**: Pass Reddit credentials via:
  1. Key service (`/mcp/usr_xxx` or `?api_key=usr_xxx`)
  2. HTTP headers (`X-Reddit-Client-ID`, `X-Reddit-Client-Secret`)
  3. URL query parameters (`?client_id=xxx&client_secret=xxx`)
  4. Environment variables (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`)
- **CORS Middleware**: Configured for browser-based MCP clients
- **Health Check Endpoint**: `/health` for monitoring and load balancer integration

### Analytics Dashboard
- **Real-time Metrics**: Track requests, tool calls, and client activity
- **Visual Dashboard**: Chart.js-powered dashboard at `/analytics/dashboard`
- **Persistent Storage**: Analytics survive container restarts via Docker volumes
- **Backup/Restore**: Import endpoint for restoring analytics from backups

### Code Improvements
- **FastMCP v2**: Upgraded to FastMCP 2.0+ with native HTTP transport support
- **Starlette Integration**: ASGI app with middleware support
- **Structured Logging**: Better debugging and monitoring

## Quick Start

### Client Configuration

Add this to your MCP client configuration (Claude Desktop, Cursor, Windsurf, etc.):

**Option 1: MCP Key Service (recommended for hosted clients)**

Get a `usr_xxx` API key from the [MCP Key Service portal](https://mcpkeys.techmavie.digital), then:

```json
{
  "mcpServers": {
    "reddit": {
      "transport": "streamable-http",
      "url": "https://mcp.techmavie.digital/reddit/mcp/usr_YOUR_KEY_HERE"
    }
  }
}
```

**Option 2: Direct Reddit credentials (for personal/self-hosted use)**
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

**Option 3: Without credentials (if server has env vars configured)**
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
| `fetch_reddit_hot_threads` | Fetch threads from any subreddit with sorting, time filter, and pagination |
| `fetch_reddit_post_content` | Get detailed post content with configurable comment sorting |
| `search_reddit` | Search Reddit for posts matching a query |
| `fetch_subreddit_info` | Get subreddit metadata, subscriber count, and rules |
| `fetch_user_profile` | Fetch user profile info and recent activity |
| `search_user_posts` | Search for posts by a specific user (works even with hidden profiles) |

### Tool Parameters

#### `fetch_reddit_hot_threads`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `subreddit` | string | *required* | Subreddit name (without `r/` prefix) |
| `limit` | int | 10 | Number of posts to fetch |
| `sort` | string | `hot` | Sort order: `hot`, `new`, `top`, `rising`, `controversial` |
| `time_filter` | string | `day` | Time filter (for `top`/`controversial`): `hour`, `day`, `week`, `month`, `year`, `all` |
| `after` | string | | Pagination cursor for next page |
| `before` | string | | Pagination cursor for previous page |

#### `fetch_reddit_post_content`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `post_id` | string | *required* | Reddit post ID |
| `comment_limit` | int | 20 | Number of top-level comments |
| `comment_depth` | int | 3 | Maximum comment tree depth |
| `comment_sort` | string | `top` | Comment sort: `top`, `best`, `new`, `controversial`, `old`, `qa` |

#### `search_reddit`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query |
| `subreddit` | string | | Subreddit to search within (empty = all of Reddit) |
| `sort` | string | `relevance` | Sort: `relevance`, `hot`, `top`, `new`, `comments` |
| `time_filter` | string | `all` | Time filter: `hour`, `day`, `week`, `month`, `year`, `all` |
| `limit` | int | 10 | Number of results |

#### `fetch_subreddit_info`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `subreddit` | string | *required* | Subreddit name (without `r/` prefix) |

#### `fetch_user_profile`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `username` | string | *required* | Reddit username (without `u/` prefix) |
| `content_type` | string | `overview` | Content type: `overview`, `submitted`, `comments` |
| `sort` | string | `new` | Sort: `hot`, `new`, `top`, `controversial` |
| `limit` | int | 10 | Number of items to fetch |
| `time_filter` | string | | Time filter for `top`/`controversial`: `hour`, `day`, `week`, `month`, `year`, `all` |
| `after` | string | | Pagination cursor for next page |
| `before` | string | | Pagination cursor for previous page |

#### `search_user_posts`
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `username` | string | *required* | Reddit username (without `u/` prefix) |
| `query` | string | | Additional search query to filter results |
| `subreddit` | string | | Subreddit to search within (empty = all of Reddit) |
| `sort` | string | `new` | Sort: `relevance`, `hot`, `top`, `new`, `comments` |
| `time_filter` | string | `all` | Time filter: `hour`, `day`, `week`, `month`, `year`, `all` |
| `limit` | int | 10 | Number of results |

## Credential Configuration

Reddit API credentials are resolved using the following priority chain (highest to lowest):

| Priority | Method | Example |
|----------|--------|---------|
| 1 | **Tool parameters** | `client_id` / `client_secret` passed directly to a tool call |
| 2 | **MCP Key Service** | `/mcp/usr_xxx` in URL path or `?api_key=usr_xxx` in query |
| 3 | **HTTP Headers** | `X-Reddit-Client-ID: xxx` and `X-Reddit-Client-Secret: xxx` |
| 4 | **URL Query Params** | `?client_id=xxx&client_secret=xxx` |
| 5 | **Environment Variables** | `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env` |

### MCP Key Service (recommended for hosted use)

The server integrates with [mcp-key-service](https://github.com/hithereiamaliff/mcp-key-service) for secure credential management. Instead of passing raw Reddit credentials, users obtain a `usr_xxx` key from the key service portal. The MCP server resolves the key to Reddit credentials server-side.

**Connection URL formats:**
- Path-based: `https://mcp.techmavie.digital/reddit/mcp/usr_YOUR_KEY`
- Query-based: `https://mcp.techmavie.digital/reddit/mcp?api_key=usr_YOUR_KEY`

**Server-side setup** (in `.env` or Docker environment):
```
KEY_SERVICE_URL=https://mcpkeys.techmavie.digital
KEY_SERVICE_TOKEN=your_internal_service_token
```

When `KEY_SERVICE_URL` is not set, the key service middleware is completely disabled (backward compatible).

### Direct Reddit credentials

To get Reddit API credentials directly:
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
> "Search Reddit for posts about Python web frameworks"
> "Tell me about the r/programming subreddit"
> "What has user spez been posting recently?"
> "Show me the top posts of the week in r/science"
> "Find posts by a user whose profile is hidden"

The assistant will use the appropriate MCP tool to retrieve and summarize the content.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (JSON) |
| `/mcp` | POST | MCP protocol endpoint (with env var or header credentials) |
| `/mcp/usr_xxx` | POST | MCP protocol endpoint (with key service credential resolution) |
| `/mcp?api_key=usr_xxx` | POST | MCP protocol endpoint (key service via query param) |
| `/analytics` | GET | Analytics summary (JSON) |
| `/analytics/dashboard` | GET | Visual analytics dashboard (HTML) |
| `/analytics/import` | POST | Import analytics from backup |

### Analytics Dashboard

Access the visual dashboard at:
```
https://mcp.techmavie.digital/reddit/analytics/dashboard
```

Features:
- Real-time metrics with auto-refresh (30 seconds)
- Tool usage charts
- Hourly request trends
- Client breakdown
- Recent tool call activity

## Architecture

```
Client (Claude, Cursor, Windsurf, etc.)
    ↓ HTTPS
https://mcp.techmavie.digital/reddit/mcp/usr_xxx
    ↓
Nginx (SSL termination + reverse proxy)
    ↓ HTTP
Docker Container (port 8089 → 8080)
    ↓
KeyServiceMiddleware (resolves usr_xxx → Reddit credentials)
    ↓                           ↓
    ↓                   MCP Key Service
    ↓                (mcpkeys.techmavie.digital)
    ↓
MCP Server (Streamable HTTP Transport)
    ↓
Reddit API
```

## License

[MIT](LICENSE) 
